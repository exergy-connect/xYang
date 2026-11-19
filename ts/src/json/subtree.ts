import { YangExportError } from "../core/errors";
import type { YangModule, YangStatement } from "../core/model";
import { reachableModuleData, stmtIfFeaturesSatisfied } from "../validator/if-feature-eval";
import { parseAbsoluteSchemaPath } from "../core/identifier-ref";
import { expressionIsWithinSubtree } from "../xpath/subtree-dependencies";
import { parseXPath } from "../xpath/parser";
import { resolveTypedef } from "../validator/type-checker";
import { translateXsdRegex } from "../xsd-regex";
import type { XPathAstNode } from "../xpath/ast";
import type { SchemaDiagnostic, SchemaExportResult } from "./generator";

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj => v && typeof v === "object" && !Array.isArray(v) ? v as Obj : {};
const local = (name: string) => name.split(":").pop()!;

function statementAt(module: YangModule, path: readonly string[]): YangStatement | undefined {
  let statements = module.statements;
  let current: YangStatement | undefined;
  const candidates = (items: YangStatement[]): YangStatement[] => items.flatMap(item =>
    item.keyword === "choice" || item.keyword === "case" ? candidates(item.statements) : [item]);
  for (const segment of path) {
    current = candidates(statements).find(item => item.name === segment);
    if (!current) return undefined;
    statements = current.statements;
  }
  return current;
}
function leafrefType(module: YangModule, path: readonly string[]): Obj | undefined {
  const stmt = statementAt(module, path);
  if (!stmt || (stmt.keyword !== "leaf" && stmt.keyword !== "leaf-list")) return undefined;
  let type = obj(stmt.type);
  const seen = new Set<object>();
  while (type.name !== "leafref") {
    if (seen.has(type)) throw new YangExportError(`circular typedef at '/${path.join("/")}'`);
    seen.add(type);
    if (type.name === "union" && Array.isArray(type.types)) {
      const containsLeafref = (member: Obj, visited: Set<object>): boolean => {
        if (member.name === "leafref") return true;
        if (visited.has(member)) throw new YangExportError(`circular typedef at '/${path.join("/")}'`);
        visited.add(member);
        if (member.name === "union" && Array.isArray(member.types)) return member.types.some(raw => containsLeafref(obj(raw), new Set(visited)));
        const nested = resolveTypedef(module, member);
        return nested?.type ? containsLeafref(obj(nested.type), visited) : false;
      };
      if (type.types.some(raw => containsLeafref(obj(raw), new Set()))) {
        throw new YangExportError(`cannot safely project a union containing a leafref at '/${path.join("/")}'`);
      }
    }
    const typedef = resolveTypedef(module, type);
    if (!typedef?.type) return undefined;
    type = obj(typedef.type);
  }
  return type;
}
function leafrefPath(type: Obj): string {
  if (typeof type.path === "string") return type.path;
  const ast = obj(type.path);
  if (ast.kind !== "path" || !Array.isArray(ast.segments)) throw new YangExportError("invalid leafref path");
  if (typeof ast.source === "string") return ast.source;
  const segments = ast.segments.map(raw => {
    const segment = obj(raw);
    if (segment.predicate) throw new YangExportError("cannot safely project a leafref typedef path with predicates");
    return String(segment.step);
  });
  return `${ast.isAbsolute ? "/" : ""}${segments.join("/")}`;
}

/** JSON Schema patterns use ECMAScript syntax; YANG patterns use XSD syntax. */
function translatePatterns(value: unknown): void {
  if (Array.isArray(value)) { for (const item of value) translatePatterns(item); return; }
  if (!value || typeof value !== "object") return;
  const node = value as Obj;
  const patterns = obj(node["x-yang"])["string-patterns"];
  if (Array.isArray(patterns) && patterns.length) {
    const convert = (raw: unknown) => {
      const pattern = String(obj(raw).pattern);
      if (/(?:^|[^\\])(?:\\\\)*\\[dDsSwWiIcCpP]/.test(pattern)) throw new YangExportError("subtree schema cannot portably encode an XSD regex shorthand or Unicode category");
      return translateXsdRegex(pattern).source.replace(
      /\\u\{([0-9A-Fa-f]+)\}/g,
      (_, hex: string) => { const n = parseInt(hex, 16); return n <= 0xffff ? `\\u${hex.padStart(4, "0")}` : String.fromCodePoint(n); }
      );
    };
    if (patterns.length === 1 && !obj(patterns[0])["invert-match"]) node.pattern = convert(patterns[0]);
    else if (Array.isArray(node.allOf)) patterns.forEach((raw, i) => {
      const part = obj((node.allOf as unknown[])[i]);
      if (obj(raw)["invert-match"]) obj(part.not).pattern = convert(raw);
      else part.pattern = convert(raw);
    });
  }
  for (const child of Object.values(node)) translatePatterns(child);
}

