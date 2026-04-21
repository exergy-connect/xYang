import { YangModule, type ModuleSource, type SerializedStatement } from "../core/model";
import { YangTokenType } from "../parser/parser-context";
import { parseXPath } from "../xpath/parser";
import { YANG_SCHEMA_KEYS } from "./schema-keys";
import {
  decimal64FractionDigitsFromSchema,
  JSON_TYPE_ARRAY,
  JSON_TYPE_OBJECT,
  JSON_TYPE_STRING,
  schemaTypeToYangType
} from "./type-constants";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function resolveSchema(schema: Record<string, unknown>, defs: Record<string, unknown>): Record<string, unknown> {
  const ref = schema.$ref;
  if (typeof ref === "string" && ref.startsWith("#/$defs/")) {
    const name = ref.slice("#/$defs/".length);
    const d = defs[name];
    if (d && typeof d === "object") {
      return resolveSchema(d as Record<string, unknown>, defs);
    }
  }
  return schema;
}

function resolveSchemaWithOverlay(schema: Record<string, unknown>, defs: Record<string, unknown>): Record<string, unknown> {
  const base = resolveSchema(schema, defs);
  const baseXy = asRecord(base[YANG_SCHEMA_KEYS.xYang]);
  const overlayXy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
  return {
    ...base,
    ...schema,
    [YANG_SCHEMA_KEYS.xYang]: { ...baseXy, ...overlayXy }
  };
}

function refToTypedefName(ref: unknown): string | undefined {
  if (typeof ref !== "string" || !ref.startsWith("#/$defs/")) {
    return undefined;
  }
  const name = ref.slice("#/$defs/".length);
  return name.trim().length > 0 ? name : undefined;
}

function whenFromXyang(xy: Record<string, unknown>): SerializedStatement["when"] | undefined {
  const w = xy.when;
  if (!w || typeof w !== "object") {
    return undefined;
  }
  const o = asRecord(w);
  const expression = typeof o.condition === "string" ? o.condition : "";
  if (!expression.trim()) {
    return undefined;
  }
  return {
    expression,
    description: typeof o.description === "string" ? o.description : "",
    evaluate_with_parent_context: Boolean(o.evaluate_with_parent_context)
  };
}

function mustStatementsFromXyang(xy: Record<string, unknown>): SerializedStatement[] {
  const raw = xy.must;
  if (!Array.isArray(raw)) {
    return [];
  }
  const out: SerializedStatement[] = [];
  for (const item of raw) {
    const e = asRecord(item);
    const expr = typeof e.must === "string" ? e.must : "";
    if (!expr.trim()) {
      continue;
    }
    out.push({
      __class__: "YangStatement",
      keyword: "must",
      name: expr,
      argument: expr,
      error_message: typeof e["error-message"] === "string" ? e["error-message"] : "",
      statements: []
    });
  }
  return out;
}

