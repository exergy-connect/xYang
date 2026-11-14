import { type ScopedTypedef } from "../typedef-scope";
import {
  coerceIdentifierRef,
  formatIdentifierRef,
  parseAbsoluteSchemaPath,
  parseIdentifierRefAtom
} from "../core/identifier-ref";
import { YangModule, YangStatement, type YangStatementInit } from "../core/model";
import { hasTokenType, YangTokenType } from "../parser/parser-context";
import { applyAugments, applyDeviations } from "../transform/augment-expand";
import { expandUses } from "../transform/uses-expand";
import { YangExportError } from "../core/errors";
import { applyBuiltinExtensionInvocations } from "../ext/rfc8791";
import { identityDef, importsForJson, withIdentityExport } from "./identity-export";
import type { IdentityPair } from "../identity-graph";
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

/** Imported extensions the export invoked. Restored around {@link generateJsonSchema}. */
let extensionUses: Array<{ owner: YangModule; name: string }> | undefined;

function isExtensionInvocation(stmt: YangStatement): boolean {
  return typeof stmt.prefix === "string" && stmt.prefix.length > 0
    && typeof stmt.resolved_extension_name === "string" && stmt.resolved_extension_name.length > 0;
}

function asStatement(value: unknown): YangStatement {
  return value instanceof YangStatement ? value : new YangStatement((value ?? {}) as YangStatementInit);
}

function statementListOf(value: unknown): YangStatement[] {
  return Array.isArray(value) ? value.map(asStatement) : [];
}

function extensionLabel(stmt: YangStatement): string {
  return `${stmt.prefix}:${stmt.resolved_extension_name}`;
}

function rejectSemanticExtension(stmt: YangStatement): void {
  const owner = stmt.resolved_module_name ?? "";
  const ext = stmt.resolved_extension_name ?? "";
  // RFC 8791 round-trips (#164). Any other extension with an apply callback does not.
  if (owner === "ietf-yang-structure-ext" && (ext === "structure" || ext === "augment-structure")) {
    return;
  }
  if ((stmt as { has_apply_callback?: boolean }).has_apply_callback === true) {
    throw new YangExportError(
      `cannot export extension invocation '${extensionLabel(stmt)}': ` +
        `extension ${owner}:${ext} is applied when the module is parsed and is not ` +
        `re-applied when the native JSON form is loaded`
    );
  }
}

function lookupImportedModule(root: YangModule, name: string): YangModule | undefined {
  for (const imported of Object.values(root.import_prefixes)) {
    if (imported.name === name) {
      return imported;
    }
  }
  return root.module_registry?.[name];
}

function recordImportedExtension(stmt: YangStatement, root: YangModule): void {
  if (!extensionUses) {
    throw new YangExportError(`cannot export extension invocation '${extensionLabel(stmt)}' outside generateJsonSchema`);
  }
  const ownerName = stmt.resolved_module_name ?? "";
  if (!ownerName || ownerName === root.name) {
    return;
  }
  const owner = lookupImportedModule(root, ownerName);
  if (!owner) {
    throw new YangExportError(
      `cannot export extension invocation '${extensionLabel(stmt)}': module '${ownerName}' is not loaded`
    );
  }
  const extName = stmt.resolved_extension_name ?? "";
  if (!extensionUses.some((item) => item.owner === owner && item.name === extName)) {
    extensionUses.push({ owner, name: extName });
  }
}

function extensionDefJson(ext: unknown): Record<string, unknown> {
  const raw = asRecord(ext);
  const out: Record<string, unknown> = {};
  const argument = typeof raw.argument_name === "string" ? raw.argument_name : "";
  if (argument.length > 0) {
    out[XYANG_KEYS.argument] = argument;
  }
  if (typeof raw.argument_yin_element === "boolean") {
    out[XYANG_KEYS.yinElement] = raw.argument_yin_element;
  }
  const description = typeof raw.description === "string" ? raw.description : "";
  if (description.length > 0) {
    out.description = description;
  }
  const reference = typeof raw.reference === "string" ? raw.reference : "";
  if (reference.length > 0) {
    out[XYANG_KEYS.reference] = reference;
  }
  return out;
}

