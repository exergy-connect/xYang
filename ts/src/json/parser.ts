import { coerceIdentifierRef, type YangIdentifierRef } from "../core/identifier-ref";
import { YangModule, YangStatement, type ModuleInit, type ModuleSource } from "../core/model";
import { YangTokenType } from "../parser/parser-context";
import { parseXPath, parseXPathPath, xpathPrefixes } from "../xpath/parser";
import { YangSyntaxError } from "../core/errors";
import { yangDefaultFromJsonSchema } from "./default-values";
import {
  decimal64FractionDigitsFromSchema,
  isStringNumberBuiltin,
  quotedNumericTypeShape,
  schemaTypeToYangType,
  yangIntegerFromJsonBounds
} from "../types/registry";
import { XYANG_KEYS, YANG_SCHEMA_KEYS } from "./schema-keys";
import {
  JSON_TYPE_ARRAY,
  JSON_TYPE_INTEGER,
  JSON_TYPE_OBJECT,
  JSON_TYPE_STRING
} from "./type-constants";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function basesFromJson(raw: unknown): YangIdentifierRef[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .map((b) => coerceIdentifierRef(b))
    .filter((b): b is YangIdentifierRef => Boolean(b));
}

function setConfigFromXyang(stmt: YangStatement, xyang: Record<string, unknown>): void {
  if (XYANG_KEYS.config in xyang && typeof xyang[XYANG_KEYS.config] === "boolean") {
    stmt.config = xyang[XYANG_KEYS.config] as boolean;
  }
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

/** Missing ``description`` is an empty string (generators omit the key when unset). */
function descriptionOrEmpty(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function firstNonEmptyDescription(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === "string" && value.length > 0) {
      return value;
    }
  }
  return "";
}

/** A recorded `xpath-prefixes` map, validated; anything else is a load error. */
function recordedPrefixes(raw: unknown): Record<string, string> | undefined {
  if (raw === undefined) {
    return undefined;
  }
  if (!raw || typeof raw !== "object" || Array.isArray(raw) || !Object.values(raw).every((v) => typeof v === "string")) {
    throw new Error(`"${XYANG_KEYS.xpathPrefixes}" must map prefixes to module names, got ${JSON.stringify(raw)}`);
  }
  return { ...(raw as Record<string, string>) };
}

/**
 * A `must`, `when` or leafref `path` without a recorded `xpath-prefixes` map may only use the
 * module's own prefix (the JSON form has no imports). Record that binding, or fail the load.
 */
function ownPrefixBinding(expression: string, isPath: boolean, moduleName: string, ownPrefix: string): Record<string, string> | undefined {
  const used = xpathPrefixes(isPath ? parseXPathPath(expression) : parseXPath(expression));
  if (used.size === 0) {
    return undefined;
  }
  const recorded: Record<string, string> = {};
  for (const prefix of used) {
    if (prefix !== ownPrefix) {
      throw new YangSyntaxError(`xpath: unknown prefix '${prefix}' in '${expression}'`);
    }
    recorded[prefix] = moduleName;
  }
  return recorded;
}

function bindUnrecordedPrefixes(statements: YangStatement[], moduleName: string, ownPrefix: string): void {
  for (const stmt of statements) {
    if (stmt.keyword === "must" && typeof stmt.argument === "string" && !stmt.xpath_prefixes) {
      const recorded = ownPrefixBinding(stmt.argument, false, moduleName, ownPrefix);
      if (recorded) stmt.xpath_prefixes = recorded;
    }
    const when = stmt.when;
    if (when && typeof when.expression === "string" && !when.xpath_prefixes) {
      const recorded = ownPrefixBinding(when.expression, false, moduleName, ownPrefix);
      if (recorded) when.xpath_prefixes = recorded;
    }
    const type = stmt.type;
    if (type && type.name === YangTokenType.LEAFREF && typeof type.path === "string" && type.path && !type.xpath_prefixes) {
      const recorded = ownPrefixBinding(type.path, true, moduleName, ownPrefix);
      if (recorded) type.xpath_prefixes = recorded;
    }
    bindUnrecordedPrefixes(stmt.statements, moduleName, ownPrefix);
  }
}