function typeShapeFromJsonLeaf(schema: Record<string, unknown>, xy: Record<string, unknown>): Record<string, unknown> {
  if (xy.type === YangTokenType.LEAFREF) {
    const path = typeof xy.path === "string" ? xy.path : "";
    if (path) {
      // Validate path syntax early for parity with YANG parsing behavior.
      parseXPath(path);
    }
    return {
      name: YangTokenType.LEAFREF,
      path,
      require_instance: xy["require-instance"] !== false
    };
  }
  if (xy.type === YangTokenType.INSTANCE_IDENTIFIER) {
    return {
      name: YangTokenType.INSTANCE_IDENTIFIER,
      require_instance: xy["require-instance"] !== false
    };
  }
  if (xy.type === YangTokenType.IDENTITYREF) {
    const bases = Array.isArray(xy.bases) ? xy.bases.filter((x): x is string => typeof x === "string") : [];
    return { name: YangTokenType.IDENTITYREF, identityref_bases: bases };
  }
  const typedefRef = refToTypedefName(schema.$ref);
  if (typedefRef) {
    return { name: typedefRef };
  }
  if (schema.type === JSON_TYPE_OBJECT && schema.maxProperties === 0) {
    return { name: YangTokenType.EMPTY };
  }
  const hasStringEnum = schema.type === JSON_TYPE_STRING && Array.isArray(schema.enum);
  const name = hasStringEnum ? YangTokenType.ENUMERATION : schemaTypeToYangType(schema);
  const shape: Record<string, unknown> = { name };
  if (name === YangTokenType.DECIMAL64) {
    const fd = decimal64FractionDigitsFromSchema(schema);
    if (typeof fd === "number") {
      shape.fraction_digits = fd;
    }
  }
  if (typeof schema.minLength === "number" || typeof schema.maxLength === "number") {
    const min = typeof schema.minLength === "number" ? `${schema.minLength}` : "min";
    const max = typeof schema.maxLength === "number" ? `${schema.maxLength}` : "max";
    shape.length = `${min}..${max}`;
  }
  if (typeof schema.minimum === "number" || typeof schema.maximum === "number") {
    const minNum = typeof schema.minimum === "number" ? schema.minimum : undefined;
    const maxNum = typeof schema.maximum === "number" ? schema.maximum : undefined;
    const decimalContext =
      (minNum !== undefined && !Number.isInteger(minNum)) ||
      (maxNum !== undefined && !Number.isInteger(maxNum));
    const fmt = (n: number): string => {
      if (decimalContext && Number.isInteger(n)) {
        return `${n}.0`;
      }
      return `${n}`;
    };
    // Avoid redundant explicit range for full-width uint8.
    if (!(name === YangTokenType.UINT8 && minNum === 0 && maxNum === 255)) {
      const min = minNum !== undefined ? fmt(minNum) : "min";
      const max = maxNum !== undefined ? fmt(maxNum) : "max";
      shape.range = `${min}..${max}`;
    }
  }
  if (name === YangTokenType.STRING_KW && typeof schema.pattern === "string") {
    let p = schema.pattern;
    if (p.startsWith("^") && p.endsWith("$")) {
      p = p.slice(1, -1);
    }
    shape.pattern = p;
  }
  const pem = xy["pattern-error-message"];
  if (typeof pem === "string" && pem.length > 0) {
    shape.pattern_error_message = pem;
  }
  const pet = xy["pattern-error-app-tag"];
  if (typeof pet === "string" && pet.length > 0) {
    shape.pattern_error_app_tag = pet;
  }
  const unionItems = Array.isArray(schema.oneOf)
    ? schema.oneOf
    : (Array.isArray(schema.anyOf) ? schema.anyOf : []);
  if (unionItems.length > 0) {
    const types = unionItems
      .filter((entry): entry is Record<string, unknown> => Boolean(entry) && typeof entry === "object" && !Array.isArray(entry))
      .map((entry) => typeShapeFromJsonLeaf(entry, asRecord(entry[YANG_SCHEMA_KEYS.xYang])));
    if (types.length > 0) {
      return { name: YangTokenType.UNION, types };
    }
  }
  if (hasStringEnum) {
    const enumValues = Array.isArray(schema.enum) ? schema.enum : [];
    shape.enums = enumValues.filter((x): x is string => typeof x === "string");
  }
  return shape;
}

function parseLeaf(name: string, schema: Record<string, unknown>, defs: Record<string, unknown>): SerializedStatement {
  const resolved = resolveSchemaWithOverlay(schema, defs);
  const xy = asRecord(resolved[YANG_SCHEMA_KEYS.xYang]);
  const typeShape = typeShapeFromJsonLeaf(resolved, xy);
  const musts = mustStatementsFromXyang(xy);
  const when = whenFromXyang(xy);
  const out: SerializedStatement = {
    __class__: "YangStatement",
    keyword: YangTokenType.LEAF,
    name,
    argument: name,
    type: typeShape,
    statements: musts
  };
  if (xy.mandatory === true) {
    out.mandatory = true;
  }
  if (typeof resolved.description === "string" && resolved.description.length > 0) {
    out.description = resolved.description;
  }
  if (resolved.default !== undefined) {
    out.default = resolved.default;
  }
  if (when) {
    out.when = when;
  }
  if (Array.isArray(xy["if-features"])) {
    const feats = (xy["if-features"] as unknown[]).filter((x): x is string => typeof x === "string" && x.trim().length > 0);
    if (feats.length > 0) {
      out.if_features = feats;
    }
  }
  return out;
}

