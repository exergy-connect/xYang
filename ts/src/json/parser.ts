import { scopePath, validateScope } from "../typedef-scope";
import { validateSemantics } from "../validator/semantic-validation";
import { coerceIdentifierRef, type YangIdentifierRef } from "../core/identifier-ref";
import { YangModule, YangStatement, normalizeTypeShape, type IdentityBases, type ModuleInit, type ModuleSource } from "../core/model";
import { YangTokenType } from "../parser/parser-context";
import { parseXPath, parseXPathPath, xpathPrefixes } from "../xpath/parser";
import { YangSyntaxError } from "../core/errors";
import { applyBuiltinExtensionInvocations } from "../ext/rfc8791";
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

function identityFromJson(def: unknown): IdentityBases {
  const d = asRecord(def);
  const xy = asRecord(d[YANG_SCHEMA_KEYS.xYang]);
  const features = Array.isArray(xy["if-features"])
    ? (xy["if-features"] as unknown[]).filter((x): x is string => typeof x === "string" && x.length > 0)
    : [];
  const holder = new YangStatement({ statements: [] });
  if (Array.isArray(xy[XYANG_KEYS.extensions])) {
    attachInvocations(holder, xy);
  }
  return {
    bases: basesFromJson(xy.bases),
    ...(typeof d.description === "string" && d.description.length > 0 ? { description: d.description } : {}),
    ...(features.length > 0 ? { if_features: features } : {}),
    ...(holder.statements.length > 0 ? { statements: holder.statements } : {})
  };
}

/** Module whose extensions an invocation resolves against while {@link parseJsonSchema} runs. */
let parsingModule: YangModule | undefined;

function extensionRecord(name: string, raw: unknown): Record<string, unknown> {
  const body = asRecord(raw);
  const record: Record<string, unknown> = { name };
  if (typeof body[XYANG_KEYS.argument] === "string" && (body[XYANG_KEYS.argument] as string).length > 0) {
    record.argument_name = body[XYANG_KEYS.argument];
  }
  if (XYANG_KEYS.yinElement in body) {
    if (typeof body[XYANG_KEYS.yinElement] !== "boolean") {
      throw new Error(`extension '${name}' "${XYANG_KEYS.yinElement}" must be a boolean`);
    }
    record.argument_yin_element = body[XYANG_KEYS.yinElement];
  }
  if (typeof body.description === "string") {
    record.description = body.description;
  }
  if (typeof body[XYANG_KEYS.reference] === "string") {
    record.reference = body[XYANG_KEYS.reference];
  }
  return record;
}

function extensionsFromJson(raw: unknown): Record<string, unknown> {
  if (raw === undefined) {
    return {};
  }
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error(`"${XYANG_KEYS.extension}" must map names to extension definitions`);
  }
  const out: Record<string, unknown> = {};
  for (const [name, body] of Object.entries(raw as Record<string, unknown>)) {
    out[name] = extensionRecord(name, body);
  }
  return out;
}