function whenFromXyang(xy: Record<string, unknown>): YangStatement["when"] | undefined {
  const w = xy.when;
  if (!w || typeof w !== "object") {
    return undefined;
  }
  const o = asRecord(w);
  const expression = typeof o.condition === "string" ? o.condition : "";
  if (!expression.trim()) {
    return undefined;
  }
  const prefixes = recordedPrefixes(o[XYANG_KEYS.xpathPrefixes]);
  return {
    expression,
    description: typeof o.description === "string" ? o.description : "",
    evaluate_with_parent_context: Boolean(o.evaluate_with_parent_context),
    ...(prefixes ? { xpath_prefixes: prefixes } : {})
  };
}

function mustStatementsFromXyang(xy: Record<string, unknown>): YangStatement[] {
  const raw = xy.must;
  if (!Array.isArray(raw)) {
    return [];
  }
  const out: YangStatement[] = [];
  for (const item of raw) {
    const e = asRecord(item);
    const expr = typeof e.must === "string" ? e.must : "";
    if (!expr.trim()) {
      continue;
    }
    out.push(new YangStatement({
      keyword: "must",
      name: expr,
      argument: expr,
      error_message: typeof e["error-message"] === "string" ? e["error-message"] : "",
      description: typeof e.description === "string" ? e.description : "",
      ...(e[XYANG_KEYS.xpathPrefixes] !== undefined ? { xpath_prefixes: recordedPrefixes(e[XYANG_KEYS.xpathPrefixes]) } : {}),
      statements: []
    }));
  }
  return out;
}

function applyStatementMetaFromXyang(stmt: YangStatement, xy: Record<string, unknown>): void {
  const when = whenFromXyang(xy);
  if (when) {
    stmt.when = when;
  }
  setConfigFromXyang(stmt, xy);
  if (Array.isArray(xy["if-features"])) {
    stmt.if_features = xy["if-features"].filter((x): x is string => typeof x === "string");
  }
}