function extractChoiceBranches(schema: Record<string, unknown>): Record<string, unknown>[] {
  const branches: Record<string, unknown>[] = [];
  if (Array.isArray(schema.oneOf)) {
    for (const item of schema.oneOf) {
      if (item && typeof item === "object" && !Array.isArray(item)) {
        branches.push(item as Record<string, unknown>);
      }
    }
  }
  if (Array.isArray(schema.allOf)) {
    for (const entry of schema.allOf) {
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
        continue;
      }
      const obj = entry as Record<string, unknown>;
      if (!Array.isArray(obj.oneOf)) {
        continue;
      }
      // Hoisted choice fragments are plain `{ oneOf: [...] }`.
      if (Object.keys(obj).some((k) => k !== "oneOf")) {
        continue;
      }
      for (const item of obj.oneOf) {
        if (item && typeof item === "object" && !Array.isArray(item)) {
          branches.push(item as Record<string, unknown>);
        }
      }
    }
  }
  return branches;
}

function splitChoiceCommonProperties(branches: Record<string, unknown>[]): {
  commonProps: Record<string, Record<string, unknown>>;
  strippedBranches: Record<string, unknown>[];
} {
  const input = Array.isArray(branches) ? branches : [];
  const nonEmpty = input.filter(
    (b) => !(b.type === JSON_TYPE_OBJECT && b.maxProperties === 0)
  );
  if (nonEmpty.length === 0) {
    return { commonProps: {}, strippedBranches: input };
  }

  const propMaps = nonEmpty.map((b) => asRecord(b.properties));
  const keySets = propMaps.map((p) => new Set(Object.keys(p)));
  const intersection = new Set<string>(keySets[0]);
  for (let i = 1; i < keySets.length; i += 1) {
    for (const k of [...intersection]) {
      if (!keySets[i].has(k)) {
        intersection.delete(k);
      }
    }
  }

  const commonProps: Record<string, Record<string, unknown>> = {};
  for (const key of intersection) {
    const first = propMaps[0][key];
    if (!first || typeof first !== "object" || Array.isArray(first)) {
      continue;
    }
    const firstJson = JSON.stringify(first);
    const sameAcross = propMaps.every((p) => JSON.stringify(p[key]) === firstJson);
    if (sameAcross) {
      commonProps[key] = first as Record<string, unknown>;
    }
  }

  if (Object.keys(commonProps).length === 0) {
    return { commonProps, strippedBranches: input };
  }

  const strippedBranches = input.map((b) => {
    const props = asRecord(b.properties);
    const nextProps: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(props)) {
      if (!(k in commonProps)) {
        nextProps[k] = v;
      }
    }
    const next: Record<string, unknown> = { ...b, properties: nextProps };
    if (Array.isArray(b.required)) {
      next.required = b.required.filter((x): x is string => typeof x === "string" && !(x in commonProps));
    }
    return next;
  });

  return { commonProps, strippedBranches };
}