function invocationFromJson(raw: unknown): YangStatement {
  const body = asRecord(raw);
  const name = body.name;
  if (typeof name !== "string" || !name.includes(":")) {
    throw new Error(`extension invocation must be an object with "name" of the form "prefix:ext"`);
  }
  if (!parsingModule) {
    throw new Error("extension invocations require parseJsonSchema");
  }
  const prefix = name.slice(0, name.indexOf(":"));
  const extName = name.slice(name.indexOf(":") + 1);
  const own = String(parsingModule.prefix ?? "").replace(/^['"]|['"]$/g, "");
  const owner = prefix === own ? parsingModule : parsingModule.import_prefixes[prefix];
  if (!owner) {
    throw new Error(`extension invocation '${name}': unknown prefix '${prefix}'`);
  }
  const ext = (owner.extensions ?? {})[extName];
  if (!ext) {
    throw new Error(`extension invocation '${name}': unknown extension '${extName}' in module '${owner.name ?? ""}'`);
  }
  if (body[XYANG_KEYS.argument] !== undefined && typeof body[XYANG_KEYS.argument] !== "string") {
    throw new Error(`extension invocation '${name}': argument must be a string`);
  }
  const statements = [...mustStatementsFromXyang(body)];
  const nested = body[XYANG_KEYS.body];
  if (nested !== undefined && !Array.isArray(nested)) {
    throw new Error(`extension invocation '${name}': "${XYANG_KEYS.body}" must be a list`);
  }
  for (const item of Array.isArray(nested) ? nested : []) {
    const entry = asRecord(item);
    if (entry[XYANG_KEYS.extension] !== undefined) {
      statements.push(invocationFromJson(entry[XYANG_KEYS.extension]));
      continue;
    }
    if (typeof entry.node === "string" && entry.schema && typeof entry.schema === "object") {
      const child = jsonSchemaPropertyToStatement(entry.node, entry.schema as Record<string, unknown>, parsingDefs);
      if (!child) {
        throw new Error(`extension invocation '${name}': body node '${entry.node}' is not a schema node`);
      }
      statements.push(child);
      continue;
    }
    throw new Error(`extension invocation '${name}': body entry must be an extension or a node`);
  }
  const features = Array.isArray(body["if-features"])
    ? body["if-features"].filter((item): item is string => typeof item === "string")
    : undefined;
  const when = whenFromXyang(body);
  return new YangStatement({
    keyword: name,
    name,
    argument: typeof body[XYANG_KEYS.argument] === "string" ? (body[XYANG_KEYS.argument] as string) : undefined,
    prefix,
    resolved_module_name: owner.name,
    resolved_extension_name: extName,
    description: typeof body.description === "string" ? body.description : undefined,
    reference: typeof body[XYANG_KEYS.reference] === "string" ? (body[XYANG_KEYS.reference] as string) : undefined,
    ...(features && features.length > 0 ? { if_features: features } : {}),
    ...(when ? { when } : {}),
    ...(typeof body[XYANG_KEYS.config] === "boolean" ? { config: body[XYANG_KEYS.config] as boolean } : {}),
    statements
  });
}

let parsingDefs: Record<string, unknown> = {};

function attachInvocations(stmt: YangStatement, xy: Record<string, unknown>): void {
  const raw = xy[XYANG_KEYS.extensions];
  if (raw === undefined) {
    return;
  }
  if (!Array.isArray(raw)) {
    throw new Error(`"${XYANG_KEYS.extensions}" must be a list of invocations`);
  }
  for (const item of raw) {
    stmt.statements.push(invocationFromJson(item));
  }
}

/** Rebuild one `x-yang.imports` entry: an imported module reduced to its identities. */
function moduleFromImportStub(key: string, raw: unknown): YangModule {
  const stub = asRecord(raw);
  if (typeof stub.module !== "string" || typeof stub.prefix !== "string") {
    throw new Error(`"${XYANG_KEYS.imports}" entry '${key}' must be an object with "module" and "prefix"`);
  }
  const identitiesRaw = stub[XYANG_KEYS.identities] ?? {};
  if (!identitiesRaw || typeof identitiesRaw !== "object" || Array.isArray(identitiesRaw)) {
    throw new Error(`"${XYANG_KEYS.identities}" of import '${key}' must be an object`);
  }
  const identities: Record<string, IdentityBases> = {};
  for (const [name, def] of Object.entries(identitiesRaw as Record<string, unknown>)) {
    const xy = asRecord(asRecord(def)[YANG_SCHEMA_KEYS.xYang]);
    if (xy.type !== YangTokenType.IDENTITY) {
      throw new Error(`identity '${name}' of import '${key}' is not an identity definition`);
    }
    identities[name] = identityFromJson(def);
  }
  const featureState = featuresFromJson(stub);
  const imported = new YangModule(
    {
      name: stub.module,
      yang_version: "1.1",
      namespace: typeof stub.namespace === "string" ? stub.namespace : "",
      prefix: stub.prefix,
      identities,
      import_prefixes: importsFromJson(stub),
      extensions: extensionsFromJson(stub[XYANG_KEYS.extension]),
      features: featureState.features,
      feature_if_features: featureState.feature_if_features,
      statements: []
    },
    { kind: "string", value: "", name: "<json-schema-import>" }
  );
  loadStubInvocations(imported, stub);
  return imported;
}

function featuresFromJson(xy: Record<string, unknown>): { features: Set<string>; feature_if_features: Record<string, string[]> } {
  const features = new Set<string>();
  const feature_if_features: Record<string, string[]> = {};
  const raw = xy[XYANG_KEYS.features];
  if (raw === undefined) {
    return { features, feature_if_features };
  }
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error(`"${XYANG_KEYS.features}" must map feature names to objects`);
  }
  for (const [name, body] of Object.entries(raw as Record<string, unknown>)) {
    if (!body || typeof body !== "object" || Array.isArray(body)) {
      throw new Error(`feature '${name}' must be an object`);
    }
    features.add(name);
    const guards = (body as Record<string, unknown>)["if-features"];
    if (guards !== undefined) {
      if (!Array.isArray(guards) || !guards.every((item) => typeof item === "string")) {
        throw new Error(`feature '${name}' "if-features" must be a list of strings`);
      }
      feature_if_features[name] = guards as string[];
    }
  }
  return { features, feature_if_features };
}

function loadStubInvocations(stub: YangModule, raw: Record<string, unknown>): void {
  const invocations = raw[XYANG_KEYS.extensions];
  if (invocations === undefined) {
    return;
  }
  if (!Array.isArray(invocations)) {
    throw new Error(`"${XYANG_KEYS.extensions}" of import '${stub.name ?? ""}' must be a list`);
  }
  const previous = parsingModule;
  parsingModule = stub;
  try {
    for (const item of invocations) {
      stub.statements.push(invocationFromJson(item));
    }
  } finally {
    parsingModule = previous;
  }
  applyBuiltinExtensionInvocations(stub);
}

/** Bind `x-yang.imports` as import prefixes, so identity bases resolve without files. */
function importsFromJson(xy: Record<string, unknown>): Record<string, YangModule> {
  const raw = xy[XYANG_KEYS.imports];
  if (raw === undefined) {
    return {};
  }
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error(`"${XYANG_KEYS.imports}" must map keys to imported modules`);
  }
  return Object.fromEntries(
    Object.entries(raw as Record<string, unknown>).map(([key, stub]) => [key, moduleFromImportStub(key, stub)])
  );
}