function typeShapeFromJsonLeaf(schema: Record<string, unknown>, xy: Record<string, unknown>): Record<string, unknown> {
  if (schema.type === JSON_TYPE_STRING) {
    const quoted = quotedNumericTypeShape(xy);
    if (quoted) {
      return quoted;
    }
  }
  if (xy.type === YangTokenType.LEAFREF) {
    const path = typeof xy.path === "string" ? xy.path : "";
    if (path) {
      // Validate path syntax early for parity with YANG parsing behavior.
      parseXPathPath(path);
    }
    const prefixes = recordedPrefixes(xy[XYANG_KEYS.xpathPrefixes]);
    return {
      name: YangTokenType.LEAFREF,
      path,
      ...(prefixes ? { xpath_prefixes: prefixes } : {}),
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
    return { name: YangTokenType.IDENTITYREF, identityref_bases: basesFromJson(xy.bases) };
  }
  const typedefRef = refToTypedefName(schema.$ref);
  if (typedefRef) {
    return { name: typedefRef };
  }
  if (schema.type === JSON_TYPE_OBJECT && schema.maxProperties === 0) {
    return { name: YangTokenType.EMPTY };
  }
  const hasStringEnum = schema.type === JSON_TYPE_STRING && Array.isArray(schema.enum);
  const shape: Record<string, unknown> = {};
  if (schema.type === JSON_TYPE_INTEGER) {
    const inferred = yangIntegerFromJsonBounds(schema.minimum, schema.maximum);
    shape.name = inferred.name;
    if (inferred.range) {
      shape.range = inferred.range;
    }
  } else {
    shape.name = hasStringEnum ? YangTokenType.ENUMERATION : schemaTypeToYangType(schema);
  }
  const name = shape.name as string;
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
  if (schema.type !== JSON_TYPE_INTEGER && (typeof schema.minimum === "number" || typeof schema.maximum === "number")) {
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
    const min = minNum !== undefined ? fmt(minNum) : "min";
    const max = maxNum !== undefined ? fmt(maxNum) : "max";
    shape.range = `${min}..${max}`;
  }
  const rawPatternEntries = Array.isArray(xy["string-patterns"]) ? xy["string-patterns"] : [];
  const parsedPatternEntries = rawPatternEntries
    .filter((x): x is Record<string, unknown> => Boolean(x) && typeof x === "object" && !Array.isArray(x))
    .map((x) => ({
      pattern: typeof x.pattern === "string" ? x.pattern : "",
      invert_match: x["invert-match"] === true,
      error_message:
        typeof x["pattern-error-message"] === "string" ? (x["pattern-error-message"] as string) : undefined,
      error_app_tag:
        typeof x["pattern-error-app-tag"] === "string" ? (x["pattern-error-app-tag"] as string) : undefined
    }))
    .filter((x) => x.pattern.length > 0);

  type PatternShape = {
    pattern: string;
    invert_match: boolean;
    error_message?: string;
    error_app_tag?: string;
  };

  let patternList: PatternShape[] = [];
  if (parsedPatternEntries.length > 0) {
    patternList = parsedPatternEntries;
  } else if (Array.isArray(schema.allOf)) {
    const fallbackEntries = schema.allOf
      .filter((x): x is Record<string, unknown> => Boolean(x) && typeof x === "object" && !Array.isArray(x))
      .map((entry) => {
        if (typeof entry.pattern === "string") {
          return { pattern: entry.pattern, invert_match: false };
        }
        const notObj = asRecord(entry.not);
        if (typeof notObj.pattern === "string") {
          return { pattern: notObj.pattern, invert_match: true };
        }
        return null;
      })
      .filter((x): x is { pattern: string; invert_match: boolean } => Boolean(x))
      .map((x) => {
        const p = x.pattern.startsWith("^") && x.pattern.endsWith("$")
          ? x.pattern.slice(1, -1)
          : x.pattern;
        return { pattern: p, invert_match: x.invert_match };
      });
    if (fallbackEntries.length > 0) {
      patternList = fallbackEntries;
    }
  } else if (name === YangTokenType.STRING_KW && typeof schema.pattern === "string") {
    let p = schema.pattern;
    if (p.startsWith("^") && p.endsWith("$")) {
      p = p.slice(1, -1);
    }
    patternList = [{ pattern: p, invert_match: false }];
  }

  const pem = typeof xy["pattern-error-message"] === "string" && xy["pattern-error-message"].length > 0
    ? (xy["pattern-error-message"] as string)
    : undefined;
  const pet = typeof xy["pattern-error-app-tag"] === "string" && xy["pattern-error-app-tag"].length > 0
    ? (xy["pattern-error-app-tag"] as string)
    : undefined;
  if (patternList.length > 0) {
    const last = patternList[patternList.length - 1];
    if (pem !== undefined && last.error_message === undefined) {
      last.error_message = pem;
    }
    if (pet !== undefined && last.error_app_tag === undefined) {
      last.error_app_tag = pet;
    }
    shape.patterns = patternList;
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

function parseLeaf(name: string, schema: Record<string, unknown>, defs: Record<string, unknown>): YangStatement {
  const resolved = resolveSchemaWithOverlay(schema, defs);
  const xy = asRecord(resolved[YANG_SCHEMA_KEYS.xYang]);
  const typeShape = typeShapeFromJsonLeaf(resolved, xy);
  const musts = mustStatementsFromXyang(xy);
  const when = whenFromXyang(xy);
  const out: YangStatement = new YangStatement({
    keyword: YangTokenType.LEAF,
    name,
    argument: name,
    type: typeShape,
    statements: musts
  });
  if (xy.mandatory === true) {
    out.mandatory = true;
  }
  out.description = descriptionOrEmpty(resolved.description);
  if (resolved.default !== undefined) {
    const schemaType = typeof resolved.type === "string" ? resolved.type : undefined;
    const xyType = typeof xy.type === "string" ? xy.type : undefined;
    out.default = yangDefaultFromJsonSchema(resolved.default, schemaType, xyType);
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
  setConfigFromXyang(out, xy);
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

function parseChoice(name: string, schema: Record<string, unknown>, defs: Record<string, unknown>): YangStatement {
  const xy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
  const choiceName = typeof xy.name === "string" && xy.name.length > 0 ? xy.name : name;
  const choiceStmt: YangStatement = new YangStatement({
    keyword: YangTokenType.CHOICE,
    name: choiceName,
    argument: choiceName,
    mandatory: xy.mandatory === true,
    statements: []
  });
  if (Array.isArray(xy["if-features"])) {
    const feats = (xy["if-features"] as unknown[]).filter((x): x is string => typeof x === "string" && x.trim().length > 0);
    if (feats.length > 0) {
      choiceStmt.if_features = feats;
    }
  }
  choiceStmt.description = firstNonEmptyDescription(xy.description, schema.description);
  setConfigFromXyang(choiceStmt, xy);

  let caseIndex = 0;
  for (const branchRaw of extractChoiceBranches(schema)) {
    const branch = asRecord(branchRaw);
    if (branch.type === JSON_TYPE_OBJECT && branch.maxProperties === 0) {
      continue;
    }
    caseIndex += 1;
    const branchXy = asRecord(branch[YANG_SCHEMA_KEYS.xYang]);
    const caseName = typeof branchXy.name === "string" && branchXy.name.length > 0 ? branchXy.name : `case-${caseIndex}`;
    const caseStmt: YangStatement = new YangStatement({
      keyword: YangTokenType.CASE,
      name: caseName,
      argument: caseName,
      statements: []
    });
    if (Array.isArray(branchXy["if-features"])) {
      const feats = (branchXy["if-features"] as unknown[]).filter(
        (x): x is string => typeof x === "string" && x.trim().length > 0
      );
      if (feats.length > 0) {
        caseStmt.if_features = feats;
      }
    }
    caseStmt.description = firstNonEmptyDescription(branchXy.description, branch.description);

    const branchProps = asRecord(branch.properties);
    for (const [childName, childSchema] of Object.entries(branchProps)) {
      if (!childSchema || typeof childSchema !== "object") {
        continue;
      }
      const childStmt = jsonSchemaPropertyToStatement(childName, childSchema as Record<string, unknown>, defs);
      if (!childStmt) {
        continue;
      }
      (caseStmt.statements as YangStatement[]).push(childStmt);
    }
    if ((caseStmt.statements as YangStatement[]).length > 0) {
      (choiceStmt.statements as YangStatement[]).push(caseStmt);
    }
  }
  return choiceStmt;
}

function parseAnydataOrAnyxml(name: string, schema: Record<string, unknown>, keyword: string): YangStatement {
  const xy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
  const musts = mustStatementsFromXyang(xy);
  const when = whenFromXyang(xy);
  const out: YangStatement = new YangStatement({
    keyword,
    name,
    argument: name,
    statements: musts
  });
  if (xy.mandatory === true) {
    out.mandatory = true;
  }
  out.description = descriptionOrEmpty(schema.description);
  if (when) {
    out.when = when;
  }
  return out;
}

function parseContainer(name: string, schema: Record<string, unknown>, defs: Record<string, unknown>): YangStatement {
  const xy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
  const props = asRecord(schema.properties);
  const musts = mustStatementsFromXyang(xy);
  const when = whenFromXyang(xy);
  const children: YangStatement[] = [...musts];
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
  const out: YangStatement = new YangStatement({
    keyword: YangTokenType.CONTAINER,
    name,
    argument: name,
    statements: children
  });
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
  out.description = descriptionOrEmpty(schema.description);
  if (when) {
    out.when = when;
  }
  setConfigFromXyang(out, xy);
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
        description: descriptionOrEmpty(ch.description)
      }
    };
    const choiceStmt = parseChoice(
      (choiceSchema[YANG_SCHEMA_KEYS.xYang] as Record<string, unknown>).name as string,
      choiceSchema,
      defs
    );
    if ((choiceStmt.statements as YangStatement[]).length > 0) {
      children.push(choiceStmt);
    }
  }
  if (Array.isArray(schema.allOf)) {
    out.allOf = schema.allOf;
  }
  return out;
}

function uniqueFromXyang(xy: Record<string, unknown>, where: string): string[][] | undefined {
  const raw = xy.unique;
  if (raw === undefined) {
    return undefined;
  }
  const ok =
    Array.isArray(raw) &&
    raw.every((paths) => Array.isArray(paths) && paths.length > 0 && paths.every((p) => typeof p === "string" && p.length > 0));
  if (!ok) {
    throw new Error(`x-yang 'unique' at ${where} must be a list of non-empty lists of paths, got ${JSON.stringify(raw)}`);
  }
  return (raw as string[][]).map((paths) => [...paths]);
}

function parseList(name: string, schema: Record<string, unknown>, defs: Record<string, unknown>): YangStatement {
  const xy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
  const items = asRecord(schema.items as Record<string, unknown>);
  const resolvedItems = resolveSchema(items, defs);
  const itemProps = asRecord(resolvedItems.properties);
  const musts = mustStatementsFromXyang(xy);
  const when = whenFromXyang(xy);
  const children: YangStatement[] = [...musts];
  for (const [childName, childSchema] of Object.entries(itemProps)) {
    if (!childSchema || typeof childSchema !== "object") {
      continue;
    }
    const stmt = jsonSchemaPropertyToStatement(childName, childSchema as Record<string, unknown>, defs);
    if (stmt) {
      children.push(stmt);
    }
  }
  const out: YangStatement = new YangStatement({
    keyword: YangTokenType.LIST,
    name,
    argument: name,
    statements: children,
    key: typeof xy.key === "string" ? xy.key : undefined,
    unique: uniqueFromXyang(xy, name),
    min_elements:
      typeof schema.minItems === "number"
        ? (schema.minItems as number)
        : (typeof xy["min-elements"] === "number" ? (xy["min-elements"] as number) : undefined),
    max_elements:
      typeof schema.maxItems === "number"
        ? (schema.maxItems as number)
        : (typeof xy["max-elements"] === "number" ? (xy["max-elements"] as number) : undefined)
  });
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
        description: descriptionOrEmpty(ch.description)
      }
    };
    const choiceStmt = parseChoice(
      (choiceSchema[YANG_SCHEMA_KEYS.xYang] as Record<string, unknown>).name as string,
      choiceSchema,
      defs
    );
    if ((choiceStmt.statements as YangStatement[]).length > 0) {
      children.push(choiceStmt);
    }
  }
  out.description = descriptionOrEmpty(schema.description);
  if (when) {
    out.when = when;
  }
  setConfigFromXyang(out, xy);
  return out;
}