function parseChoice(name: string, schema: Record<string, unknown>, defs: Record<string, unknown>): SerializedStatement {
  const xy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
  const choiceName = typeof xy.name === "string" && xy.name.length > 0 ? xy.name : name;
  const choiceStmt: SerializedStatement = {
    __class__: "YangStatement",
    keyword: YangTokenType.CHOICE,
    name: choiceName,
    argument: choiceName,
    mandatory: xy.mandatory === true,
    statements: []
  };
  if (Array.isArray(xy["if-features"])) {
    const feats = (xy["if-features"] as unknown[]).filter((x): x is string => typeof x === "string" && x.trim().length > 0);
    if (feats.length > 0) {
      choiceStmt.if_features = feats;
    }
  }
  if (typeof xy.description === "string" && xy.description.length > 0) {
    choiceStmt.description = xy.description;
  } else if (typeof schema.description === "string" && schema.description.length > 0) {
    choiceStmt.description = schema.description;
  }

  let caseIndex = 0;
  for (const branchRaw of extractChoiceBranches(schema)) {
    const branch = asRecord(branchRaw);
    if (branch.type === JSON_TYPE_OBJECT && branch.maxProperties === 0) {
      continue;
    }
    caseIndex += 1;
    const branchXy = asRecord(branch[YANG_SCHEMA_KEYS.xYang]);
    const caseName = typeof branchXy.name === "string" && branchXy.name.length > 0 ? branchXy.name : `case-${caseIndex}`;
    const caseStmt: SerializedStatement = {
      __class__: "YangStatement",
      keyword: YangTokenType.CASE,
      name: caseName,
      argument: caseName,
      statements: []
    };
    if (Array.isArray(branchXy["if-features"])) {
      const feats = (branchXy["if-features"] as unknown[]).filter(
        (x): x is string => typeof x === "string" && x.trim().length > 0
      );
      if (feats.length > 0) {
        caseStmt.if_features = feats;
      }
    }
    if (typeof branchXy.description === "string" && branchXy.description.length > 0) {
      caseStmt.description = branchXy.description;
    } else if (typeof branch.description === "string" && branch.description.length > 0) {
      caseStmt.description = branch.description;
    }

    const branchProps = asRecord(branch.properties);
    for (const [childName, childSchema] of Object.entries(branchProps)) {
      if (!childSchema || typeof childSchema !== "object") {
        continue;
      }
      const childStmt = jsonSchemaPropertyToStatement(childName, childSchema as Record<string, unknown>, defs);
      if (!childStmt) {
        continue;
      }
      (caseStmt.statements as SerializedStatement[]).push(childStmt);
    }
    if ((caseStmt.statements as SerializedStatement[]).length > 0) {
      (choiceStmt.statements as SerializedStatement[]).push(caseStmt);
    }
  }
  return choiceStmt;
}

function parseAnydataOrAnyxml(name: string, schema: Record<string, unknown>, keyword: string): SerializedStatement {
  const xy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
  const musts = mustStatementsFromXyang(xy);
  const when = whenFromXyang(xy);
  const out: SerializedStatement = {
    __class__: "YangStatement",
    keyword,
    name,
    argument: name,
    statements: musts
  };
  if (xy.mandatory === true) {
    out.mandatory = true;
  }
  if (typeof schema.description === "string" && schema.description.length > 0) {
    out.description = schema.description;
  }
  if (when) {
    out.when = when;
  }
  return out;
}