function oneExtensionInvocation(
  stmt: YangStatement,
  module: YangModule,
  typedefNames: Set<string>
): Record<string, unknown> {
  rejectSemanticExtension(stmt);
  recordImportedExtension(stmt, module);
  const out: Record<string, unknown> = { name: extensionLabel(stmt) };
  if (typeof stmt.argument === "string") {
    out[XYANG_KEYS.argument] = stmt.argument;
  }
  if (typeof stmt.description === "string" && stmt.description.length > 0) {
    out.description = stmt.description;
  }
  if (typeof stmt.reference === "string" && stmt.reference.length > 0) {
    out[XYANG_KEYS.reference] = stmt.reference;
  }
  const features = Array.isArray(stmt.if_features)
    ? stmt.if_features.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
  if (features.length > 0) {
    out["if-features"] = features;
  }
  const whenShape = asRecord(stmt.when);
  const whenExpression = typeof whenShape.expression === "string" ? whenShape.expression : "";
  if (whenExpression.trim().length > 0) {
    const whenOut: Record<string, unknown> = {
      condition: whenExpression,
      ...xpathPrefixesEntry(whenShape.xpath_prefixes)
    };
    if (typeof whenShape.description === "string" && whenShape.description.trim().length > 0) {
      whenOut.description = whenShape.description.trim();
    }
    if (whenShape.evaluate_with_parent_context === true) {
      whenOut["evaluate-with-parent-context"] = true;
    }
    out.when = whenOut;
  }
  const must = mustToXYang(stmt);
  if (must.length > 0) {
    out.must = must;
  }
  if (typeof stmt.config === "boolean") {
    out[XYANG_KEYS.config] = stmt.config;
  }
  const body: Array<Record<string, unknown>> = [];
  for (const child of stmt.statements ?? []) {
    if (child.keyword === YangTokenType.MUST) {
      continue;
    }
    if (isExtensionInvocation(child)) {
      body.push({ [XYANG_KEYS.extension]: oneExtensionInvocation(child, module, typedefNames) });
      continue;
    }
    if (isSchemaDataNode(child) && child.keyword !== YangTokenType.CASE) {
      body.push({
        node: propertyKey(child, module),
        schema: statementToSchema(child, module, typedefNames)
      });
      continue;
    }
    throw new YangExportError(
      `cannot export extension invocation '${extensionLabel(stmt)}': nested statement ${child.keyword ?? ""} '${child.name ?? ""}' is not representable in the native JSON form`
    );
  }
  if (body.length > 0) {
    out[XYANG_KEYS.body] = body;
  }
  return out;
}

function extensionInvocationsJson(
  statements: YangStatement[],
  module: YangModule,
  typedefNames: Set<string>
): Array<Record<string, unknown>> {
  return statements.filter(isExtensionInvocation).map((stmt) => oneExtensionInvocation(stmt, module, typedefNames));
}

function stampExtensions(
  xyang: Record<string, unknown>,
  statements: YangStatement[],
  module: YangModule,
  typedefNames: Set<string>
): void {
  const invocations = extensionInvocationsJson(statements, module, typedefNames);
  if (invocations.length > 0) {
    xyang[XYANG_KEYS.extensions] = invocations;
  }
}

function ownPrefixOf(module: YangModule): string {
  return String(module.prefix ?? "").replace(/^['"]|['"]$/g, "");
}

function extensionImportKey(root: YangModule, module: YangModule): string {
  for (const [prefix, imported] of Object.entries(root.import_prefixes)) {
    if (imported === module || imported.name === module.name) {
      return prefix;
    }
  }
  const name = module.name ?? "";
  if (name in root.import_prefixes || name === ownPrefixOf(root)) {
    throw new YangExportError(
      `cannot export extensions of module '${name}': the name is also a prefix of module '${root.name}'`
    );
  }
  return name;
}

function localExtensionDefs(module: YangModule): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [name, ext] of Object.entries(module.extensions ?? {})) {
    out[name] = extensionDefJson(ext);
  }
  return out;
}