function parseLeafList(name: string, schema: Record<string, unknown>, defs: Record<string, unknown>): YangStatement {
  const xy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
  const items = resolveSchema(asRecord(schema.items), defs);
  const itemXy = asRecord(items[YANG_SCHEMA_KEYS.xYang]);
  const mergedXy = { ...xy, ...itemXy };
  const typeShape = typeShapeFromJsonLeaf(items, mergedXy);
  const out: YangStatement = new YangStatement({
    keyword: YangTokenType.LEAF_LIST,
    name,
    argument: name,
    type: typeShape,
    statements: mustStatementsFromXyang(xy)
  });
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
  out.description = descriptionOrEmpty(schema.description);
  if (schema.default !== undefined) {
    if (Array.isArray(schema.default)) {
      out.defaults = schema.default.filter((x) => x !== undefined);
    } else {
      out.defaults = [schema.default];
    }
  }
  setConfigFromXyang(out, xy);
  return out;
}

function parseIoBlock(
  schema: Record<string, unknown>,
  defs: Record<string, unknown>,
  ioType: typeof YangTokenType.INPUT | typeof YangTokenType.OUTPUT
): YangStatement {
  const xy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
  const parsed = parseContainer(ioType, schema, defs);
  parsed.keyword = ioType;
  parsed.name = ioType;
  parsed.argument = ioType;
  applyStatementMetaFromXyang(parsed, xy);
  parsed.description = descriptionOrEmpty(schema.description);
  return parsed;
}

