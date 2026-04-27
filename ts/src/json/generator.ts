import { YangModule, YangStatement } from "../core/model";
import { YangTokenType } from "../parser/parser-context";
import { expandUses } from "../transform/uses-expand";
import { YANG_SCHEMA_KEYS } from "./schema-keys";
import {
  JSON_SCHEMA_DRAFT_2020_12,
  JSON_TYPE_ARRAY,
  JSON_TYPE_FREE_FORM,
  JSON_TYPE_OBJECT,
  leafTypeToSchema
} from "./type-constants";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function isSchemaDataNode(stmt: YangStatement): boolean {
  return [
    YangTokenType.CONTAINER,
    YangTokenType.LIST,
    YangTokenType.LEAF,
    YangTokenType.LEAF_LIST,
    YangTokenType.CHOICE,
    YangTokenType.CASE,
    YangTokenType.ANYDATA,
    YangTokenType.ANYXML
  ].includes((stmt.keyword ?? "") as YangTokenType);
}

/** Paths with predicates cannot be cache-resolved (matches Python JSON generator). */
function pathHasPredicate(path: unknown): boolean {
  if (typeof path === "string") {
    return path.includes("[");
  }
  const shape = asRecord(path);
  if (shape.kind !== "path") {
    return false;
  }
  const segmentsRaw = Array.isArray(shape.segments) ? shape.segments : [];
  return segmentsRaw.some((seg) => {
    const s = asRecord(seg);
    return s.predicate !== undefined && s.predicate !== null;
  });
}

function pathText(path: unknown): string {
  if (typeof path === "string") {
    return path;
  }
  const shape = asRecord(path);
  if (shape.kind !== "path") {
    return "";
  }
  const segmentsRaw = Array.isArray(shape.segments) ? shape.segments : [];
  const segments = segmentsRaw
    .map((seg) => asRecord(seg).step)
    .filter((step): step is string => typeof step === "string" && step.length > 0);
  if (segments.length === 0) {
    return "";
  }
  const absolute = shape.isAbsolute === true;
  return `${absolute ? "/" : ""}${segments.join("/")}`;
}

function mustToXYang(stmt: YangStatement): Array<Record<string, unknown>> {
  const out: Array<Record<string, unknown>> = [];
  for (const child of stmt.statements) {
    if (child.keyword !== YangTokenType.MUST || typeof child.argument !== "string") {
      continue;
    }
    out.push({
      must: child.argument,
      "error-message": typeof child.data.error_message === "string" ? child.data.error_message : "",
      description: typeof child.data.description === "string" ? child.data.description : ""
    });
  }
  return out;
}

function withStatementMeta(
  stmt: YangStatement,
  meta: Record<string, unknown>
): Record<string, unknown> {
  const out = { ...meta };
  const ifFeatures = Array.isArray(stmt.data.if_features)
    ? stmt.data.if_features.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
    : [];
  if (ifFeatures.length > 0) {
    out["if-features"] = ifFeatures;
  }
  const whenShape = asRecord(stmt.data.when);
  const whenExpression = typeof whenShape.expression === "string" ? whenShape.expression : "";
  if (whenExpression.trim().length > 0) {
    const whenOut: Record<string, unknown> = { condition: whenExpression };
    const wd =
      typeof whenShape.description === "string" && whenShape.description.trim().length > 0
        ? whenShape.description.trim()
        : "";
    if (wd.length > 0) {
      whenOut.description = wd;
    }
    out.when = whenOut;
  }
  const presenceRaw = stmt.data.presence;
  if (typeof presenceRaw === "string" && presenceRaw.trim().length > 0) {
    out.presence = presenceRaw;
  }
  const must = mustToXYang(stmt);
  if (must.length > 0) {
    out.must = must;
  }
  return out;
}