function parseContainer(name: string, schema: Record<string, unknown>, defs: Record<string, unknown>): SerializedStatement {
  const xy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
  const props = asRecord(schema.properties);
  const musts = mustStatementsFromXyang(xy);
  const when = whenFromXyang(xy);
  const children: SerializedStatement[] = [...musts];
  for (const [childName, childSchema] of Object.entries(props)) {
    if (!childSchema || typeof childSchema !== "object") {
      continue;
    }
    const stmt = jsonSchemaPropertyToStatement(childName, childSchema as Record<string, unknown>, defs);
    if (stmt) {
      children.push(stmt);
    }
  }
  const hasExplicitChoiceChildren = children.some((s) => s.keyword === YangTokenType.CHOICE);
  const out: SerializedStatement = {
    __class__: "YangStatement",
    keyword: YangTokenType.CONTAINER,
    name,
    argument: name,
    statements: children
  };
  const reqList = Array.isArray(schema.required)
    ? schema.required.filter((x): x is string => typeof x === "string")
    : [];
  for (const ch of children) {
    if (typeof ch.name === "string" && reqList.includes(ch.name)) {
      ch.mandatory = true;
    }
  }
  if (typeof xy.presence === "string" && xy.presence.length > 0) {
    out.presence = xy.presence;
  }
  if (typeof schema.description === "string" && schema.description.length > 0) {
    out.description = schema.description;
  }
  if (when) {
    out.when = when;
  }
  const choice = xy.choice;
  if (!hasExplicitChoiceChildren && choice && typeof choice === "object") {
    const ch = asRecord(choice);
    const branches = extractChoiceBranches(schema);
    const { commonProps, strippedBranches } = splitChoiceCommonProperties(branches);
    for (const [commonName, commonSchema] of Object.entries(commonProps)) {
      const commonStmt = jsonSchemaPropertyToStatement(commonName, commonSchema, defs);
      if (commonStmt) {
        children.push(commonStmt);
      }
    }
    const choiceSchema: Record<string, unknown> = {
      type: JSON_TYPE_OBJECT,
      oneOf: strippedBranches,
      [YANG_SCHEMA_KEYS.xYang]: {
        name: typeof ch.name === "string" && ch.name.length > 0 ? ch.name : "choice",
        mandatory: ch.mandatory === true,
        ...(Array.isArray(ch["if-features"]) ? { "if-features": ch["if-features"] } : {}),
        ...(typeof ch.description === "string" && ch.description.length > 0 ? { description: ch.description } : {})
      }
    };
    const choiceStmt = parseChoice(
      (choiceSchema[YANG_SCHEMA_KEYS.xYang] as Record<string, unknown>).name as string,
      choiceSchema,
      defs
    );
    if ((choiceStmt.statements as SerializedStatement[]).length > 0) {
      children.push(choiceStmt);
    }
  }
  if (Array.isArray(schema.allOf)) {
    (out as Record<string, unknown>).allOf = schema.allOf;
  }
  return out;
}

function parseList(name: string, schema: Record<string, unknown>, defs: Record<string, unknown>): SerializedStatement {
  const xy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
  const items = asRecord(schema.items as Record<string, unknown>);
  const resolvedItems = resolveSchema(items, defs);
  const itemProps = asRecord(resolvedItems.properties);
  const musts = mustStatementsFromXyang(xy);
  const when = whenFromXyang(xy);
  const children: SerializedStatement[] = [...musts];
  for (const [childName, childSchema] of Object.entries(itemProps)) {
    if (!childSchema || typeof childSchema !== "object") {
      continue;
    }
    const stmt = jsonSchemaPropertyToStatement(childName, childSchema as Record<string, unknown>, defs);
    if (stmt) {
      children.push(stmt);
    }
  }
  const out: SerializedStatement = {
    __class__: "YangStatement",
    keyword: YangTokenType.LIST,
    name,
    argument: name,
    statements: children,
    key: typeof xy.key === "string" ? xy.key : undefined,
    min_elements:
      typeof schema.minItems === "number"
        ? (schema.minItems as number)
        : (typeof xy["min-elements"] === "number" ? (xy["min-elements"] as number) : undefined),
    max_elements:
      typeof schema.maxItems === "number"
        ? (schema.maxItems as number)
        : (typeof xy["max-elements"] === "number" ? (xy["max-elements"] as number) : undefined)
  };
  const itemReq = Array.isArray(resolvedItems.required)
    ? resolvedItems.required.filter((x): x is string => typeof x === "string")
    : [];
  for (const ch of children) {
    if (typeof ch.name === "string" && itemReq.includes(ch.name)) {
      ch.mandatory = true;
    }
  }
  const itemXy = asRecord(resolvedItems[YANG_SCHEMA_KEYS.xYang]);
  const itemChoice = itemXy.choice;
  if (itemChoice && typeof itemChoice === "object") {
    const ch = asRecord(itemChoice);
    const branches = extractChoiceBranches(resolvedItems);
    const { commonProps, strippedBranches } = splitChoiceCommonProperties(branches);
    for (const [commonName, commonSchema] of Object.entries(commonProps)) {
      const commonStmt = jsonSchemaPropertyToStatement(commonName, commonSchema, defs);
      if (commonStmt) {
        children.push(commonStmt);
      }
    }
    const choiceSchema: Record<string, unknown> = {
      type: JSON_TYPE_OBJECT,
      oneOf: strippedBranches,
      [YANG_SCHEMA_KEYS.xYang]: {
        name: typeof ch.name === "string" && ch.name.length > 0 ? ch.name : "choice",
        mandatory: ch.mandatory === true,
        ...(Array.isArray(ch["if-features"]) ? { "if-features": ch["if-features"] } : {}),
        ...(typeof ch.description === "string" && ch.description.length > 0 ? { description: ch.description } : {})
      }
    };
    const choiceStmt = parseChoice(
      (choiceSchema[YANG_SCHEMA_KEYS.xYang] as Record<string, unknown>).name as string,
      choiceSchema,
      defs
    );
    if ((choiceStmt.statements as SerializedStatement[]).length > 0) {
      children.push(choiceStmt);
    }
  }
  if (typeof schema.description === "string" && schema.description.length > 0) {
    out.description = schema.description;
  }
  if (when) {
    out.when = when;
  }
  return out;
}

