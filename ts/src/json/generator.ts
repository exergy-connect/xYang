import {
  coerceIdentifierRef,
  formatIdentifierRef,
  parseIdentifierRefAtom
} from "../core/identifier-ref";
import { YangModule, YangStatement } from "../core/model";
import { hasTokenType, YangTokenType } from "../parser/parser-context";
import { expandUses } from "../transform/uses-expand";
import { jsonSchemaDefaultValue } from "./default-values";
import { XYANG_KEYS, YANG_SCHEMA_KEYS } from "./schema-keys";
import {
  JSON_SCHEMA_DRAFT_2020_12,
  JSON_TYPE_ARRAY,
  JSON_TYPE_FREE_FORM,
  JSON_TYPE_OBJECT,
} from "./type-constants";
import { leafTypeToSchema, REGISTRY } from "../types/registry";
import { resolveTypedef } from "../validator/type-checker";

/** Emit ``description`` only when *text* is a non-empty string. */
function withDescription(out: Record<string, unknown>, text: unknown): void {
  if (typeof text === "string" && text.length > 0) {
    out.description = text;
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function isSchemaDataNode(stmt: YangStatement): boolean {
  return hasTokenType(stmt.keyword ?? "", [
    YangTokenType.CONTAINER,
    YangTokenType.LIST,
    YangTokenType.LEAF,
    YangTokenType.LEAF_LIST,
    YangTokenType.CHOICE,
    YangTokenType.CASE,
    YangTokenType.ANYDATA,
    YangTokenType.ANYXML
  ]);
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

/** `{ "xpath-prefixes": {prefix: module} }` for a bound expression; the JSON form has no imports. */
function xpathPrefixesEntry(recorded: unknown): Record<string, unknown> {
  if (!recorded || typeof recorded !== "object" || Object.keys(recorded).length === 0) {
    return {};
  }
  const sorted = Object.keys(recorded as Record<string, string>)
    .sort()
    .map((prefix) => [prefix, (recorded as Record<string, string>)[prefix]]);
  return { [XYANG_KEYS.xpathPrefixes]: Object.fromEntries(sorted) };
}

/** RFC 7951 member name: `module:name` for a node another module defines (augment). */
function propertyKey(stmt: YangStatement, module: YangModule): string {
  const owner = stmt.defining_module;
  return owner && owner !== module.name ? `${owner}:${stmt.name}` : (stmt.name ?? "");
}

function mustToXYang(stmt: YangStatement): Array<Record<string, unknown>> {
  const out: Array<Record<string, unknown>> = [];
  for (const child of stmt.statements) {
    if (child.keyword !== YangTokenType.MUST || typeof child.argument !== "string") {
      continue;
    }
    const entry: Record<string, unknown> = {
      must: child.argument,
      "error-message": typeof child.error_message === "string" ? child.error_message : "",
      ...xpathPrefixesEntry(child.xpath_prefixes)
    };
    withDescription(entry, child.description);
    out.push(entry);
  }
  return out;
}

function explicitConfig(stmt: YangStatement): boolean | undefined {
  const cfg = stmt.config;
  return typeof cfg === "boolean" ? cfg : undefined;
}

function withStatementMeta(
  stmt: YangStatement,
  meta: Record<string, unknown>
): Record<string, unknown> {
  const out = { ...meta };
  const config = explicitConfig(stmt);
  if (config !== undefined) {
    out[XYANG_KEYS.config] = config;
  }
  const ifFeatures = Array.isArray(stmt.if_features)
    ? stmt.if_features.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
    : [];
  if (ifFeatures.length > 0) {
    out["if-features"] = ifFeatures;
  }
  const whenShape = asRecord(stmt.when);
  const whenExpression = typeof whenShape.expression === "string" ? whenShape.expression : "";
  if (whenExpression.trim().length > 0) {
    const whenOut: Record<string, unknown> = {
      condition: whenExpression,
      ...xpathPrefixesEntry(whenShape.xpath_prefixes as Record<string, string> | undefined)
    };
    const wd =
      typeof whenShape.description === "string" && whenShape.description.trim().length > 0
        ? whenShape.description.trim()
        : "";
    if (wd.length > 0) {
      whenOut.description = wd;
    }
    out.when = whenOut;
  }
  const presenceRaw = stmt.presence;
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
    const name = parseIdentifierRefAtom(seg).name;
    current = level.find((stmt) => stmt.name === name);
    if (!current) {
      return undefined;
    }
    level = current.statements;
  }
  if (current?.keyword !== YangTokenType.LEAF) {
    return undefined;
  }
  return asRecord(current.type);
}

/**
 * Follow a `type` that names a typedef of another module to that typedef's own type; the JSON form's
 * `$defs` hold only this module's typedefs. Restrictions on such a `type` cannot be kept, so they fail.
 */
function foreignTypedefResolved(typeShape: Record<string, unknown>, module: YangModule): Record<string, unknown> {
  let current = typeShape;
  for (let depth = 0; depth < 64; depth += 1) {
    const typeName = typeof current.name === "string" ? current.name : "";
    const prefix = typeof current.prefix === "string" && current.prefix ? current.prefix : undefined;
    const scope = typeof current.scope_module === "string" ? current.scope_module : undefined;
    const foreign = prefix !== undefined || (scope !== undefined && scope !== module.name);
    if (!foreign || (!prefix && Object.prototype.hasOwnProperty.call(REGISTRY, typeName))) {
      return current;
    }
    const label = prefix ? `${prefix}:${typeName}` : typeName;
    const typedef = resolveTypedef(module, current);
    if (!typedef?.type) {
      throw new Error(`cannot export type '${label}': its typedef is not found where the type is written`);
    }
    if (current.range || current.length || (Array.isArray(current.patterns) && current.patterns.length > 0)) {
      throw new Error(`cannot export restrictions on the imported typedef '${label}' in the native JSON form`);
    }
    current = typedef.type;
  }
  return current;
}

function typedefRefOrInline(
  typeShape: Record<string, unknown>,
  typedefNames: Set<string>,
  module: YangModule
): Record<string, unknown> {
  const typeName = typeof typeShape.name === "string" ? typeShape.name : "";
  const prefix = typeof typeShape.prefix === "string" && typeShape.prefix ? typeShape.prefix : undefined;
  const scope = typeof typeShape.scope_module === "string" ? typeShape.scope_module : undefined;
  const local = !prefix && (scope === undefined || scope === module.name);
  if (local && typedefNames.has(typeName)) {
    return { $ref: `#/$defs/${typeName}` };
  }
  if (!prefix && Object.prototype.hasOwnProperty.call(REGISTRY, typeName)) {
    return leafTypeToSchema(typeShape);
  }
  // A typedef from another module is inlined; the JSON form's `$defs` hold only this module's.
  const label = prefix ? `${prefix}:${typeName}` : typeName;
  const typedef = resolveTypedef(module, typeShape);
  if (!typedef?.type) {
    throw new Error(`cannot export type '${label}': its typedef is not found where the type is written`);
  }
  if (typeShape.range || typeShape.length || (Array.isArray(typeShape.patterns) && typeShape.patterns.length > 0)) {
    throw new Error(`cannot export restrictions on the imported typedef '${label}' in the native JSON form`);
  }
  return typedefRefOrInline(typedef.type, new Set(), module);
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
    mandatory: choice.mandatory === true
  };
  withDescription(meta, choice.description);
  const ifFeatures = Array.isArray(choice.if_features)
    ? choice.if_features.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
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
    properties[propertyKey(child, module)] = statementToSchema(child, module, typedefNames);
    if (
      hasTokenType(child.keyword ?? "", [YangTokenType.LEAF, YangTokenType.ANYDATA, YangTokenType.ANYXML]) &&
      child.mandatory === true
    ) {
      required.push(propertyKey(child, module));
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

function ioBlockToSchema(
  stmt: YangStatement,
  module: YangModule,
  typedefNames: Set<string>,
  ioType: typeof YangTokenType.INPUT | typeof YangTokenType.OUTPUT
): Record<string, unknown> {
  const body = buildMultiChildObjectSchema(stmt.statements, module, typedefNames);
  const out: Record<string, unknown> = {
    ...body,
    [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(stmt, { type: ioType })
  };
  withDescription(out, stmt.description);
  return out;
}

/** One rpc for `x-yang.rpcs`, or one action for `x-yang.actions` (RFC 7950 §7.15). */
function rpcToJson(
  stmt: YangStatement,
  module: YangModule,
  typedefNames: Set<string>,
  kind: string = YangTokenType.RPC
): Record<string, unknown> {
  const out: Record<string, unknown> = {
    [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(stmt, { type: kind })
  };
  const inp = stmt.findStatement("input");
  if (inp?.keyword === YangTokenType.INPUT) {
    out.input = ioBlockToSchema(inp, module, typedefNames, YangTokenType.INPUT);
  }
  const outp = stmt.findStatement("output");
  if (outp?.keyword === YangTokenType.OUTPUT) {
    out.output = ioBlockToSchema(outp, module, typedefNames, YangTokenType.OUTPUT);
  }
  return out;
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
    properties[propertyKey(child, module)] = statementToSchema(child, module, typedefNames);
    if (
      hasTokenType(child.keyword ?? "", [YangTokenType.LEAF, YangTokenType.ANYDATA, YangTokenType.ANYXML]) &&
      child.mandatory === true
    ) {
      required.push(propertyKey(child, module));
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
  const mandatory = choice.mandatory === true;

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
      properties[propertyKey(child, module)] = statementToSchema(child, module, typedefNames);
      required.push(propertyKey(child, module));
    }
    if (Object.keys(properties).length === 0) {
      continue;
    }
    const branch: Record<string, unknown> = {
      type: JSON_TYPE_OBJECT,
      properties,
      additionalProperties: false,
      required,
      [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(c, { name: c.name ?? "case" })
    };
    withDescription(branch, c.description);
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
  const out = statementToSchemaBody(stmt, module, typedefNames);
  if (stmt.keyword !== YangTokenType.CONTAINER && stmt.keyword !== YangTokenType.LIST) {
    return out;
  }
  const actions: Record<string, unknown> = {};
  for (const child of stmt.statements) {
    if (child.keyword === YangTokenType.ACTION && child.name) {
      actions[propertyKey(child, module)] = rpcToJson(child, module, typedefNames, YangTokenType.ACTION);
    }
  }
  if (Object.keys(actions).length > 0) {
    asRecord(out[YANG_SCHEMA_KEYS.xYang])[XYANG_KEYS.actions] = actions;
  }
  return out;
}

function statementToSchemaBody(
  stmt: YangStatement,
  module: YangModule,
  typedefNames: Set<string>
): Record<string, unknown> {
  const keyword = stmt.keyword ?? "";

  if (keyword === YangTokenType.CHOICE) {
    const oneOfShape = buildChoiceOneOf(stmt, module, typedefNames);
    const xyChoice: Record<string, unknown> = {
      type: "choice",
      mandatory: stmt.mandatory === true
    };
    const choiceConfig = explicitConfig(stmt);
    if (choiceConfig !== undefined) {
      xyChoice[XYANG_KEYS.config] = choiceConfig;
    }
    const ifFeatures = Array.isArray(stmt.if_features)
      ? stmt.if_features.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
      : [];
    if (ifFeatures.length > 0) {
      xyChoice["if-features"] = ifFeatures;
    }
    const out: Record<string, unknown> = {
      type: JSON_TYPE_OBJECT,
      [YANG_SCHEMA_KEYS.xYang]: xyChoice
    };
    withDescription(out, stmt.description);
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
      [YANG_SCHEMA_KEYS.xYang]: xYang
    };
    withDescription(out, stmt.description);
    return out;
  }

  if (keyword === YangTokenType.LIST) {
    const { others, soleChoice } = partitionChoiceSiblings(stmt.statements);
    const listXY = withStatementMeta(stmt, {
      type: keyword,
      key: typeof stmt.key === "string" ? stmt.key : undefined
    }) as Record<string, unknown>;
    if (soleChoice) {
      listXY.choice = choiceMetaForXYang(soleChoice);
    }
    const unique = stmt.unique;
    if (Array.isArray(unique) && unique.length > 0) {
      listXY.unique = (unique as string[][]).map((paths) => [...paths]);
    }
    const itemSchema = soleChoice
      ? buildSoleChoiceObjectSchema(others, soleChoice, module, typedefNames)
      : buildMultiChildObjectSchema(stmt.statements, module, typedefNames);
    const out: Record<string, unknown> = {
      type: JSON_TYPE_ARRAY,
      items: itemSchema,
      [YANG_SCHEMA_KEYS.xYang]: listXY
    };
    withDescription(out, stmt.description);
    if (typeof stmt.min_elements === "number") {
      out.minItems = stmt.min_elements;
    }
    if (typeof stmt.max_elements === "number") {
      out.maxItems = stmt.max_elements;
    }
    return out;
  }

  if (keyword === YangTokenType.LEAF_LIST) {
    const typeShape = foreignTypedefResolved(asRecord(stmt.type), module);
    const itemSchema = typedefRefOrInline(typeShape, typedefNames, module);
    const typeName = (typeShape.name as string | undefined) ?? YangTokenType.STRING_KW;
    const out: Record<string, unknown> = {
      type: JSON_TYPE_ARRAY,
      items: itemSchema,
      [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(stmt, {
        type: keyword
      })
    };
    withDescription(out, stmt.description);
    if (typeName === YangTokenType.LEAFREF) {
      const itemsXYang = asRecord(out.items);
      itemsXYang[YANG_SCHEMA_KEYS.xYang] = {
        type: YangTokenType.LEAFREF,
        path: pathText(typeShape.path),
        "require-instance": typeShape.require_instance !== false,
        ...xpathPrefixesEntry(typeShape.xpath_prefixes)
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
    if (typeof stmt.min_elements === "number") {
      out.minItems = stmt.min_elements;
    }
    if (typeof stmt.max_elements === "number") {
      out.maxItems = stmt.max_elements;
    }
    const llDefaults = stmt.defaults as unknown[] | undefined;
    if (Array.isArray(llDefaults) && llDefaults.length > 0) {
      out.default = llDefaults;
    }
    return out;
  }

  if (keyword === YangTokenType.LEAF) {
    const typeShape = foreignTypedefResolved(asRecord(stmt.type), module);
    const typeName = (typeShape.name as string | undefined) ?? YangTokenType.STRING_KW;
    let leafSchema = typedefRefOrInline(typeShape, typedefNames, module);

    if (typeName === YangTokenType.LEAFREF) {
      const targetType = resolveAbsoluteLeafTypePath(module, typeShape.path);
      leafSchema = targetType
        ? typedefRefOrInline(targetType, typedefNames, module)
        : leafTypeToSchema({ name: YangTokenType.STRING_KW });
    }

    const xYang = withStatementMeta(stmt, {
      type: keyword
    });
    if (stmt.mandatory === true) {
      xYang.mandatory = true;
    }
    if (typeName === YangTokenType.LEAFREF) {
      xYang.type = YangTokenType.LEAFREF;
      xYang.path = pathText(typeShape.path);
      xYang["require-instance"] = typeShape.require_instance !== false;
      Object.assign(xYang, xpathPrefixesEntry(typeShape.xpath_prefixes));
    }
    if (typeName === YangTokenType.IDENTITYREF) {
      xYang.type = YangTokenType.IDENTITYREF;
      const bases = Array.isArray(typeShape.identityref_bases)
        ? typeShape.identityref_bases
            .map((b) => coerceIdentifierRef(b))
            .filter((b): b is NonNullable<typeof b> => Boolean(b))
            .map((b) => formatIdentifierRef(b))
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
    const { description: _leafTypeDescription, ...leafSchemaRest } = leafSchema;
    const out: Record<string, unknown> = {
      ...leafSchemaRest,
      [YANG_SCHEMA_KEYS.xYang]: { ...xYang, ...schemaXy }
    };
    withDescription(out, stmt.description);
    if (stmt.default !== undefined) {
      const schemaType = typeof out.type === "string" ? out.type : null;
      out.default = jsonSchemaDefaultValue(stmt.default, {
        yangTypeName: typeName,
        jsonSchemaType: schemaType
      });
    }
    return out;
  }

  if (keyword === YangTokenType.ANYDATA || keyword === YangTokenType.ANYXML) {
    const out: Record<string, unknown> = {
      type: JSON_TYPE_FREE_FORM,
      [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(stmt, {
        type: keyword
      })
    };
    withDescription(out, stmt.description);
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
    const schema = typedefRefOrInline(typeShape, names, module);
    const { description: _typedefTypeDescription, ...schemaRest } = schema;
    const def: Record<string, unknown> = {
      ...schemaRest
    };
    withDescription(def, entry.description);
    const schemaXy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
    const typedefXy: Record<string, unknown> = {};
    const rawPatList = Array.isArray(typeShape.patterns) ? typeShape.patterns : [];
    const lastPat = rawPatList.length > 0 ? (rawPatList[rawPatList.length - 1] as Record<string, unknown>) : null;
    if (lastPat && typeof lastPat.error_message === "string" && lastPat.error_message.length > 0) {
      typedefXy["pattern-error-message"] = lastPat.error_message;
    }
    if (lastPat && typeof lastPat.error_app_tag === "string" && lastPat.error_app_tag.length > 0) {
      typedefXy["pattern-error-app-tag"] = lastPat.error_app_tag;
    }
    if (Object.keys(schemaXy).length > 0 || Object.keys(typedefXy).length > 0) {
      def[YANG_SCHEMA_KEYS.xYang] = { ...schemaXy, ...typedefXy };
    }
    out[name] = def;
  }
  return out;
}

function identityBaseStrings(bases: unknown): string[] {
  if (!Array.isArray(bases)) {
    return [];
  }
  return bases
    .map((b) => coerceIdentifierRef(b))
    .filter((b): b is NonNullable<typeof b> => Boolean(b))
    .map((b) => formatIdentifierRef(b));
}

function identityToSchema(module: YangModule): Record<string, unknown> {
  const raw = module.identities as Record<string, { bases?: unknown }>;
  const identityNames = Object.keys(raw);
  if (identityNames.length === 0) {
    return {};
  }

  const childrenByBase: Record<string, string[]> = {};
  for (const [identityName, info] of Object.entries(raw)) {
    for (const base of identityBaseStrings(info?.bases)) {
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
    const bases = identityBaseStrings(info?.bases);
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
  if (effectiveModule !== module && module.module_registry && !effectiveModule.module_registry) {
    Object.defineProperty(effectiveModule, "module_registry", { value: module.module_registry, enumerable: false });
  }
  const properties: Record<string, unknown> = {};
  const required: string[] = [];
  const typedefNames = new Set(Object.keys(effectiveModule.typedefs as Record<string, unknown>));

  for (const stmt of effectiveModule.statements) {
    if (!stmt.name) {
      continue;
    }
    if (
      !hasTokenType(stmt.keyword ?? "", [
        YangTokenType.CONTAINER,
        YangTokenType.LIST,
        YangTokenType.LEAF,
        YangTokenType.LEAF_LIST,
        YangTokenType.ANYDATA,
        YangTokenType.ANYXML
      ])
    ) {
      continue;
    }
    properties[propertyKey(stmt, module)] = statementToSchema(stmt, effectiveModule, typedefNames);
    if (
      hasTokenType(stmt.keyword ?? "", [YangTokenType.LEAF, YangTokenType.ANYDATA, YangTokenType.ANYXML]) &&
      stmt.mandatory === true
    ) {
      required.push(propertyKey(stmt, module));
    }
  }

  const rootXYang: Record<string, unknown> = {
    module: effectiveModule.name,
    "yang-version": effectiveModule.yangVersion ?? "1.1",
    namespace: effectiveModule.namespace,
    prefix: effectiveModule.prefix,
    organization: effectiveModule.organization ?? "",
    contact: effectiveModule.contact ?? ""
  };
  const rpcs: Record<string, unknown> = {};
  for (const stmt of effectiveModule.statements) {
    if (stmt.keyword === YangTokenType.RPC && stmt.name) {
      rpcs[stmt.name] = rpcToJson(stmt, effectiveModule, typedefNames);
    }
  }
  if (Object.keys(rpcs).length > 0) {
    rootXYang[XYANG_KEYS.rpcs] = rpcs;
  }

  const schema: Record<string, unknown> = {
    $schema: JSON_SCHEMA_DRAFT_2020_12,
    $id: effectiveModule.namespace ? effectiveModule.namespace : (effectiveModule.name ? `urn:${effectiveModule.name}` : "urn:module"),
    type: JSON_TYPE_OBJECT,
    properties,
    additionalProperties: false,
    [YANG_SCHEMA_KEYS.xYang]: rootXYang
  };
  withDescription(schema, effectiveModule.description);

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