function parseRpc(
  name: string,
  rpcValue: Record<string, unknown>,
  defs: Record<string, unknown>,
  kind: string = YangTokenType.RPC
): YangStatement {
  const xy = asRecord(rpcValue[YANG_SCHEMA_KEYS.xYang]);
  if (xy.type !== kind) {
    throw new Error(`${kind} '${name}' must have x-yang type '${kind}', got ${JSON.stringify(xy.type)}`);
  }
  const statements: YangStatement[] = [...mustStatementsFromXyang(xy)];
  for (const ioKey of [YangTokenType.INPUT, YangTokenType.OUTPUT] as const) {
    const block = rpcValue[ioKey];
    if (block && typeof block === "object") {
      statements.push(parseIoBlock(block as Record<string, unknown>, defs, ioKey));
    }
  }
  const out: YangStatement = new YangStatement({
    keyword: kind,
    name,
    argument: name,
    statements
  });
  applyStatementMetaFromXyang(out, xy);
  return out;
}

/** Add the `x-yang.actions` of a container or list property as `action` children. */
function attachActions(stmt: YangStatement | null, schema: Record<string, unknown>, defs: Record<string, unknown>): YangStatement | null {
  if (!stmt || (stmt.keyword !== YangTokenType.CONTAINER && stmt.keyword !== YangTokenType.LIST)) {
    return stmt;
  }
  const xy = asRecord(resolveSchemaWithOverlay(schema, defs)[YANG_SCHEMA_KEYS.xYang]);
  const actions = xy[XYANG_KEYS.actions];
  if (actions === undefined) {
    return stmt;
  }
  if (!actions || typeof actions !== "object" || Array.isArray(actions)) {
    throw new Error(`x-yang "actions" of '${stmt.name}' must be an object keyed by action name`);
  }
  for (const [key, value] of Object.entries(actions as Record<string, unknown>)) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error(`action '${key}' of '${stmt.name}' must be an object`);
    }
    const colon = key.lastIndexOf(":");
    const action = parseRpc(colon < 0 ? key : key.slice(colon + 1), value as Record<string, unknown>, defs, YangTokenType.ACTION);
    if (colon >= 0) {
      action.defining_module = key.slice(0, colon);
    }
    stmt.statements.push(action);
  }
  return stmt;
}