function parseLeafList(name: string, schema: Record<string, unknown>, defs: Record<string, unknown>): SerializedStatement {
  const xy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
  const items = resolveSchema(asRecord(schema.items), defs);
  const itemXy = asRecord(items[YANG_SCHEMA_KEYS.xYang]);
  const mergedXy = { ...xy, ...itemXy };
  const typeShape = typeShapeFromJsonLeaf(items, mergedXy);
  const out: SerializedStatement = {
    __class__: "YangStatement",
    keyword: YangTokenType.LEAF_LIST,
    name,
    argument: name,
    type: typeShape,
    statements: mustStatementsFromXyang(xy)
  };
  if (typeof schema.minItems === "number") {
    out.min_elements = schema.minItems as number;
  } else if (typeof xy["min-elements"] === "number") {
    out.min_elements = xy["min-elements"] as number;
  }
  if (typeof schema.maxItems === "number") {
    out.max_elements = schema.maxItems as number;
  } else if (typeof xy["max-elements"] === "number") {
    out.max_elements = xy["max-elements"] as number;
  }
  if (typeof schema.description === "string" && schema.description.length > 0) {
    out.description = schema.description;
  }
  if (schema.default !== undefined) {
    if (Array.isArray(schema.default)) {
      out.defaults = schema.default.filter((x) => x !== undefined);
    } else {
      out.defaults = [schema.default];
    }
  }
  return out;
}

function jsonSchemaPropertyToStatement(
  name: string,
  schema: Record<string, unknown>,
  defs: Record<string, unknown>
): SerializedStatement | null {
  const resolved = resolveSchemaWithOverlay(schema, defs);
  const xy = asRecord(resolved[YANG_SCHEMA_KEYS.xYang]);
  const xyType = typeof xy.type === "string" ? xy.type : "";

  if (xyType === YangTokenType.CONTAINER && resolved.type === JSON_TYPE_OBJECT) {
    return parseContainer(name, resolved, defs);
  }
  if (xyType === YangTokenType.LIST && resolved.type === JSON_TYPE_ARRAY) {
    return parseList(name, resolved, defs);
  }
  if (xyType === YangTokenType.LEAF_LIST && resolved.type === JSON_TYPE_ARRAY) {
    return parseLeafList(name, resolved, defs);
  }
  if (xyType === YangTokenType.CHOICE) {
    return parseChoice(name, resolved, defs);
  }
  if (xyType === YangTokenType.LEAF) {
    return parseLeaf(name, resolved, defs);
  }
  if (
    xyType === YangTokenType.LEAFREF ||
    xyType === YangTokenType.IDENTITYREF ||
    xyType === YangTokenType.INSTANCE_IDENTIFIER
  ) {
    return parseLeaf(name, resolved, defs);
  }
  if (xyType === YangTokenType.ANYDATA) {
    return parseAnydataOrAnyxml(name, resolved, YangTokenType.ANYDATA);
  }
  if (xyType === YangTokenType.ANYXML) {
    return parseAnydataOrAnyxml(name, resolved, YangTokenType.ANYXML);
  }

  if (resolved.type === JSON_TYPE_OBJECT && Object.keys(xy).length > 0) {
    return parseContainer(name, resolved, defs);
  }

  return null;
}