/** Resolve data properties through list items and choice branches. */
function children(node: Obj): Obj[] {
  const out = [node];
  if (node.items && typeof node.items === "object") out.push(...children(obj(node.items)));
  for (const value of Object.values(obj(node.properties))) {
    const schema = obj(value);
    if (obj(schema["x-yang"]).type === "choice") out.push(...children(schema));
  }
  for (const k of ["oneOf", "anyOf", "allOf"]) if (Array.isArray(node[k])) {
    for (const branch of node[k] as unknown[]) out.push(...children(obj(branch)));
  }
  return out;
}
function child(node: Obj, name: string): Obj {
  const matches: Obj[] = [];
  for (const parent of children(node)) for (const [key, value] of Object.entries(obj(parent.properties))) {
    if ((key === name || (!name.includes(":") && local(key) === name)) && !matches.some(existing => JSON.stringify(existing) === JSON.stringify(value))) matches.push(obj(value));
  }
  if (matches.length !== 1) throw new YangExportError(`subtree path segment '${name}' ${matches.length ? "is ambiguous" : "was not found"}`);
  return matches[0]!;
}
function lookup(root: Obj, path: readonly string[]): Obj {
  return path.reduce((node, name) => child(node, name), root);
}
function targetPath(expression: string, context: readonly string[]): string[] {
  const ast = parseXPath(expression);
  if (ast.kind !== "path") throw new YangExportError(`cannot resolve leafref '${expression}'`);
  const path = ast.isAbsolute ? [] : [...context];
  for (const step of ast.segments) {
    if (step.step === "..") { if (!path.length) throw new YangExportError(`invalid leafref '${expression}'`); path.pop(); }
    else if (step.step !== ".") {
      if (step.step.includes("*")) throw new YangExportError(`cannot resolve leafref '${expression}'`);
      path.push(local(step.step));
    }
  }
  return path;
}
function supportedPrefixes(expression: string, module: YangModule, bindings: Obj): boolean {
  const visit = (node: XPathAstNode): boolean => {
    if (node.kind === "literal") return true;
    if (node.kind === "binary") return visit(node.left) && visit(node.right);
    if (node.kind === "function") return node.args.every(visit);
    return node.segments.every(s => {
      const prefix = s.step.includes(":") ? s.step.split(":")[0] : undefined;
      return (!prefix || prefix === module.prefix || bindings[prefix] === module.name) && (!s.predicate || visit(s.predicate));
    });
  };
  return visit(parseXPath(expression));
}

function guardsActive(expressions: string[], module: YangModule, enabled: Readonly<Record<string, ReadonlySet<string>>>): boolean {
  const imported = reachableModuleData(module).filter(other => other.name !== module.name);
  for (const expression of expressions) {
    for (const token of expression.match(/[A-Za-z_][A-Za-z0-9_.:-]*/g) ?? []) {
      if (!["and", "or", "not"].includes(token) && !token.includes(":") && imported.some(other => other.features.has(token))) {
        throw new YangExportError(`cannot safely resolve unqualified if-feature '${token}' shared with an imported module`);
      }
    }
  }
  return stmtIfFeaturesSatisfied(expressions, module, enabled);
}