/** One property. A `module:name` key is a node another module defines (augment). */
function jsonSchemaPropertyToStatement(
  name: string,
  schema: Record<string, unknown>,
  defs: Record<string, unknown>
): YangStatement | null {
  const colon = name.indexOf(":");
  if (colon < 0) {
    return attachActions(localPropertyToStatement(name, schema, defs), schema, defs);
  }
  const owner = name.slice(0, colon);
  const local = name.slice(colon + 1);
  if (!owner || !local) {
    throw new Error(`property name '${name}' must be 'name' or 'module:name'`);
  }
  const stmt = localPropertyToStatement(local, schema, defs);
  if (stmt) {
    stmt.defining_module = owner;
  }
  return attachActions(stmt, schema, defs);
}

function localPropertyToStatement(
  name: string,
  schema: Record<string, unknown>,
  defs: Record<string, unknown>
): YangStatement | null {
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
  if (resolved.type === JSON_TYPE_STRING && isStringNumberBuiltin(xyType)) {
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

const MISSING_ROOT_X_YANG =
  'JSON Schema has no root "x-yang" annotation; xYang needs a .yang.json produced by "xyang convert" (see design/json-schema-xyang-profile.md)';

function requireXYangObject(value: unknown, message: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(message);
  }
  return value as Record<string, unknown>;
}

/**
 * Build a {@link YangModule} from JSON Schema with `x-yang` annotations,
 * as produced by {@link generateJsonSchema}. Covers common data nodes used in tests; extend as needed for parity.
 *
 * Throws `Error` when the root schema, or a root `properties` member, has no `x-yang` object.
 * Plain JSON Schema is not imported.
 */
export function parseJsonSchema(source: string | Record<string, unknown>): YangModule {
  const root: Record<string, unknown> =
    typeof source === "string" ? (JSON.parse(source) as Record<string, unknown>) : { ...source };

  const rootXy = requireXYangObject(root[YANG_SCHEMA_KEYS.xYang], MISSING_ROOT_X_YANG);
  const moduleName = typeof rootXy.module === "string" ? rootXy.module : (typeof root.title === "string" ? root.title : "");
  const namespace = typeof rootXy.namespace === "string" ? rootXy.namespace : "";
  const prefix = typeof rootXy.prefix === "string" ? rootXy.prefix : "";

  const defsRaw = root.$defs;
  const defs = defsRaw && typeof defsRaw === "object" && !Array.isArray(defsRaw) ? (defsRaw as Record<string, unknown>) : {};

  const properties = asRecord(root.properties);
  const statements: YangStatement[] = [];
  for (const [propName, propSchema] of Object.entries(properties)) {
    if (!propSchema || typeof propSchema !== "object" || Array.isArray(propSchema)) {
      continue;
    }
    const prop = propSchema as Record<string, unknown>;
    requireXYangObject(
      prop[YANG_SCHEMA_KEYS.xYang],
      `JSON Schema property "${propName}" has no "x-yang" annotation`
    );
    const stmt = jsonSchemaPropertyToStatement(propName, prop, defs);
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

  const rpcsRaw = rootXy[XYANG_KEYS.rpcs];
  if (rpcsRaw && typeof rpcsRaw === "object" && !Array.isArray(rpcsRaw)) {
    for (const [rpcName, rpcVal] of Object.entries(rpcsRaw as Record<string, unknown>)) {
      if (!rpcVal || typeof rpcVal !== "object") {
        continue;
      }
      const rpcStmt = parseRpc(String(rpcName), rpcVal as Record<string, unknown>, defs);
      if (rpcStmt) {
        statements.push(rpcStmt);
      }
    }
  }

  bindUnrecordedPrefixes(statements, moduleName, prefix);

  const typedefs: Record<string, unknown> = {};
  const identities: Record<string, { bases: YangIdentifierRef[] }> = {};
  for (const [defName, defSchema] of Object.entries(defs)) {
    if (!defSchema || typeof defSchema !== "object") {
      continue;
    }
    const d = defSchema as Record<string, unknown>;
    const dxy = asRecord(d[YANG_SCHEMA_KEYS.xYang]);
    if (dxy.type === YangTokenType.IDENTITY) {
      identities[defName] = { bases: basesFromJson(dxy.bases) };
      continue;
    }
    // Legacy schemas may omit x-yang typedef metadata in $defs.
    typedefs[defName] = {
      name: defName,
      description: descriptionOrEmpty(d.description),
      type: typeShapeFromJsonLeaf(d, dxy),
      statements: []
    };
  }

  for (const typedef of Object.values(typedefs) as Array<{ type?: Record<string, unknown> }>) {
    const type = typedef.type;
    if (type && type.name === YangTokenType.LEAFREF && typeof type.path === "string" && type.path && !type.xpath_prefixes) {
      const recorded = ownPrefixBinding(type.path, true, moduleName, prefix);
      if (recorded) type.xpath_prefixes = recorded;
    }
  }

  const data: ModuleInit = {
        name: moduleName,
    yang_version: "1.1",
    namespace,
    prefix,
    description: descriptionOrEmpty(root.description),
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