function mergeExtensionImports(
  root: YangModule,
  imports: Record<string, unknown>,
  used: Array<{ owner: YangModule; name: string }>
): Record<string, unknown> {
  const byOwner = new Map<string, { owner: YangModule; names: string[] }>();
  for (const item of used) {
    const key = item.owner.name ?? "";
    const bucket = byOwner.get(key) ?? { owner: item.owner, names: [] };
    if (!bucket.names.includes(item.name)) {
      bucket.names.push(item.name);
    }
    byOwner.set(key, bucket);
  }
  for (const { owner, names } of byOwner.values()) {
    const key = extensionImportKey(root, owner);
    const stub = asRecord(imports[key]);
    if (!imports[key]) {
      imports[key] = {
        module: owner.name,
        namespace: owner.namespace ?? "",
        prefix: owner.prefix ?? ""
      };
    }
    const target = asRecord(imports[key]);
    if (Object.keys(stub).length === 0 && imports[key] !== target) {
      Object.assign(target, stub);
    }
    const extMap: Record<string, unknown> = {};
    for (const name of [...names].sort()) {
      const ext = (owner.extensions ?? {})[name];
      if (!ext) {
        throw new YangExportError(
          `cannot export extension ${owner.name}:${name}: the extension definition is not in that module`
        );
      }
      extMap[name] = extensionDefJson(ext);
    }
    target[XYANG_KEYS.extension] = extMap;
  }
  return Object.fromEntries(Object.entries(imports).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));
}

const PLACED_KEYWORDS = new Set([
  YangTokenType.CONTAINER,
  YangTokenType.LIST,
  YangTokenType.LEAF,
  YangTokenType.LEAF_LIST,
  YangTokenType.CHOICE,
  YangTokenType.CASE,
  YangTokenType.ANYDATA,
  YangTokenType.ANYXML,
  YangTokenType.RPC,
  YangTokenType.ACTION,
  YangTokenType.INPUT,
  YangTokenType.OUTPUT,
  YangTokenType.TYPEDEF,
  "identity"
]);

function findExtensionInvocation(stmt: YangStatement): YangStatement | undefined {
  if (isExtensionInvocation(stmt)) {
    return stmt;
  }
  for (const child of stmt.statements ?? []) {
    const found = findExtensionInvocation(child);
    if (found) {
      return found;
    }
  }
  return undefined;
}

function assertExtensionsPlaced(module: YangModule): void {
  const walk = (owner: YangStatement, placed: boolean): void => {
    for (const child of owner.statements ?? []) {
      if (isExtensionInvocation(child)) {
        rejectSemanticExtension(child);
        if (!placed) {
          throw new YangExportError(
            `cannot export extension invocation '${extensionLabel(child)}': ` +
              `it is on ${owner.keyword ?? ""} '${owner.name ?? ""}', which the native JSON form does not carry`
          );
        }
        walk(child, true);
        continue;
      }
      if (child.keyword === "grouping" || child.keyword === YangTokenType.EXTENSION) {
        continue;
      }
      if (child.keyword === YangTokenType.USES) {
        const found = findExtensionInvocation(child);
        if (found) {
          throw new YangExportError(
            `cannot export extension invocation '${extensionLabel(found)}': ` +
              `it is inside uses '${child.argument ?? child.name ?? ""}', which the native JSON form does not carry`
          );
        }
        continue;
      }
      walk(child, PLACED_KEYWORDS.has(child.keyword ?? ""));
    }
  };
  for (const stmt of module.statements) {
    if (isExtensionInvocation(stmt)) {
      rejectSemanticExtension(stmt);
      walk(stmt, true);
      continue;
    }
    if (stmt.keyword === "grouping" || stmt.keyword === YangTokenType.EXTENSION) {
      continue;
    }
    if (stmt.keyword === YangTokenType.USES) {
      const found = findExtensionInvocation(stmt);
      if (found) {
        throw new YangExportError(
          `cannot export extension invocation '${extensionLabel(found)}': ` +
            `it is inside uses '${stmt.argument ?? stmt.name ?? ""}', which the native JSON form does not carry`
        );
      }
      continue;
    }
    walk(stmt, PLACED_KEYWORDS.has(stmt.keyword ?? ""));
  }
  for (const raw of Object.values(module.identities)) {
    for (const stmt of statementListOf((raw as { statements?: unknown }).statements)) {
      if (!isExtensionInvocation(stmt)) {
        continue;
      }
      rejectSemanticExtension(stmt);
      walk(stmt, true);
    }
  }
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
      ...(typeof child.error_app_tag === "string" && child.error_app_tag.length > 0
        ? { "error-app-tag": child.error_app_tag }
        : {}),
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
  meta: Record<string, unknown>,
  module?: YangModule,
  typedefNames?: Set<string>
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
  if (typeof stmt.units === "string" && stmt.units) out.units = stmt.units;
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
    if (whenShape.evaluate_with_parent_context === true) {
      whenOut["evaluate-with-parent-context"] = true;
    }
    out.when = whenOut;
  }
  const augmentStructure = (stmt as { augment_structure?: string }).augment_structure;
  if (typeof augmentStructure === "string" && augmentStructure.length > 0) {
    out["augment-structure"] = augmentStructure;
  }
  const presenceRaw = stmt.presence;
  if (typeof presenceRaw === "string" && presenceRaw.trim().length > 0) {
    out.presence = presenceRaw;
  }
  const must = mustToXYang(stmt);
  if (must.length > 0) {
    out.must = must;
  }
  if (module && typedefNames) {
    stampExtensions(out, stmt.statements ?? [], module, typedefNames);
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
  if (resolveTypedef(module, typeShape)?.scope !== undefined) return typeShape;
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
      throw new YangExportError(`cannot export type '${label}': its typedef is not found where the type is written`);
    }
    if (current.range || current.length || (Array.isArray(current.patterns) && current.patterns.length > 0)) {
      throw new YangExportError(`cannot export restrictions on the imported typedef '${label}' in the native JSON form`);
    }
    current = typedef.type;
  }
  return current;
}

