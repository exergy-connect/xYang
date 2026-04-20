import { YangModule, YangStatement } from "../core/model";
import { YangTokenType } from "../parser/parser-context";
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
    out.when = {
      condition: whenExpression,
      description: typeof whenShape.description === "string" ? whenShape.description : ""
    };
  }
  const must = mustToXYang(stmt);
  if (must.length > 0) {
    out.must = must;
  }
  return out;
}

function resolveAbsoluteLeafTypePath(module: YangModule, path: string): Record<string, unknown> | undefined {
  if (!path.startsWith("/")) {
    return undefined;
  }
  const segments = path.split("/").map((x) => x.trim()).filter(Boolean);
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
      if (!child.name) {
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

  if (keyword === YangTokenType.CONTAINER) {
    const properties: Record<string, unknown> = {};
    const required: string[] = [];
    const choices: YangStatement[] = [];

    for (const child of stmt.statements) {
      if (child.keyword === YangTokenType.CHOICE) {
        choices.push(child);
        continue;
      }
      if (!child.name) {
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

    const xYang = withStatementMeta(stmt, { type: keyword });
    const out: Record<string, unknown> = {
      type: JSON_TYPE_OBJECT,
      properties,
      additionalProperties: false,
      [YANG_SCHEMA_KEYS.xYang]: xYang
    };
    if (required.length > 0) {
      out.required = required;
    }

    for (const choice of choices) {
      const choiceShape = buildChoiceOneOf(choice, module, typedefNames);
      if (!choiceShape) {
        continue;
      }
      const xyangForChoice = {
        name: choice.name ?? "choice",
        description: typeof choice.data.description === "string" ? choice.data.description : "",
        mandatory: choice.data.mandatory === true,
        ...withStatementMeta(choice, {})
      };
      (out[YANG_SCHEMA_KEYS.xYang] as Record<string, unknown>).choice = xyangForChoice;
      if (Object.keys(properties).length === 0 && required.length === 0) {
        Object.assign(out, choiceShape);
      } else {
        out.allOf = [...((out.allOf as unknown[]) ?? []), choiceShape];
      }
    }

    return out;
  }

  if (keyword === YangTokenType.LIST) {
    const itemSchema: Record<string, unknown> = {
      type: JSON_TYPE_OBJECT,
      properties: {},
      additionalProperties: false
    };
    const itemRequired: string[] = [];
    const choices: YangStatement[] = [];
    for (const child of stmt.statements) {
      if (child.keyword === YangTokenType.CHOICE) {
        choices.push(child);
        continue;
      }
      if (!child.name) {
        continue;
      }
      (itemSchema.properties as Record<string, unknown>)[child.name] = statementToSchema(child, module, typedefNames);
      if (
        [YangTokenType.LEAF, YangTokenType.ANYDATA, YangTokenType.ANYXML].includes((child.keyword ?? "") as YangTokenType) &&
        child.data.mandatory === true
      ) {
        itemRequired.push(child.name);
      }
    }
    if (itemRequired.length > 0) {
      itemSchema.required = itemRequired;
    }
    for (const choice of choices) {
      const choiceShape = buildChoiceOneOf(choice, module, typedefNames);
      if (!choiceShape) {
        continue;
      }
      if (Object.keys(itemSchema.properties as Record<string, unknown>).length === 0 && itemRequired.length === 0) {
        Object.assign(itemSchema, choiceShape);
      } else {
        itemSchema.allOf = [...((itemSchema.allOf as unknown[]) ?? []), choiceShape];
      }
    }

    const out: Record<string, unknown> = {
      type: JSON_TYPE_ARRAY,
      items: itemSchema,
      [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(stmt, {
        type: keyword,
        key: typeof stmt.data.key === "string" ? stmt.data.key : undefined
      })
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
      [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(stmt, {
        type: keyword
      })
    };
    if (typeof stmt.data.description === "string" && stmt.data.description.length > 0) {
      out.description = stmt.data.description;
    }
    if (typeName === YangTokenType.LEAFREF) {
      const itemsXYang = asRecord(out.items);
      itemsXYang[YANG_SCHEMA_KEYS.xYang] = {
        type: YangTokenType.LEAFREF,
        path: typeShape.path,
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
      const path = pathText(typeShape.path);
      const targetType = path ? resolveAbsoluteLeafTypePath(module, path) : undefined;
      leafSchema = targetType ? leafTypeToSchema(targetType) : leafTypeToSchema({ name: YangTokenType.STRING_KW });
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

    const out: Record<string, unknown> = {
      ...leafSchema,
      [YANG_SCHEMA_KEYS.xYang]: xYang
    };
    if (typeof stmt.data.description === "string" && stmt.data.description.length > 0) {
      out.description = stmt.data.description;
    }
    if (stmt.data.default !== undefined) {
      out.default = stmt.data.default;
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
    if (typeof stmt.data.description === "string" && stmt.data.description.length > 0) {
      out.description = stmt.data.description;
    }
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
      ...schema
    };
    if (typeof entry.description === "string" && entry.description.length > 0) {
      def.description = entry.description;
    }
    const typedefXy: Record<string, unknown> = { type: "typedef" };
    if (typeof typeShape.pattern_error_message === "string") {
      typedefXy["pattern-error-message"] = typeShape.pattern_error_message;
    }
    if (typeof typeShape.pattern_error_app_tag === "string") {
      typedefXy["pattern-error-app-tag"] = typeShape.pattern_error_app_tag;
    }
    def[YANG_SCHEMA_KEYS.xYang] = typedefXy;
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
  const properties: Record<string, unknown> = {};
  const required: string[] = [];
  const typedefNames = new Set(Object.keys(module.typedefs as Record<string, unknown>));

  for (const stmt of module.statements) {
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
    properties[stmt.name] = statementToSchema(stmt, module, typedefNames);
    if (
      [YangTokenType.LEAF, YangTokenType.ANYDATA, YangTokenType.ANYXML].includes((stmt.keyword ?? "") as YangTokenType) &&
      stmt.data.mandatory === true
    ) {
      required.push(stmt.name);
    }
  }

  const schema: Record<string, unknown> = {
    $schema: JSON_SCHEMA_DRAFT_2020_12,
    $id: module.name ? `urn:yang:${module.name}` : "urn:yang:module",
    title: module.name ?? "yang-module",
    type: JSON_TYPE_OBJECT,
    properties,
    additionalProperties: false,
    [YANG_SCHEMA_KEYS.xYang]: {
      module: module.name,
      namespace: module.namespace,
      prefix: module.prefix
    }
  };

  if (required.length > 0) {
    schema.required = required;
  }
  const defs = {
    ...typedefToSchema(module),
    ...identityToSchema(module)
  };
  if (Object.keys(defs).length > 0) {
    schema.$defs = defs;
  }

  return schema;
}