function resolveAbsoluteLeafTypePath(module: YangModule, path: unknown): Record<string, unknown> | undefined {
  if (pathHasPredicate(path)) {
    return undefined;
  }
  let segments: string[];
  if (typeof path === "string") {
    if (!path.startsWith("/")) {
      return undefined;
    }
    segments = path.split("/").map((x) => x.trim()).filter(Boolean);
  } else {
    const shape = asRecord(path);
    if (shape.kind !== "path" || shape.isAbsolute !== true) {
      return undefined;
    }
    const segmentsRaw = Array.isArray(shape.segments) ? shape.segments : [];
    segments = segmentsRaw
      .map((seg) => asRecord(seg).step)
      .filter((step): step is string => typeof step === "string" && step.length > 0);
  }
  if (segments.length === 0) {
    return undefined;
  }
  let level = module.statements;
  let current: YangStatement | undefined;
  for (const seg of segments) {
    const name = seg.includes(":") ? seg.split(":")[1] : seg;
    current = level.find((stmt) => stmt.name === name);
    if (!current) {
      return undefined;
    }
    level = current.statements;
  }
  if (current?.keyword !== YangTokenType.LEAF) {
    return undefined;
  }
  return asRecord(current.data.type);
}

function typedefRefOrInline(
  typeShape: Record<string, unknown>,
  typedefNames: Set<string>
): Record<string, unknown> {
  const typeName = typeof typeShape.name === "string" ? typeShape.name : "";
  if (typedefNames.has(typeName)) {
    return { $ref: `#/$defs/${typeName}` };
  }
  return leafTypeToSchema(typeShape);
}

function partitionChoiceSiblings(children: YangStatement[]): {
  others: YangStatement[];
  soleChoice: YangStatement | undefined;
} {
  const choices = children.filter((c) => c.keyword === YangTokenType.CHOICE);
  const others = children.filter((c) => c.keyword !== YangTokenType.CHOICE);
  if (choices.length === 1) {
    return { others, soleChoice: choices[0] };
  }
  return { others: children, soleChoice: undefined };
}

/** Match Python `_merge_oneof_branches_with_base`: hoist choice branches with sibling properties. */
function mergeOneOfBranchesWithBase(
  oneOf: Array<Record<string, unknown>>,
  baseProps: Record<string, unknown>,
  baseRequired: string[]
): Array<Record<string, unknown>> {
  const merged: Array<Record<string, unknown>> = [];
  const baseReqUnique = [...new Set(baseRequired)];
  for (const branch of oneOf) {
    if (branch.type === JSON_TYPE_OBJECT && branch.maxProperties === 0) {
      if (Object.keys(baseProps).length > 0 || baseReqUnique.length > 0) {
        merged.push({
          type: JSON_TYPE_OBJECT,
          properties: { ...baseProps },
          required: [...baseReqUnique],
          additionalProperties: false
        });
      } else {
        merged.push({ ...branch });
      }
      continue;
    }
    const bp = asRecord(branch.properties);
    const br = Array.isArray(branch.required)
      ? (branch.required as string[]).filter((x): x is string => typeof x === "string")
      : [];
    const mergedBranch: Record<string, unknown> = {
      type: JSON_TYPE_OBJECT,
      properties: { ...baseProps, ...bp },
      required: [...new Set([...baseRequired, ...br])].sort(),
      additionalProperties: false
    };
    const bDesc = branch.description;
    if (typeof bDesc === "string" && bDesc.length > 0) {
      mergedBranch.description = bDesc;
    }
    const bXy = branch[YANG_SCHEMA_KEYS.xYang];
    if (bXy && typeof bXy === "object" && !Array.isArray(bXy) && Object.keys(bXy as object).length > 0) {
      mergedBranch[YANG_SCHEMA_KEYS.xYang] = { ...(bXy as Record<string, unknown>) };
    }
    merged.push(mergedBranch);
  }
  return merged;
}

/** Match Python `_choice_meta_xyang` (hoisted choice on container/list only). */
function choiceMetaForXYang(choice: YangStatement): Record<string, unknown> {
  const meta: Record<string, unknown> = {
    name: choice.name ?? "",
    description: typeof choice.data.description === "string" ? choice.data.description : "",
    mandatory: choice.data.mandatory === true
  };
  const ifFeatures = Array.isArray(choice.data.if_features)
    ? choice.data.if_features.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
    : [];
  if (ifFeatures.length > 0) {
    meta["if-features"] = ifFeatures;
  }
  return meta;
}