type ScopedExportEntry = { td: ScopedTypedef; owner: YangModule; key: string };
let scopedExportDefs: Record<string, ScopedExportEntry> = {};
const defsRef = (name: string): string => `#/$defs/${encodeURIComponent(name.replace(/~/g, "~0").replace(/\//g, "~1"))}`;
function scopedCatalog(module: YangModule): Record<string, ScopedExportEntry> {
  const out: Record<string, ScopedExportEntry> = {};
  const seen = new Set<YangModule>();
  const collect = (current: YangModule): void => {
    if (seen.has(current)) return;
    seen.add(current);
    for (const [key, value] of Object.entries(current.typedefs)) {
      const td = value as ScopedTypedef;
      if (td.scope !== undefined) {
        const exported = current === module ? key : `@${current.name}:${key}`;
        if (exported in out) throw new YangExportError(`Conflicting scoped typedef key '${exported}'`);
        out[exported] = { td, owner: current, key };
      }
    }
    for (const imported of Object.values(current.import_prefixes)) collect(imported);
  };
  collect(module);
  return out;
}
function scopedTypeSchema(type: Record<string, unknown>, module: YangModule): Record<string, unknown> | undefined {
  const td = resolveTypedef(module, type);
  if (td?.scope === undefined) return undefined;
  if (type.range || type.length || (Array.isArray(type.patterns) && type.patterns.length)) throw new YangExportError(`cannot export restrictions on scoped typedef '${td.name}' in the native JSON form`);
  const writer = typeof type.scope_module === "string" ? type.scope_module : module.name;
  const source = writer === module.name ? module : module.module_registry?.[String(writer)];
  const storageKey = Object.entries(source?.typedefs ?? {}).find(([, value]) => value === td)?.[0];
  const found = Object.entries(scopedExportDefs).find(([, entry]) => entry.owner.name === writer && entry.key === storageKey);
  if (!found) throw new YangExportError(`Scoped typedef '${td.name}' is absent from the export catalog`);
  return { $ref: defsRef(found[0]), [YANG_SCHEMA_KEYS.xYang]: { "type-context": type.context ?? "" } };
}