/**
 * Build a {@link YangModule} (serialized AST in `module.data`) from JSON Schema with `x-yang` annotations,
 * as produced by {@link generateJsonSchema}. Covers common data nodes used in tests; extend as needed for parity.
 */
export function parseJsonSchema(source: string | Record<string, unknown>): YangModule {
  const root: Record<string, unknown> =
    typeof source === "string" ? (JSON.parse(source) as Record<string, unknown>) : { ...source };

  const rootXy = asRecord(root[YANG_SCHEMA_KEYS.xYang]);
  const moduleName = typeof rootXy.module === "string" ? rootXy.module : (typeof root.title === "string" ? root.title : "");
  const namespace = typeof rootXy.namespace === "string" ? rootXy.namespace : "";
  const prefix = typeof rootXy.prefix === "string" ? rootXy.prefix : "";

  const defsRaw = root.$defs;
  const defs = defsRaw && typeof defsRaw === "object" && !Array.isArray(defsRaw) ? (defsRaw as Record<string, unknown>) : {};

  const properties = asRecord(root.properties);
  const statements: SerializedStatement[] = [];
  for (const [propName, propSchema] of Object.entries(properties)) {
    if (!propSchema || typeof propSchema !== "object") {
      continue;
    }
    const stmt = jsonSchemaPropertyToStatement(propName, propSchema as Record<string, unknown>, defs);
    if (stmt) {
      statements.push(stmt);
    }
  }
  const rootRequired = Array.isArray(root.required) ? root.required.filter((x): x is string => typeof x === "string") : [];
  for (const stmt of statements) {
    if (typeof stmt.name === "string" && rootRequired.includes(stmt.name)) {
      stmt.mandatory = true;
    }
  }

  const typedefs: Record<string, unknown> = {};
  const identities: Record<string, { bases: string[] }> = {};
  for (const [defName, defSchema] of Object.entries(defs)) {
    if (!defSchema || typeof defSchema !== "object") {
      continue;
    }
    const d = defSchema as Record<string, unknown>;
    const dxy = asRecord(d[YANG_SCHEMA_KEYS.xYang]);
    if (dxy.type === YangTokenType.IDENTITY) {
      const bases = Array.isArray(dxy.bases) ? dxy.bases.filter((x): x is string => typeof x === "string") : [];
      identities[defName] = { bases };
      continue;
    }
    // Legacy schemas may omit x-yang typedef metadata in $defs.
    typedefs[defName] = {
      name: defName,
      type: typeShapeFromJsonLeaf(d, dxy),
      statements: []
    };
  }

  const data: Record<string, unknown> = {
    __class__: "YangModule",
    name: moduleName,
    yang_version: "1.1",
    namespace,
    prefix,
    typedefs,
    identities,
    import_prefixes: {},
    extensions: {},
    extension_runtime: {},
    statements
  };

  const modSource: ModuleSource = { kind: "string", value: typeof source === "string" ? source : JSON.stringify(source), name: "<json-schema>" };
  return new YangModule(data, modSource);
}