function buildSoleChoiceObjectSchema(
  others: YangStatement[],
  soleChoice: YangStatement,
  module: YangModule,
  typedefNames: Set<string>
): Record<string, unknown> {
  const properties: Record<string, unknown> = {};
  const required: string[] = [];
  for (const child of others) {
    if (!child.name || !isSchemaDataNode(child)) {
      continue;
    }
    properties[child.name] = statementToSchema(child, module, typedefNames);
    if (
      [YangTokenType.LEAF, YangTokenType.ANYDATA, YangTokenType.ANYXML].includes((child.keyword ?? "") as YangTokenType) &&
      child.data.mandatory === true
    ) {
      required.push(child.name);
    }
  }
  const choiceShape = buildChoiceOneOf(soleChoice, module, typedefNames);
  const oneOfArr = (choiceShape?.oneOf as Array<Record<string, unknown>>) ?? [];
  if (Object.keys(properties).length === 0 && required.length === 0) {
    return { type: JSON_TYPE_OBJECT, oneOf: oneOfArr };
  }
  return {
    type: JSON_TYPE_OBJECT,
    oneOf: mergeOneOfBranchesWithBase(oneOfArr, properties, required)
  };
}

function buildMultiChildObjectSchema(
  statements: YangStatement[],
  module: YangModule,
  typedefNames: Set<string>
): Record<string, unknown> {
  const properties: Record<string, unknown> = {};
  const required: string[] = [];
  for (const child of statements) {
    if (child.keyword === YangTokenType.CHOICE) {
      if (!child.name) {
        continue;
      }
      properties[child.name] = statementToSchema(child, module, typedefNames);
      continue;
    }
    if (!child.name || !isSchemaDataNode(child)) {
      continue;
    }
    properties[child.name] = statementToSchema(child, module, typedefNames);
    if (
      [YangTokenType.LEAF, YangTokenType.ANYDATA, YangTokenType.ANYXML].includes((child.keyword ?? "") as YangTokenType) &&
      child.data.mandatory === true
    ) {
      required.push(child.name);
    }
  }
  const out: Record<string, unknown> = {
    type: JSON_TYPE_OBJECT,
    properties,
    additionalProperties: false
  };
  if (required.length > 0) {
    out.required = required;
  }
  return out;
}