function typedefRefOrInline(
  typeShape: Record<string, unknown>,
  typedefNames: Set<string>,
  module: YangModule
): Record<string, unknown> {
  const scoped = scopedTypeSchema(typeShape, module);
  if (scoped) return scoped;
  const typeName = typeof typeShape.name === "string" ? typeShape.name : "";
  const prefix = typeof typeShape.prefix === "string" && typeShape.prefix ? typeShape.prefix : undefined;
  const scope = typeof typeShape.scope_module === "string" ? typeShape.scope_module : undefined;
  const local = !prefix && (scope === undefined || scope === module.name);
  if (local && typedefNames.has(typeName)) {
    return { $ref: defsRef(typeName) };
  }
  if (!prefix && Object.prototype.hasOwnProperty.call(REGISTRY, typeName)) {
    if (typeName === "union") return { oneOf: ((typeShape.types ?? []) as Record<string, unknown>[]).map((member) => typedefRefOrInline(member, typedefNames, module)) };
    return leafTypeToSchema(typeShape);
  }
  // A typedef from another module is inlined; the JSON form's `$defs` hold only this module's.
  const label = prefix ? `${prefix}:${typeName}` : typeName;
  const typedef = resolveTypedef(module, typeShape);
  if (!typedef?.type) {
    throw new YangExportError(`cannot export type '${label}': its typedef is not found where the type is written`);
  }
  if (typeShape.range || typeShape.length || (Array.isArray(typeShape.patterns) && typeShape.patterns.length > 0)) {
    throw new YangExportError(`cannot export restrictions on the imported typedef '${label}' in the native JSON form`);
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
function choiceMetaForXYang(
  choice: YangStatement,
  module: YangModule,
  typedefNames: Set<string>
): Record<string, unknown> {
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
  stampExtensions(meta, choice.statements ?? [], module, typedefNames);
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
    [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(stmt, { type: ioType }, module, typedefNames)
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
    [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(stmt, { type: kind }, module, typedefNames)
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
      [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(c, { name: c.name ?? "case" }, module, typedefNames)
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
    stampExtensions(xyChoice, stmt.statements ?? [], module, typedefNames);
    const choiceAugment = (stmt as { augment_structure?: string }).augment_structure;
    if (typeof choiceAugment === "string" && choiceAugment.length > 0) {
      xyChoice["augment-structure"] = choiceAugment;
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
    const xYang = withStatementMeta(stmt, { type: keyword }, module, typedefNames) as Record<string, unknown>;
    if (soleChoice) {
      xYang.choice = choiceMetaForXYang(soleChoice, module, typedefNames);
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
    }, module, typedefNames) as Record<string, unknown>;
    if (soleChoice) {
      listXY.choice = choiceMetaForXYang(soleChoice, module, typedefNames);
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
      }, module, typedefNames)
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
      ...asRecord(leafSchema[YANG_SCHEMA_KEYS.xYang]),
      type: keyword
    }, module, typedefNames);
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
      }, module, typedefNames)
    };
    withDescription(out, stmt.description);
    return out;
  }

  return {
    type: JSON_TYPE_FREE_FORM
  };
}

function typedefToSchema(module: YangModule, entries = module.typedefs): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const typedefs = entries as Record<string, { type?: unknown; description?: string }>;
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
    const invocations = extensionInvocationsJson(statementListOf((entry as { statements?: unknown }).statements), module, names);
    if (invocations.length > 0) {
      const xy = asRecord(def[YANG_SCHEMA_KEYS.xYang]);
      xy[XYANG_KEYS.extensions] = invocations;
      def[YANG_SCHEMA_KEYS.xYang] = xy;
    }
    const scoped = entry as ScopedTypedef;
    if (scoped.scope !== undefined) {
      def[YANG_SCHEMA_KEYS.xYang] = { ...asRecord(def[YANG_SCHEMA_KEYS.xYang]), scope: scoped.scope, name: scoped.name, ...(scoped.units ? { units: scoped.units } : {}) };
      const defaultValue = (entry as { default?: unknown }).default;
      if (defaultValue !== undefined) def.default = jsonSchemaDefaultValue(defaultValue, { yangTypeName: String(typeShape.name), jsonSchemaType: typeof def.type === "string" ? def.type : null });
    }
    out[name] = def;
  }
  return out;
}