/** Drop enum and bit values whose ``if-feature`` is false. The reversible module schema is left unchanged. */
export function restrictGatedValues(node: unknown, module: YangModule, enabled: Readonly<Record<string, ReadonlySet<string>>>): void {
  if (Array.isArray(node)) {
    for (const item of node) restrictGatedValues(item, module, enabled);
    return;
  }
  if (!node || typeof node !== "object") return;
  const current = node as Obj;
  const meta = obj(current["x-yang"]);
  const entries = meta.enums;
  const values = current.enum;
  if (Array.isArray(entries) && Array.isArray(values)) {
    const drop = new Set<string>();
    const kept: unknown[] = [];
    for (const entry of entries) {
      const item = obj(entry);
      const name = item.name;
      const feats = Array.isArray(item["if-features"])
        ? item["if-features"].filter((feat): feat is string => typeof feat === "string" && feat.length > 0)
        : [];
      if (typeof name === "string" && feats.length > 0 && !guardsActive(feats, module, enabled)) {
        drop.add(name);
        continue;
      }
      kept.push(entry);
    }
    if (drop.size > 0) {
      current.enum = values.filter(value => typeof value !== "string" || !drop.has(value));
      if (kept.some(entry => {
        const item = obj(entry);
        return (Array.isArray(item["if-features"]) && (item["if-features"] as unknown[]).length > 0)
          || (typeof item.description === "string" && item.description.length > 0);
      })) meta.enums = kept;
      else delete meta.enums;
    }
  }
  const bitGuards = meta["bit-if-features"];
  const bits = meta.bits;
  if (bitGuards && typeof bitGuards === "object" && !Array.isArray(bitGuards) && bits && typeof bits === "object" && !Array.isArray(bits)) {
    const disabled = Object.entries(bitGuards as Record<string, unknown>).filter(([, feats]) =>
      Array.isArray(feats) && feats.some(feat => typeof feat === "string" && feat.length > 0)
      && !guardsActive((feats as unknown[]).filter((feat): feat is string => typeof feat === "string"), module, enabled)
    ).map(([name]) => name);
    if (disabled.length > 0) {
      for (const name of disabled) {
        delete (bits as Obj)[name];
        delete (bitGuards as Obj)[name];
      }
      const names = Object.keys(bits as Obj);
      const escaped = names.map(name => name.replace(/[()[\]{}?*+|^$\\.\-&~#\s]/g, "\\$&")).sort((a, b) => b.length - a.length);
      current.pattern = names.length === 0 ? "^$" : `^$|^(?:${escaped.join("|")})(?:\\s+(?:${escaped.join("|")}))*$`;
      if (Object.keys(bitGuards as Obj).length === 0) delete meta["bit-if-features"];
    }
  }
  for (const child of Object.values(current)) restrictGatedValues(child, module, enabled);
}

function descriptionFrom(node: Obj, defs: Obj): string {
  let source = node;
  const ref = node.$ref;
  if (typeof ref === "string" && ref.startsWith("#/$defs/")) {
    const target = obj(defs[ref.slice("#/$defs/".length)]);
    if (Object.keys(target).length > 0) source = target;
  }
  if (source !== node && typeof source.description === "string" && source.description.trim()) return source.description;
  const entries = obj(source["x-yang"]).enums;
  if (!Array.isArray(entries)) return "";
  const lines: string[] = [];
  for (const entry of entries) {
    const item = obj(entry);
    const name = item.name;
    const text = item.description;
    if (typeof name === "string" && name && typeof text === "string" && text.trim()) lines.push(`${name}: ${text.trim()}`);
  }
  return lines.join("\n");
}

function preserveDescriptions(node: unknown, defs: Obj, seen: Set<object>): void {
  if (Array.isArray(node)) {
    for (const item of node) preserveDescriptions(item, defs, seen);
    return;
  }
  if (!node || typeof node !== "object" || seen.has(node)) return;
  seen.add(node);
  const current = node as Obj;
  if (typeof current.description !== "string" || !current.description.trim()) {
    const text = descriptionFrom(current, defs);
    if (text) current.description = text;
  }
  for (const value of Object.values(current)) preserveDescriptions(value, defs, seen);
}

export function projectSubtree(full: Obj, module: YangModule, selection: string, nativeJson = false, available: Obj = full): SchemaExportResult {
  const segments = parseAbsoluteSchemaPath(selection, module.prefix || undefined);
  for (const seg of segments) if (seg.prefix !== module.prefix && seg.prefix !== module.name) {
    throw new YangExportError(`unsupported module prefix '${seg.prefix}' in subtree path '${selection}'`);
  }
  const scope = segments.map(s => s.name);
  const selected = structuredClone(lookup(available, scope));
  const diagnostics: SchemaDiagnostic[] = [];
  const within = (expression: string, path: string[], bindings: Obj) =>
    supportedPrefixes(expression, module, bindings) && expressionIsWithinSubtree(expression, path, scope);
  const report = (path: string[], constraint: string, expression: string, reason = "depends on data outside the selected subtree or cannot be proved local") => {
    const entry = { path: `/${path.join("/")}`, constraint, expression, reason };
    if (!diagnostics.some(item => item.path === entry.path && item.constraint === constraint && item.expression === expression && item.reason === reason)) diagnostics.push(entry);
  };
  const visit = (node: Obj, path: string[], dataNode = true) => {
    const meta = obj(node["x-yang"]);
    const stmt = statementAt(module, path);
    const inheritedLeafref = dataNode ? leafrefType(module, path) : undefined;
    if (inheritedLeafref && meta.type !== "leafref" && (stmt?.keyword === "leaf" || (stmt?.keyword === "leaf-list" && meta.type !== "leaf-list"))) {
      meta.type = "leafref";
      meta.path = leafrefPath(inheritedLeafref);
      meta["require-instance"] = inheritedLeafref.require_instance !== false;
      if (inheritedLeafref.xpath_prefixes) meta["xpath-prefixes"] = inheritedLeafref.xpath_prefixes;
      node["x-yang"] = meta;
    }
    const bindings = obj(meta["xpath-prefixes"]);
    if (Array.isArray(meta.must)) meta.must = meta.must.filter((raw: unknown) => {
      const item = obj(raw), expression = String(item.must ?? "");
      if (within(expression, path, obj(item["xpath-prefixes"]))) return true;
      report(path, "must", expression); return false;
    });
    const when = obj(meta.when);
    if (typeof when.condition === "string" && !within(when.condition, when["evaluate-with-parent-context"] === true ? path.slice(0, -1) : path, obj(when["xpath-prefixes"]))) {
      report(path, "when", when.condition); delete meta.when;
    }
    if (meta.type === "leafref" && typeof meta.path === "string") {
      const expression = meta.path;
      if (!supportedPrefixes(expression, module, bindings)) throw new YangExportError(`cannot resolve leafref '${expression}' outside module`);
      let target = lookup(full, targetPath(expression, path));
      let targetContext = targetPath(expression, path);
      const seen = new Set<string>();
      while (true) {
        const targetMeta = obj(target["x-yang"]);
        const targetType = leafrefType(module, targetContext);
        const next = targetMeta.type === "leafref" ? String(targetMeta.path ?? "") : targetType ? leafrefPath(targetType) : undefined;
        if (next === undefined) break;
        const identity = targetContext.join("/");
        if (seen.has(identity)) throw new YangExportError(`circular leafref '${expression}'`);
        seen.add(identity);
        if (!supportedPrefixes(next, module, obj(targetMeta["xpath-prefixes"] ?? targetType?.xpath_prefixes))) throw new YangExportError(`cannot resolve leafref '${next}' outside module`);
        targetContext = targetPath(next, targetContext);
        target = lookup(full, targetContext);
      }
      for (const key of ["type", "$ref", "enum", "pattern", "minimum", "maximum", "minLength", "maxLength", "anyOf", "oneOf", "allOf", "format", "multipleOf"]) {
        delete node[key]; if (key in target) node[key] = structuredClone(target[key]);
      }
      let targetEnabled = true;
      try { lookup(available, targetPath(expression, path)); } catch { targetEnabled = false; }
      if (!within(expression, path, bindings) || !targetEnabled) {
        meta.type = "leaf"; delete meta.path; delete meta["require-instance"]; delete meta["xpath-prefixes"];
        if (targetEnabled) report(path, "leafref", expression);
        else report(path, "leafref", expression, "target is disabled by feature selection");
      }
    }
    for (const [name, value] of Object.entries(obj(node.properties))) visit(obj(value), [...path, local(name)]);
    if (node.items && typeof node.items === "object") visit(obj(node.items), path, meta.type === "leaf-list");
    for (const key of ["oneOf", "anyOf", "allOf"]) if (Array.isArray(node[key])) for (const branch of node[key] as unknown[]) visit(obj(branch), path, false);
    // Native encoding accepts a keyed object as well as an array for single-key lists.
    if (nativeJson && meta.type === "list" && typeof meta.key === "string" && meta.key.trim().split(/\s+/).length === 1) {
      const item = obj(node.items);
      const keyedItem = structuredClone(item);
      if (Array.isArray(keyedItem.required)) keyedItem.required = keyedItem.required.filter(k => local(String(k)) !== local(String(meta.key)));
      const array: Obj = { type: "array", items: item };
      for (const k of ["minItems", "maxItems"]) if (k in node) { array[k] = node[k]; delete node[k]; }
      delete node.type; delete node.items;
      const keyed: Obj = { type: "object", additionalProperties: keyedItem };
      if (typeof array.minItems === "number") keyed.minProperties = array.minItems;
      if (typeof array.maxItems === "number") keyed.maxProperties = array.maxItems;
      node.anyOf = [array, keyed];
    }
  };
  visit(selected, scope);
  const rootMeta = obj(selected["x-yang"]);
  rootMeta["subtree-path"] = selection;
  selected["x-yang"] = rootMeta;
  selected.$schema = full.$schema;
  selected.$id = full.$id;
  if (available.$defs) selected.$defs = structuredClone(available.$defs);
  translatePatterns(selected);
  preserveDescriptions(selected, obj(selected.$defs), new Set());
  return { schema: selected, diagnostics };
}