function buildChoiceOneOf(
  choice: YangStatement,
  module: YangModule,
  typedefNames: Set<string>
): Record<string, unknown> | undefined {
  const branches: Array<Record<string, unknown>> = [];
  const cases = choice.statements.filter((stmt) => stmt.keyword === YangTokenType.CASE);
  const mandatory = choice.data.mandatory === true;

  if (!mandatory) {
    branches.push({ type: JSON_TYPE_OBJECT, maxProperties: 0 });
  }

  for (const c of cases) {
    const properties: Record<string, unknown> = {};
    const required: string[] = [];
    for (const child of c.statements) {
      if (!child.name || !isSchemaDataNode(child)) {
        continue;
      }
      properties[child.name] = statementToSchema(child, module, typedefNames);
      required.push(child.name);
    }
    if (Object.keys(properties).length === 0) {
      continue;
    }
    const branch: Record<string, unknown> = {
      type: JSON_TYPE_OBJECT,
      description: typeof c.data.description === "string" ? c.data.description : "",
      properties,
      additionalProperties: false,
      required,
      [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(c, { name: c.name ?? "case" })
    };
    branches.push(branch);
  }

  if (branches.length === 0) {
    return undefined;
  }
  return {
    oneOf: branches
  };
}

function statementToSchema(
  stmt: YangStatement,
  module: YangModule,
  typedefNames: Set<string>
): Record<string, unknown> {
  const keyword = stmt.keyword ?? "";

  if (keyword === YangTokenType.CHOICE) {
    const oneOfShape = buildChoiceOneOf(stmt, module, typedefNames);
    const xyChoice: Record<string, unknown> = {
      type: "choice",
      mandatory: stmt.data.mandatory === true
    };
    const ifFeatures = Array.isArray(stmt.data.if_features)
      ? stmt.data.if_features.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
      : [];
    if (ifFeatures.length > 0) {
      xyChoice["if-features"] = ifFeatures;
    }
    const out: Record<string, unknown> = {
      type: JSON_TYPE_OBJECT,
      description: typeof stmt.data.description === "string" ? stmt.data.description : "",
      [YANG_SCHEMA_KEYS.xYang]: xyChoice
    };
    if (oneOfShape?.oneOf) {
      out.oneOf = oneOfShape.oneOf;
    }
    return out;
  }

  if (keyword === YangTokenType.CONTAINER) {
    const { others, soleChoice } = partitionChoiceSiblings(stmt.statements);
    const xYang = withStatementMeta(stmt, { type: keyword }) as Record<string, unknown>;
    if (soleChoice) {
      xYang.choice = choiceMetaForXYang(soleChoice);
    }
    const body = soleChoice
      ? buildSoleChoiceObjectSchema(others, soleChoice, module, typedefNames)
      : buildMultiChildObjectSchema(stmt.statements, module, typedefNames);
    const out: Record<string, unknown> = {
      ...body,
      description: typeof stmt.data.description === "string" ? stmt.data.description : "",
      [YANG_SCHEMA_KEYS.xYang]: xYang
    };
    return out;
  }

  if (keyword === YangTokenType.LIST) {
    const { others, soleChoice } = partitionChoiceSiblings(stmt.statements);
    const listXY = withStatementMeta(stmt, {
      type: keyword,
      key: typeof stmt.data.key === "string" ? stmt.data.key : undefined
    }) as Record<string, unknown>;
    if (soleChoice) {
      listXY.choice = choiceMetaForXYang(soleChoice);
    }
    const itemSchema = soleChoice
      ? buildSoleChoiceObjectSchema(others, soleChoice, module, typedefNames)
      : buildMultiChildObjectSchema(stmt.statements, module, typedefNames);
    const out: Record<string, unknown> = {
      type: JSON_TYPE_ARRAY,
      items: itemSchema,
      description: typeof stmt.data.description === "string" ? stmt.data.description : "",
      [YANG_SCHEMA_KEYS.xYang]: listXY
    };
    if (typeof stmt.data.min_elements === "number") {
      out.minItems = stmt.data.min_elements;
    }
    if (typeof stmt.data.max_elements === "number") {
      out.maxItems = stmt.data.max_elements;
    }
    return out;
  }

  if (keyword === YangTokenType.LEAF_LIST) {
    const typeShape = asRecord(stmt.data.type);
    const itemSchema = typedefRefOrInline(typeShape, typedefNames);
    const typeName = (typeShape.name as string | undefined) ?? YangTokenType.STRING_KW;
    const out: Record<string, unknown> = {
      type: JSON_TYPE_ARRAY,
      items: itemSchema,
      description: typeof stmt.data.description === "string" ? stmt.data.description : "",
      [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(stmt, {
        type: keyword
      })
    };
    if (typeName === YangTokenType.LEAFREF) {
      const itemsXYang = asRecord(out.items);
      itemsXYang[YANG_SCHEMA_KEYS.xYang] = {
        type: YangTokenType.LEAFREF,
        path: pathText(typeShape.path),
        "require-instance": typeShape.require_instance !== false
      };
      out.items = itemsXYang;
    }
    if (typeName === YangTokenType.INSTANCE_IDENTIFIER) {
      const itemsXYang = asRecord(out.items);
      itemsXYang[YANG_SCHEMA_KEYS.xYang] = {
        type: YangTokenType.INSTANCE_IDENTIFIER,
        "require-instance": typeShape.require_instance !== false
      };
      out.items = itemsXYang;
    }
    if (typeof stmt.data.min_elements === "number") {
      out.minItems = stmt.data.min_elements;
    }
    if (typeof stmt.data.max_elements === "number") {
      out.maxItems = stmt.data.max_elements;
    }
    const llDefaults = stmt.data.defaults as unknown[] | undefined;
    if (Array.isArray(llDefaults) && llDefaults.length > 0) {
      out.default = llDefaults;
    }
    return out;
  }

  if (keyword === YangTokenType.LEAF) {
    const typeShape = asRecord(stmt.data.type);
    const typeName = (typeShape.name as string | undefined) ?? YangTokenType.STRING_KW;
    let leafSchema = typedefRefOrInline(typeShape, typedefNames);

    if (typeName === YangTokenType.LEAFREF) {
      const targetType = resolveAbsoluteLeafTypePath(module, typeShape.path);
      leafSchema = targetType
        ? typedefRefOrInline(targetType, typedefNames)
        : leafTypeToSchema({ name: YangTokenType.STRING_KW });
    }

    const xYang = withStatementMeta(stmt, {
      type: keyword
    });
    if (stmt.data.mandatory === true) {
      xYang.mandatory = true;
    }
    if (typeName === YangTokenType.LEAFREF) {
      xYang.type = YangTokenType.LEAFREF;
      xYang.path = pathText(typeShape.path);
      xYang["require-instance"] = typeShape.require_instance !== false;
    }
    if (typeName === YangTokenType.IDENTITYREF) {
      xYang.type = YangTokenType.IDENTITYREF;
      const bases = Array.isArray(typeShape.identityref_bases)
        ? typeShape.identityref_bases.filter((x): x is string => typeof x === "string")
        : [];
      if (bases.length > 0) {
        xYang.bases = bases;
      }
    }
    if (typeName === YangTokenType.INSTANCE_IDENTIFIER) {
      xYang.type = YangTokenType.INSTANCE_IDENTIFIER;
      xYang["require-instance"] = typeShape.require_instance !== false;
    }

    const schemaXy = asRecord(leafSchema[YANG_SCHEMA_KEYS.xYang]);
    const out: Record<string, unknown> = {
      ...leafSchema,
      description: typeof stmt.data.description === "string" ? stmt.data.description : "",
      [YANG_SCHEMA_KEYS.xYang]: { ...xYang, ...schemaXy }
    };
    if (stmt.data.default !== undefined) {
      out.default = stmt.data.default;
    }
    return out;
  }

  if (keyword === YangTokenType.ANYDATA || keyword === YangTokenType.ANYXML) {
    const out: Record<string, unknown> = {
      type: JSON_TYPE_FREE_FORM,
      description: typeof stmt.data.description === "string" ? stmt.data.description : "",
      [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(stmt, {
        type: keyword
      })
    };
    return out;
  }

  return {
    type: JSON_TYPE_FREE_FORM
  };
}

function typedefToSchema(module: YangModule): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const typedefs = module.typedefs as Record<string, { type?: unknown; description?: string }>;
  const names = new Set(Object.keys(typedefs));
  for (const [name, entry] of Object.entries(typedefs)) {
    const typeShape = asRecord(entry.type);
    const schema = typedefRefOrInline(typeShape, names);
    const def: Record<string, unknown> = {
      ...schema,
      description: typeof entry.description === "string" ? entry.description : ""
    };
    const schemaXy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
    const typedefXy: Record<string, unknown> = {};
    if (typeof typeShape.pattern_error_message === "string" && typeShape.pattern_error_message.length > 0) {
      typedefXy["pattern-error-message"] = typeShape.pattern_error_message;
    }
    if (typeof typeShape.pattern_error_app_tag === "string" && typeShape.pattern_error_app_tag.length > 0) {
      typedefXy["pattern-error-app-tag"] = typeShape.pattern_error_app_tag;
    }
    if (Object.keys(schemaXy).length > 0 || Object.keys(typedefXy).length > 0) {
      def[YANG_SCHEMA_KEYS.xYang] = { ...schemaXy, ...typedefXy };
    }
    out[name] = def;
  }
  return out;
}

function identityToSchema(module: YangModule): Record<string, unknown> {
  const raw = module.identities as Record<string, { bases?: string[] }>;
  const identityNames = Object.keys(raw);
  if (identityNames.length === 0) {
    return {};
  }

  const childrenByBase: Record<string, string[]> = {};
  for (const [identityName, info] of Object.entries(raw)) {
    const bases = Array.isArray(info?.bases) ? info.bases.filter((x): x is string => typeof x === "string") : [];
    for (const base of bases) {
      if (!childrenByBase[base]) {
        childrenByBase[base] = [];
      }
      childrenByBase[base].push(identityName);
    }
  }

  const descendants = (name: string): string[] => {
    const out = new Set<string>([name]);
    const stack = [...(childrenByBase[name] ?? [])];
    while (stack.length > 0) {
      const next = stack.pop() as string;
      if (out.has(next)) {
        continue;
      }
      out.add(next);
      stack.push(...(childrenByBase[next] ?? []));
    }
    return [...out].sort();
  };

  const defs: Record<string, unknown> = {};
  for (const [identityName, info] of Object.entries(raw)) {
    const bases = Array.isArray(info?.bases) ? info.bases.filter((x): x is string => typeof x === "string") : [];
    defs[identityName] = {
      type: "string",
      enum: descendants(identityName),
      [YANG_SCHEMA_KEYS.xYang]: {
        type: YangTokenType.IDENTITY,
        ...(bases.length > 0 ? { bases } : {})
      }
    };
  }
  return defs;
}

export function generateJsonSchema(module: YangModule): Record<string, unknown> {
  // Preserve parse-time AST shape (reversible YANG <-> yang.json) while still
  // emitting a flattened schema view.
  const effectiveModule = expandUses(module);
  const properties: Record<string, unknown> = {};
  const required: string[] = [];
  const typedefNames = new Set(Object.keys(effectiveModule.typedefs as Record<string, unknown>));

  for (const stmt of effectiveModule.statements) {
    if (!stmt.name) {
      continue;
    }
    if (
      ![
        YangTokenType.CONTAINER,
        YangTokenType.LIST,
        YangTokenType.LEAF,
        YangTokenType.LEAF_LIST,
        YangTokenType.ANYDATA,
        YangTokenType.ANYXML
      ].includes((stmt.keyword ?? "") as YangTokenType)
    ) {
      continue;
    }
    properties[stmt.name] = statementToSchema(stmt, effectiveModule, typedefNames);
    if (
      [YangTokenType.LEAF, YangTokenType.ANYDATA, YangTokenType.ANYXML].includes((stmt.keyword ?? "") as YangTokenType) &&
      stmt.data.mandatory === true
    ) {
      required.push(stmt.name);
    }
  }

  const schema: Record<string, unknown> = {
    $schema: JSON_SCHEMA_DRAFT_2020_12,
    $id: effectiveModule.namespace ? effectiveModule.namespace : (effectiveModule.name ? `urn:${effectiveModule.name}` : "urn:module"),
    description: effectiveModule.description ?? "",
    type: JSON_TYPE_OBJECT,
    properties,
    additionalProperties: false,
    [YANG_SCHEMA_KEYS.xYang]: {
      module: effectiveModule.name,
      "yang-version": effectiveModule.yangVersion ?? "1.1",
      namespace: effectiveModule.namespace,
      prefix: effectiveModule.prefix,
      organization: effectiveModule.organization ?? "",
      contact: effectiveModule.contact ?? ""
    }
  };

  if (required.length > 0) {
    schema.required = required;
  }
  const defs = {
    ...typedefToSchema(effectiveModule),
    ...identityToSchema(effectiveModule)
  };
  if (Object.keys(defs).length > 0) {
    schema.$defs = defs;
  }

  return schema;
}