function scopedTypedefsToSchema(): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, { td, owner }] of Object.entries(scopedExportDefs)) {
    Object.assign(out, typedefToSchema(owner, { [key]: td }));
  }
  return out;
}

function identityToSchema(module: YangModule, typedefNames: Set<string>): Record<string, unknown> {
  const defs: Record<string, unknown> = {};
  for (const identityName of Object.keys(module.identities)) {
    const def = identityDef(module, identityName);
    const raw = (module.identities as Record<string, { statements?: unknown }>)[identityName];
    const invocations = extensionInvocationsJson(statementListOf(raw?.statements), module, typedefNames);
    if (invocations.length > 0) {
      asRecord(def[YANG_SCHEMA_KEYS.xYang])[XYANG_KEYS.extensions] = invocations;
    }
    defs[identityName] = def;
  }
  return defs;
}

/**
 * Merge the module's `augment` statements into its own (`uses`-expanded) tree. The native JSON form is the
 * module's schema tree, so an augment of a node it instantiates (including through an imported grouping)
 * becomes part of that node. An augment of another module's own tree has no place here: an error, not dropped.
 */
function applyOwnAugments(effective: YangModule): void {
  for (const stmt of effective.statements) {
    if (stmt.keyword !== YangTokenType.AUGMENT) {
      continue;
    }
    const path = String(stmt.augment_path ?? stmt.argument ?? "");
    const first = (Array.isArray(stmt.augment_path_segments) && stmt.augment_path_segments.length > 0
      ? stmt.augment_path_segments
      : parseAbsoluteSchemaPath(path))[0];
    const own = String(effective.prefix ?? "").replace(/^['"]|['"]$/g, "");
    if (first?.prefix !== own) {
      throw new YangExportError(
        `cannot export augment '${path}': its target belongs to another module, ` +
          `which the native JSON form of module '${effective.name}' does not carry`
      );
    }
  }
  applyAugments(effective);
}

/**
 * Apply the module's `deviation` statements to its own (augmented) tree. Like an augment, a deviation of
 * another module's tree has no place in this module's JSON: an error, not dropped.
 */
function applyOwnDeviations(effective: YangModule): void {
  for (const stmt of effective.statements) {
    if (stmt.keyword !== "deviation") {
      continue;
    }
    const path = String(stmt.deviation_path ?? stmt.argument ?? "");
    const first = (Array.isArray(stmt.deviation_path_segments) && stmt.deviation_path_segments.length > 0
      ? stmt.deviation_path_segments
      : parseAbsoluteSchemaPath(path))[0];
    const own = String(effective.prefix ?? "").replace(/^['"]|['"]$/g, "");
    if (first?.prefix !== own) {
      throw new YangExportError(
        `cannot export deviation '${path}': its target belongs to another module, ` +
          `which the native JSON form of module '${effective.name}' does not carry`
      );
    }
  }
  applyDeviations(effective);
}

const FOREIGN_AUGMENTS = "ietf-yang-structure-ext:foreign-augment-structure";
const FOREIGN_SLOTS = "ietf-yang-structure-ext:foreign-augment-structure-slots";
const STRUCTURE_INDEX = "ietf-yang-structure-ext:structure-index";

function isRfc8791(stmt: YangStatement, name: string): boolean {
  return stmt.resolved_module_name === "ietf-yang-structure-ext" && stmt.resolved_extension_name === name;
}

function foreignAugmentsOf(module: YangModule): YangStatement[] {
  const raw = module.extension_runtime?.[FOREIGN_AUGMENTS];
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.map((item) => (item instanceof YangStatement ? item : new YangStatement(asRecord(item))));
}

function foreignSlotsOf(module: YangModule): number[] {
  const raw = module.extension_runtime?.[FOREIGN_SLOTS];
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((item): item is number => typeof item === "number");
}

function orderedExtensionInvocations(
  module: YangModule,
  typedefNames: Set<string>
): Array<Record<string, unknown>> {
  const kept = extensionInvocationsJson(module.statements, module, typedefNames);
  const foreign = foreignAugmentsOf(module);
  const slots = foreignSlotsOf(module);
  if (foreign.length === 0) {
    return kept;
  }
  const groups = new Map<number, Array<Record<string, unknown>>>();
  foreign.forEach((inv, index) => {
    const slot = slots[index] ?? kept.length;
    const list = groups.get(slot) ?? [];
    list.push(oneExtensionInvocation(inv, module, typedefNames));
    groups.set(slot, list);
  });
  const ordered: Array<Record<string, unknown>> = [];
  kept.forEach((item, index) => {
    ordered.push(...(groups.get(index) ?? []));
    groups.delete(index);
    ordered.push(item);
  });
  ordered.push(...(groups.get(kept.length) ?? []));
  groups.delete(kept.length);
  for (const slot of [...groups.keys()].sort((a, b) => a - b)) {
    ordered.push(...(groups.get(slot) ?? []));
  }
  return ordered;
}

function structureInvocations(module: YangModule): YangStatement[] {
  const found: YangStatement[] = [];
  const seen = new Set<YangStatement>();
  for (const stmt of module.statements) {
    if (isRfc8791(stmt, "structure")) {
      found.push(stmt);
      seen.add(stmt);
    }
  }
  const index = asRecord(module.extension_runtime?.[STRUCTURE_INDEX]);
  for (const stmt of Object.values(index)) {
    if (stmt instanceof YangStatement && !seen.has(stmt) && isRfc8791(stmt, "structure")) {
      found.push(stmt);
    }
  }
  return found;
}

function structureView(module: YangModule): YangModule {
  if (!module.statements.some((stmt) => isRfc8791(stmt, "augment-structure"))) {
    return module;
  }
  const cloned = new YangModule(
    {
      name: module.name,
      yang_version: module.yang_version,
      namespace: module.namespace,
      prefix: module.prefix,
      import_prefixes: module.import_prefixes,
      extensions: module.extensions,
      extension_runtime: {},
      statements: module.statements.map((stmt) => new YangStatement(JSON.parse(JSON.stringify(stmt))))
    },
    module.source
  );
  applyBuiltinExtensionInvocations(cloned, { exportView: true });
  return cloned;
}

function extensionStub(module: YangModule): Record<string, unknown> {
  return {
    module: module.name,
    namespace: module.namespace ?? "",
    prefix: module.prefix ?? "",
    [XYANG_KEYS.extension]: localExtensionDefs(module)
  };
}

function stripAugmentedBy(stmt: YangStatement, exporterName: string): YangStatement | undefined {
  if ((stmt as { augment_structure_module?: string }).augment_structure_module === exporterName) {
    return undefined;
  }
  const cloned = new YangStatement(JSON.parse(JSON.stringify(stmt)));
  cloned.statements = cloned.statements
    .map((child) => stripAugmentedBy(child, exporterName))
    .filter((child): child is YangStatement => child !== undefined);
  return cloned;
}

function addImportedStructures(root: YangModule, imports: Record<string, unknown>): void {
  const seen = new Set<string>();
  const invocations = root.statements.filter((stmt) => isRfc8791(stmt, "augment-structure"));
  for (const saved of foreignAugmentsOf(root)) {
    if (!invocations.includes(saved)) {
      invocations.push(saved);
    }
  }
  for (const inv of invocations) {
    const path = String(inv.argument ?? "");
    if (!path) {
      continue;
    }
    let firstPrefix = "";
    let firstName = "";
    try {
      const first = parseAbsoluteSchemaPath(path)[0];
      firstPrefix = first?.prefix ?? "";
      firstName = first?.name ?? "";
    } catch {
      continue;
    }
    const owner = root.import_prefixes[firstPrefix];
    if (!owner || owner === root || owner.name === root.name) {
      continue;
    }
    const key = extensionImportKey(root, owner);
    if (!imports[key]) {
      imports[key] = {
        module: owner.name,
        namespace: owner.namespace ?? "",
        prefix: owner.prefix ?? ""
      };
    }
    const stub = asRecord(imports[key]);
    const view = structureView(owner);
    for (const structure of structureInvocations(view)) {
      const marker = `${key}:${String(structure.argument ?? "").trim()}`;
      if (seen.has(marker) || marker.endsWith(":") && !firstName) {
        continue;
      }
      seen.add(marker);
      const shadow = new YangStatement(JSON.parse(JSON.stringify(structure)));
      shadow.statements = structure.statements
        .map((child) => stripAugmentedBy(child, root.name ?? ""))
        .filter((child): child is YangStatement => child !== undefined);
      const body = oneExtensionInvocation(shadow, root, new Set());
      const list = Array.isArray(stub[XYANG_KEYS.extensions])
        ? (stub[XYANG_KEYS.extensions] as Array<Record<string, unknown>>)
        : [];
      list.push(body);
      stub[XYANG_KEYS.extensions] = list;
      const prefix = structure.prefix ?? "";
      const definingName = structure.resolved_module_name ?? "";
      const defining = prefix ? owner.import_prefixes?.[prefix] : undefined;
      if (defining && prefix) {
        const nested = asRecord(stub[XYANG_KEYS.imports]);
        if (!nested[prefix]) {
          nested[prefix] = extensionStub(defining);
        }
        stub[XYANG_KEYS.imports] = nested;
      } else if (definingName && prefix) {
        const nested = asRecord(stub[XYANG_KEYS.imports]);
        if (!nested[prefix]) {
          nested[prefix] = {
            module: definingName,
            namespace: "",
            prefix
          };
        }
        stub[XYANG_KEYS.imports] = nested;
      }
    }
  }
}

function featuresJson(module: YangModule): Record<string, unknown> {
  const names = [...module.features].sort();
  if (names.length === 0) {
    return {};
  }
  const out: Record<string, unknown> = {};
  for (const name of names) {
    const body: Record<string, unknown> = {};
    const guards = module.feature_if_features?.[name] ?? [];
    if (guards.length > 0) {
      body["if-features"] = [...guards];
    }
    out[name] = body;
  }
  return out;
}

/** Throws {@link YangExportError} for a construct the native JSON form cannot carry. */
export function generateJsonSchema(module: YangModule): Record<string, unknown> {

  const previous = extensionUses;
  const previousScoped = scopedExportDefs;
  scopedExportDefs = scopedCatalog(module);
  extensionUses = [];
  try {
    return withIdentityExport(module, (used) => generateSchema(module, used));
  } finally {
    extensionUses = previous;
    scopedExportDefs = previousScoped;
  }
}

function generateSchema(module: YangModule, used: IdentityPair[]): Record<string, unknown> {
  // Preserve parse-time AST shape (reversible YANG <-> yang.json) while still
  // emitting a flattened schema view.
  const effectiveModule = expandUses(module);

  if (effectiveModule !== module && module.module_registry && !effectiveModule.module_registry) {
    Object.defineProperty(effectiveModule, "module_registry", { value: module.module_registry, enumerable: false });
  }
  applyOwnAugments(effectiveModule);
  applyOwnDeviations(effectiveModule);
  // Merge a same-module sx:augment-structure. A cross-module one stays an invocation.
  applyBuiltinExtensionInvocations(effectiveModule, { exportView: true });
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

  const defs = {
    ...typedefToSchema(effectiveModule),
    ...scopedTypedefsToSchema(),
    ...identityToSchema(effectiveModule, typedefNames)
  };
  const moduleInvocations = orderedExtensionInvocations(effectiveModule, typedefNames);
  const imports = mergeExtensionImports(module, { ...importsForJson(module, used) }, extensionUses ?? []);
  addImportedStructures(effectiveModule, imports);
  const sortedImports = Object.fromEntries(Object.entries(imports).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));
  if (Object.keys(sortedImports).length > 0) {
    rootXYang[XYANG_KEYS.imports] = sortedImports;
  }
  const extensionDefs = localExtensionDefs(effectiveModule);
  if (Object.keys(extensionDefs).length > 0) {
    rootXYang[XYANG_KEYS.extension] = extensionDefs;
  }
  const features = featuresJson(module);
  if (Object.keys(features).length > 0) {
    rootXYang[XYANG_KEYS.features] = features;
  }
  if (moduleInvocations.length > 0) {
    rootXYang[XYANG_KEYS.extensions] = moduleInvocations;
  }
  assertExtensionsPlaced(effectiveModule);

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
  if (Object.keys(defs).length > 0) {
    schema.$defs = defs;
  }

  return schema;
}