function setConfigFromXyang(stmt: YangStatement, xyang: Record<string, unknown>): void {
  if (XYANG_KEYS.config in xyang && typeof xyang[XYANG_KEYS.config] === "boolean") {
    stmt.config = xyang[XYANG_KEYS.config] as boolean;
  }
}

function resolveSchema(schema: Record<string, unknown>, defs: Record<string, unknown>): Record<string, unknown> {
  const ref = schema.$ref;
  if (typeof ref === "string" && ref.startsWith("#/$defs/")) {
    const name = decodeURIComponent(ref.slice("#/$defs/".length)).replace(/~1/g, "/").replace(/~0/g, "~");
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
  const name = decodeURIComponent(ref.slice("#/$defs/".length)).replace(/~1/g, "/").replace(/~0/g, "~");
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

function setTypeContext(shape: Record<string, unknown> | undefined, inherited: string): void {
  if (!shape) return;
  shape.context ??= inherited;
  for (const member of (shape.types ?? []) as Record<string, unknown>[]) setTypeContext(member, String(shape.context));
}

function bindUnrecordedPrefixes(statements: YangStatement[], moduleName: string, ownPrefix: string, context = ""): void {
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
    setTypeContext(type, context);
    if (type?.kind === "leafref" && typeof type.path === "string" && type.path && !type.xpath_prefixes) {
      const recorded = ownPrefixBinding(type.path, true, moduleName, ownPrefix);
      if (recorded) type.xpath_prefixes = recorded;
    }
    bindUnrecordedPrefixes(stmt.statements, moduleName, ownPrefix, scopePath(context, stmt));
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
    evaluate_with_parent_context:
      o["evaluate-with-parent-context"] === true || o.evaluate_with_parent_context === true,
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
      ...(typeof e["error-app-tag"] === "string" && e["error-app-tag"].length > 0
        ? { error_app_tag: e["error-app-tag"] }
        : {}),
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
  return normalizeTypeShape(rawTypeShapeFromJsonLeaf(schema, xy));
}

function rawTypeShapeFromJsonLeaf(schema: Record<string, unknown>, xy: Record<string, unknown>): Record<string, unknown> {
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
    return { name: typedefRef, ...(xy["type-context"] !== undefined ? { context: xy["type-context"] === "" ? "" : validateScope(xy["type-context"]) } : {}) };
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
  out.description = descriptionOrEmpty(schema.description);
  if (schema.default !== undefined) {
    const schemaType = typeof resolved.type === "string" ? resolved.type : undefined;
    const xyType = typeof xy.type === "string" ? xy.type : undefined;
    out.default = yangDefaultFromJsonSchema(schema.default, schemaType, xyType);
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
  if (typeof xy.units === "string") out.units = xy.units;
  setConfigFromXyang(out, xy);
  attachInvocations(out, xy);
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
    attachInvocations(caseStmt, branchXy);
    if ((caseStmt.statements as YangStatement[]).length > 0) {
      (choiceStmt.statements as YangStatement[]).push(caseStmt);
    }
  }
  attachInvocations(choiceStmt, xy);
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
  attachInvocations(out, xy);
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
        ...(Array.isArray(ch[XYANG_KEYS.extensions]) ? { [XYANG_KEYS.extensions]: ch[XYANG_KEYS.extensions] } : {}),
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
  attachInvocations(out, xy);
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
        ...(Array.isArray(ch[XYANG_KEYS.extensions]) ? { [XYANG_KEYS.extensions]: ch[XYANG_KEYS.extensions] } : {}),
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
  attachInvocations(out, xy);
  out.description = descriptionOrEmpty(schema.description);
  if (when) {
    out.when = when;
  }
  setConfigFromXyang(out, xy);
  return out;
}

function parseLeafList(name: string, schema: Record<string, unknown>, defs: Record<string, unknown>): YangStatement {
  const xy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
  const items = resolveSchemaWithOverlay(asRecord(schema.items), defs);
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
  if (typeof xy.units === "string") out.units = xy.units;
  setConfigFromXyang(out, xy);
  attachInvocations(out, xy);
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
  attachInvocations(out, xy);
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
function stampAugmentStructure(stmt: YangStatement | null, schema: Record<string, unknown>): YangStatement | null {
  if (!stmt) {
    return stmt;
  }
  const path = asRecord(schema[YANG_SCHEMA_KEYS.xYang])[XYANG_KEYS.augmentStructure];
  if (typeof path === "string" && path.length > 0) {
    (stmt as { augment_structure?: string }).augment_structure = path;
  }
  return stmt;
}

function jsonSchemaPropertyToStatement(
  name: string,
  schema: Record<string, unknown>,
  defs: Record<string, unknown>
): YangStatement | null {
  const colon = name.indexOf(":");
  if (colon < 0) {
    return stampAugmentStructure(attachActions(localPropertyToStatement(name, schema, defs), schema, defs), schema);
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
  return stampAugmentStructure(attachActions(stmt, schema, defs), schema);
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
    return parseLeaf(name, schema, defs);
  }
  if (
    xyType === YangTokenType.LEAFREF ||
    xyType === YangTokenType.IDENTITYREF ||
    xyType === YangTokenType.INSTANCE_IDENTIFIER
  ) {
    return parseLeaf(name, schema, defs);
  }
  if (resolved.type === JSON_TYPE_STRING && isStringNumberBuiltin(xyType)) {
    return parseLeaf(name, schema, defs);
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

  const importPrefixes = importsFromJson(rootXy);
  const extensions = extensionsFromJson(rootXy[XYANG_KEYS.extension]);
  const shell = new YangModule(
    {
      name: moduleName,
      yang_version: "1.1",
      namespace,
      prefix,
      import_prefixes: importPrefixes,
      extensions,
      statements: []
    },
    { kind: "string", value: "", name: "<json-schema>" }
  );
  const previousModule = parsingModule;
  const previousDefs = parsingDefs;
  parsingModule = shell;
  parsingDefs = defs;
  try {

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
  const identities: Record<string, IdentityBases> = {};
  for (const [defName, defSchema] of Object.entries(defs)) {
    if (!defSchema || typeof defSchema !== "object") {
      continue;
    }
    const d = defSchema as Record<string, unknown>;
    const dxy = asRecord(d[YANG_SCHEMA_KEYS.xYang]);
    if (dxy.type === YangTokenType.IDENTITY) {
      identities[defName] = identityFromJson(d);
      continue;
    }
    // Legacy schemas may omit x-yang typedef metadata in $defs.
    const holder = new YangStatement({ statements: [] });
    attachInvocations(holder, dxy);
    typedefs[defName] = {
      name: typeof dxy.name === "string" ? dxy.name : defName,
      scope: validateScope(dxy.scope),
      ...(dxy.scope !== undefined ? { units: typeof dxy.units === "string" ? dxy.units : undefined, default: d.default } : {}),
      description: descriptionOrEmpty(d.description),
      type: typeShapeFromJsonLeaf(d, dxy),
      statements: holder.statements
    };
  }

  for (const typedef of Object.values(typedefs) as Array<{ scope?: string; type?: Record<string, unknown> }>) {
    const type = typedef.type;
    setTypeContext(type, typedef.scope ?? "");
    if (type?.kind === "leafref" && typeof type.path === "string" && type.path && !type.xpath_prefixes) {
      const recorded = ownPrefixBinding(type.path, true, moduleName, prefix);
      if (recorded) type.xpath_prefixes = recorded;
    }
  }

  const moduleInvocations = new YangStatement({ statements: [] });
  attachInvocations(moduleInvocations, rootXy);
  statements.push(...moduleInvocations.statements);

  const featureState = featuresFromJson(rootXy);
  const data: ModuleInit = {
        name: moduleName,
    yang_version: "1.1",
    namespace,
    prefix,
    description: descriptionOrEmpty(root.description),
    typedefs,
    identities,
    import_prefixes: importPrefixes,
    extensions,
    extension_runtime: {},
    features: featureState.features,
    feature_if_features: featureState.feature_if_features,
    statements
  };

  const modSource: ModuleSource = { kind: "string", value: typeof source === "string" ? source : JSON.stringify(source), name: "<json-schema>" };
  const loaded = new YangModule(data, modSource);
  // Index sx:structure and apply a cross-module sx:augment-structure once.
  applyBuiltinExtensionInvocations(loaded);
  validateSemantics(loaded);
  return loaded;
  } finally {
    parsingModule = previousModule;
    parsingDefs = previousDefs;
  }
}
