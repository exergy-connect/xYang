// ts/src/shims/node-path-browser.ts
function resolve(...parts) {
  const joined = parts.filter((p) => p && p.length > 0).join("/");
  return joined.replace(/\/+/g, "/").replace(/^\.\//, "") || ".";
}
function dirname(p) {
  const s = p.replace(/\/+$/, "");
  if (s.length === 0) {
    return ".";
  }
  const i = s.lastIndexOf("/");
  if (i <= 0) {
    return ".";
  }
  return s.slice(0, i) || "/";
}

// ts/src/core/errors.ts
var YangError = class extends Error {
  constructor(message) {
    super(message);
    this.name = "YangError";
  }
};
var YangSyntaxError = class extends SyntaxError {
  messageText;
  line_num;
  line;
  context_lines;
  filename;
  constructor(message, options = {}) {
    const { line_num, line, context_lines = [], filename } = options;
    const parts = [];
    if (filename) {
      parts.push(`${filename}:`);
    }
    if (line_num) {
      parts.push(`${line_num}:`);
    }
    parts.push(message);
    let rendered = parts.join(" ");
    if (context_lines.length > 0) {
      rendered += "\n";
      for (const [ctxLineNum, ctxLine] of context_lines) {
        const marker = ctxLineNum === line_num ? ">>> " : "    ";
        rendered += `${marker}${String(ctxLineNum).padStart(4, " ")} | ${ctxLine}
`;
      }
      if (line_num && line) {
        rendered += `     ${" ".repeat(String(line_num).length + 3)}${"^".repeat(Math.max(1, line.trim().length))}`;
      }
    }
    super(rendered);
    this.name = "YangSyntaxError";
    this.messageText = message;
    this.line_num = line_num;
    this.line = line;
    this.context_lines = context_lines;
    this.filename = filename;
  }
  formatHeadline() {
    const parts = [];
    if (this.filename) {
      parts.push(`${this.filename}:`);
    }
    if (this.line_num !== void 0) {
      parts.push(`${this.line_num}:`);
    }
    parts.push(this.messageText);
    return parts.join(" ");
  }
  toString() {
    return this.formatHeadline();
  }
};
var YangSemanticError = class extends YangError {
  constructor(message) {
    super(message);
    this.name = "YangSemanticError";
  }
};
var YangRefineTargetNotFoundError = class extends YangSemanticError {
  target_path;
  constructor(target_path) {
    super(`Refine target path matches no node in the used grouping: '${target_path}'`);
    this.name = "YangRefineTargetNotFoundError";
    this.target_path = target_path;
  }
};
var YangCircularUsesError = class extends YangSemanticError {
  prefix_chain;
  repeated;
  constructor(prefix_chain, repeated) {
    const cycle = [...prefix_chain, repeated].join(" -> ");
    super(
      `Circular uses chain: groupings are expanded at compile-time and this cycle would not terminate (${cycle}). Restructure groupings to break the cycle.`
    );
    this.name = "YangCircularUsesError";
    this.prefix_chain = [...prefix_chain];
    this.repeated = repeated;
  }
};
var XPathSyntaxError = class extends Error {
  messageText;
  position;
  expression;
  constructor(message, options = {}) {
    const { position, expression, context_before = 10, context_after = 10 } = options;
    if (expression !== void 0 && position !== void 0) {
      const start = Math.max(0, position - context_before);
      const end = Math.min(expression.length, position + context_after);
      const context = expression.slice(start, end);
      const pointerPos = position - start;
      const parts = [message, `
Expression: ${context}`, `           ${" ".repeat(pointerPos)}^`];
      if (position < expression.length) {
        parts.push(`Position: ${position} (character: ${JSON.stringify(expression[position])})`);
      } else {
        parts.push(`Position: ${position} (end of expression)`);
      }
      super(parts.join("\n"));
    } else {
      super(message);
    }
    this.name = "XPathSyntaxError";
    this.messageText = message;
    this.position = position;
    this.expression = expression;
  }
  toString() {
    return this.messageText;
  }
};
var XPathEvaluationError = class extends Error {
  messageText;
  constructor(message) {
    super(message);
    this.name = "XPathEvaluationError";
    this.messageText = message;
  }
  toString() {
    return this.messageText;
  }
};
var UnsupportedXPathError = class extends Error {
  messageText;
  expression;
  construct;
  code;
  constructor(message, options = {}) {
    const parts = [message];
    if (options.construct) {
      parts.push(`Unsupported construct: ${options.construct}`);
    }
    if (options.expression) {
      parts.push(`Expression: ${options.expression}`);
    }
    super(parts.join("\n"));
    this.name = "UnsupportedXPathError";
    this.messageText = message;
    this.expression = options.expression;
    this.construct = options.construct;
    this.code = options.code;
  }
  toString() {
    return this.messageText;
  }
};
var YangExportError = class extends Error {
  constructor(message) {
    super(message);
    this.name = "YangExportError";
  }
};

// ts/src/json/type-constants.ts
var JSON_SCHEMA_DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema";
var JSON_TYPE_STRING = "string";
var JSON_TYPE_INTEGER = "integer";
var JSON_TYPE_NUMBER = "number";
var JSON_TYPE_BOOLEAN = "boolean";
var JSON_TYPE_OBJECT = "object";
var JSON_TYPE_ARRAY = "array";
var JSON_TYPE_NULL = "null";
var JSON_TYPE_FREE_FORM = [
  JSON_TYPE_STRING,
  JSON_TYPE_NUMBER,
  JSON_TYPE_BOOLEAN,
  JSON_TYPE_OBJECT,
  JSON_TYPE_ARRAY,
  JSON_TYPE_NULL
];

// ts/src/core/identifier-ref.ts
function formatIdentifierRef(ref) {
  return ref.prefix ? `${ref.prefix}:${ref.name}` : ref.name;
}
function parseIdentifierRefAtom(atom) {
  const idx = atom.indexOf(":");
  if (idx <= 0 || idx >= atom.length - 1) {
    return { name: atom };
  }
  return { prefix: atom.slice(0, idx), name: atom.slice(idx + 1) };
}
function parseAbsoluteSchemaPath(path, defaultPrefix) {
  const raw = path.replace(/^["']|["']$/g, "");
  if (!raw.startsWith("/")) {
    throw new Error(`Schema path must be absolute, got '${path}'`);
  }
  const parts = raw.slice(1).split("/").map((p) => p.trim()).filter((p) => p.length > 0);
  if (parts.length === 0) {
    throw new Error(`Empty schema path: '${path}'`);
  }
  return parts.map((seg) => {
    const ref = parseIdentifierRefAtom(seg);
    if (ref.prefix) return ref;
    if (seg.includes(":") || !defaultPrefix) {
      throw new Error(`Invalid schema path segment '${seg}': expected 'prefix:identifier'`);
    }
    return { prefix: defaultPrefix, name: ref.name };
  });
}
function coerceIdentifierRef(value) {
  if (typeof value === "string" && value.length > 0) {
    return parseIdentifierRefAtom(value);
  }
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const o = value;
    if (typeof o.name === "string" && o.name.length > 0) {
      return typeof o.prefix === "string" && o.prefix.length > 0 ? { prefix: o.prefix, name: o.name } : { name: o.name };
    }
  }
  return void 0;
}

// ts/src/validator/if-feature-eval.ts
function stripQuotes(prefix) {
  return String(prefix ?? "").replace(/^['"]|['"]$/g, "");
}
function moduleName(m) {
  return String(m.name ?? "");
}
function declaredFeatures(m) {
  const f = m.features;
  if (f instanceof Set) {
    return new Set(f);
  }
  if (Array.isArray(f)) {
    return new Set(f);
  }
  return /* @__PURE__ */ new Set();
}
function resolvePrefixedModule(ctx, prefix, file) {
  const own = stripQuotes(ctx.prefix);
  if (prefix === own) {
    return ctx;
  }
  const maps = ctx.file_imports;
  const imports = file ? maps?.[file] : ctx.import_prefixes;
  const hit = imports?.[prefix];
  if (hit && typeof hit === "object") {
    return hit;
  }
  return void 0;
}
function reachableModuleData(root) {
  const out = [];
  const seen = /* @__PURE__ */ new Set();
  const walk = (m) => {
    if (seen.has(m)) {
      return;
    }
    seen.add(m);
    out.push(m);
    const im = m.import_prefixes;
    if (!im) {
      return;
    }
    for (const v of Object.values(im)) {
      if (v && typeof v === "object") {
        walk(v);
      }
    }
    const files = m.file_imports;
    if (!files) {
      return;
    }
    for (const map of Object.values(files)) {
      for (const v of Object.values(map ?? {})) {
        if (v && typeof v === "object") {
          walk(v);
        }
      }
    }
  };
  walk(root);
  return out;
}
function featureIsSupported(ctxModule, enabledByModule, ref, file) {
  const id = typeof ref === "string" ? parseIdentifierRefAtom(ref) : ref;
  let mod;
  if (id.prefix) {
    const resolved = resolvePrefixedModule(ctxModule, id.prefix, file);
    if (!resolved) {
      return false;
    }
    mod = resolved;
  } else {
    mod = ctxModule;
  }
  const fname = id.name;
  if (!declaredFeatures(mod).has(fname)) {
    return false;
  }
  const enabled = enabledByModule[moduleName(mod)];
  if (!enabled) {
    return false;
  }
  return enabled.has(fname);
}
function tokenize(expr) {
  const tokens = [];
  let i = 0;
  const n = expr.length;
  while (i < n) {
    const c = expr[i];
    if (/\s/.test(c)) {
      i += 1;
      continue;
    }
    if (c === "(" || c === ")") {
      tokens.push(c);
      i += 1;
      continue;
    }
    let j = i;
    while (j < n && !/\s/.test(expr[j]) && expr[j] !== "(" && expr[j] !== ")") {
      j += 1;
    }
    tokens.push(expr.slice(i, j));
    i = j;
  }
  return tokens;
}
var IfFeatureParser = class {
  constructor(toks, ctx, enabled, file) {
    this.toks = toks;
    this.ctx = ctx;
    this.enabled = enabled;
    this.file = file;
  }
  toks;
  ctx;
  enabled;
  file;
  i = 0;
  peek() {
    return this.toks[this.i];
  }
  eat(expected) {
    const t = this.peek();
    if (t === void 0) {
      throw new Error("unexpected end of expression");
    }
    if (expected !== void 0 && t !== expected) {
      throw new Error(`expected ${expected}, got ${t}`);
    }
    this.i += 1;
    return t;
  }
  parseExpr() {
    let left = this.parseTerm();
    while (this.peek() === "or") {
      this.eat("or");
      const right = this.parseExpr();
      left = left || right;
    }
    return left;
  }
  parseTerm() {
    let left = this.parseFactor();
    while (this.peek() === "and") {
      this.eat("and");
      const right = this.parseTerm();
      left = left && right;
    }
    return left;
  }
  parseFactor() {
    const t = this.peek();
    if (t === "not") {
      this.eat("not");
      return !this.parseFactor();
    }
    if (t === "(") {
      this.eat("(");
      const v = this.parseExpr();
      this.eat(")");
      return v;
    }
    if (t === void 0) {
      throw new Error("unexpected end of expression");
    }
    this.eat();
    return featureIsSupported(this.ctx, this.enabled, t, this.file);
  }
  atEnd() {
    return this.i >= this.toks.length;
  }
};
function evaluateIfFeatureExpression(expr, ctxModule, enabledByModule, file) {
  const trimmed = expr.trim();
  if (!trimmed) {
    return false;
  }
  try {
    const p = new IfFeatureParser(tokenize(trimmed), ctxModule, enabledByModule, file);
    const out = p.parseExpr();
    if (!p.atEnd()) {
      return false;
    }
    return out;
  } catch {
    return false;
  }
}
function stmtIfFeaturesSatisfied(ifFeatures, ctxModule, enabledByModule, file) {
  if (!ifFeatures || ifFeatures.length === 0) {
    return true;
  }
  return ifFeatures.every((e) => evaluateIfFeatureExpression(e, ctxModule, enabledByModule, file));
}
function normalizeOverride(override) {
  if (override == null) {
    return null;
  }
  if (override instanceof Map) {
    return new Map(override);
  }
  return new Map(Object.entries(override));
}
function prunePerFeatureIfFeatures(modules, enabled) {
  let changed = true;
  while (changed) {
    changed = false;
    const frozen = {};
    for (const [mn, s] of Object.entries(enabled)) {
      frozen[mn] = new Set(s);
    }
    for (const m of modules) {
      const mn = moduleName(m);
      const mutable = enabled[mn];
      if (!mutable) {
        continue;
      }
      const fif = m.feature_if_features;
      for (const fname of [...mutable]) {
        const reqs = fif?.[fname];
        if (!reqs?.length) {
          continue;
        }
        if (!stmtIfFeaturesSatisfied(reqs, m, frozen)) {
          mutable.delete(fname);
          changed = true;
        }
      }
    }
  }
  const out = {};
  for (const [k, v] of Object.entries(enabled)) {
    out[k] = new Set(v);
  }
  return out;
}
function buildEnabledFeaturesMap(root, override) {
  const modules = reachableModuleData(root);
  const ov = normalizeOverride(override);
  const enabled = {};
  for (const m of modules) {
    const mn = moduleName(m);
    const declared = declaredFeatures(m);
    if (ov === null || !ov.has(mn)) {
      enabled[mn] = new Set(declared);
    } else {
      enabled[mn] = new Set(ov.get(mn) ?? []);
    }
  }
  return prunePerFeatureIfFeatures(modules, enabled);
}

// ts/src/identity-graph.ts
function getIdentities(mod) {
  const raw = mod.identities;
  if (!raw || typeof raw !== "object") {
    return {};
  }
  return raw;
}
function asBaseRef(base) {
  if (typeof base === "string") {
    return parseIdentifierRefAtom(base);
  }
  return base.prefix ? { prefix: base.prefix, name: base.name } : { name: base.name };
}
function resolvePrefixedModuleData(importer, prefix, file) {
  return resolvePrefixedModule(importer, prefix, file);
}
function resolveIdentityQnamePair(importer, qname) {
  const ref = parseIdentifierRefAtom(qname);
  if (!ref.prefix) {
    return null;
  }
  return resolveIdentityBaseRef(importer, ref);
}
function resolveIdentityValue(moduleData, value) {
  if (typeof value !== "string" || value.length === 0) {
    return null;
  }
  const colon = value.indexOf(":");
  let target = moduleData;
  let local2 = value;
  if (colon >= 0) {
    const modName = value.slice(0, colon);
    local2 = value.slice(colon + 1);
    if (modName !== moduleData.name) {
      const imported = [
        ...Object.values(moduleData.import_prefixes),
        ...Object.values(moduleData.file_imports ?? {}).flatMap((map) => Object.values(map ?? {}))
      ];
      target = imported.find((m) => m && typeof m === "object" && m.name === modName);
    }
  }
  if (!target || !(local2 in getIdentities(target))) {
    return null;
  }
  return { mod: target, local: local2 };
}
function identityrefValueValid(moduleData, value, bases, baseScope = moduleData) {
  if (bases.length === 0) {
    return false;
  }
  const v = resolveIdentityValue(moduleData, value);
  if (!v) {
    return false;
  }
  const closure = identityAncestorClosure(v.mod, v.local);
  return bases.every((b) => {
    const br = resolveIdentityBaseRef(baseScope, b);
    return br !== null && pairInPairs(br, closure);
  });
}
function resolveIdentityBaseRef(fromMod, base, file) {
  const ref = asBaseRef(base);
  if (ref.prefix) {
    const m = resolvePrefixedModuleData(fromMod, ref.prefix, file);
    if (!m || !(ref.name in getIdentities(m))) {
      return null;
    }
    return { mod: m, local: ref.name };
  }
  if (ref.name in getIdentities(fromMod)) {
    return { mod: fromMod, local: ref.name };
  }
  return null;
}
function pairEquals(a, b) {
  return a.mod === b.mod && a.local === b.local;
}
function pairInPairs(p, pairs) {
  return pairs.some((x) => pairEquals(x, p));
}
var moduleSlot = /* @__PURE__ */ new WeakMap();
var nextModuleSlot = 1;
function moduleId(mod) {
  let id = moduleSlot.get(mod);
  if (id === void 0) {
    id = nextModuleSlot;
    nextModuleSlot += 1;
    moduleSlot.set(mod, id);
  }
  return id;
}
function pairKey(p) {
  return `${moduleId(p.mod)}:${p.local}`;
}
function identityAncestorClosure(startMod, startName) {
  const start = { mod: startMod, local: startName };
  const out = [];
  const seen = /* @__PURE__ */ new Set();
  const stack = [start];
  while (stack.length > 0) {
    const cur = stack.pop();
    const key2 = pairKey(cur);
    if (seen.has(key2)) {
      continue;
    }
    seen.add(key2);
    out.push(cur);
    const stmt = getIdentities(cur.mod)[cur.local];
    if (!stmt?.bases) {
      continue;
    }
    for (const b of stmt.bases) {
      const parent2 = resolveIdentityBaseRef(cur.mod, b, stmt.included_from);
      if (parent2) {
        stack.push(parent2);
      }
    }
  }
  return out;
}
function isDerivedFromStrictQNames(importer, vQ, tQ) {
  const v = resolveIdentityValue(importer, vQ);
  const t = resolveIdentityQnamePair(importer, tQ);
  if (!v || !t) {
    return false;
  }
  const ancestors = identityAncestorClosure(v.mod, v.local).filter((p) => !pairEquals(p, v));
  return pairInPairs(t, ancestors);
}
function isDerivedFromOrSelfQNames(importer, vQ, tQ) {
  const v = resolveIdentityValue(importer, vQ);
  const t = resolveIdentityQnamePair(importer, tQ);
  if (!v || !t) {
    return false;
  }
  if (pairEquals(v, t)) {
    return true;
  }
  return pairInPairs(t, identityAncestorClosure(v.mod, v.local));
}

// ts/src/json/schema-keys.ts
var YANG_SCHEMA_KEYS = {
  xYang: "x-yang"
};
var XYANG_KEYS = {
  config: "config",
  /** Module-level RPC definitions (RFC 7950 §7.14), keyed by RPC name. */
  rpcs: "rpcs",
  /** Actions of a container or list (RFC 7950 §7.15), keyed by action name; same shape as `rpcs`. */
  actions: "actions",
  /** `{prefix: module}` for the prefixed steps of a leafref `path`, `must` or `when` (RFC 7950 §6.4.1). */
  xpathPrefixes: "xpath-prefixes",
  /** `{key: module stub}` of the imported modules the identities of this module derive from (RFC 7950 §7.18.2). */
  imports: "imports",
  /** Identities of an `imports` stub, keyed by name. */
  identities: "identities",
  /** Extension definitions (RFC 7950 §7.19) of this module, keyed by name. */
  extension: "extension",
  /** Invocations on this node, in source order: `{name, argument?, ...}`. `name` is `prefix:ext`. */
  extensions: "extensions",
  argument: "argument",
  yinElement: "yin-element",
  reference: "reference",
  /** Nested statements of an invocation: `{extension}` or `{node, schema}`. */
  body: "body",
  /** Declared feature names. A value is `{}` or `{ "if-features": [...] }`. */
  features: "features",
  /** Absolute path of the `sx:augment-structure` that added this node. */
  augmentStructure: "augment-structure"
};

// ts/src/json/identity-export.ts
var active;
function withIdentityExport(root, fn) {
  const previous = active;
  const current = { root, used: [] };
  active = current;
  try {
    return fn(current.used);
  } finally {
    active = previous;
  }
}
function ownPrefix(module) {
  return String(module.prefix ?? "").replace(/^['"]|['"]$/g, "");
}
function importKey(root, module) {
  for (const [prefix, imported] of Object.entries(root.import_prefixes)) {
    if (imported === module || imported.name === module.name) {
      return prefix;
    }
  }
  const name = module.name ?? "";
  if (name in root.import_prefixes || name === ownPrefix(root)) {
    throw new YangExportError(
      `cannot export identities of module '${name}': the name is also a prefix of module '${root.name}'`
    );
  }
  return name;
}
function scopeModule(root, scopeName) {
  if (typeof scopeName !== "string" || scopeName === "" || scopeName === root.name) {
    return root;
  }
  const loaded2 = root.module_registry?.[scopeName];
  if (!loaded2) {
    throw new YangExportError(`type is written in module '${scopeName}', which is not loaded`);
  }
  return loaded2;
}
function identityBaseForJson(base, scope, root) {
  const parsed = coerceIdentifierRef(base);
  const label = parsed ? formatIdentifierRef(parsed) : String(base);
  const pair = parsed ? resolveIdentityBaseRef(scope, parsed) : null;
  if (!pair) {
    throw new YangExportError(`cannot export identity base '${label}': it does not resolve in module '${scope.name}'`);
  }
  if (pair.mod.name === root.name) {
    return { base: pair.local, ref: `#/$defs/${pair.local}` };
  }
  active?.used.push(pair);
  const key2 = importKey(root, pair.mod);
  return {
    base: `${key2}:${pair.local}`,
    ref: `#/${YANG_SCHEMA_KEYS.xYang}/${XYANG_KEYS.imports}/${key2}/${XYANG_KEYS.identities}/${pair.local}`
  };
}
function identityrefSchema(typeShape) {
  const rawBases = Array.isArray(typeShape.identityref_bases) ? typeShape.identityref_bases : [];
  if (rawBases.length === 0) {
    return { type: "string" };
  }
  if (!active) {
    throw new YangExportError("cannot export an identityref outside generateJsonSchema");
  }
  const scope = scopeModule(active.root, typeShape.scope_module);
  const exported = rawBases.map((b) => identityBaseForJson(b, scope, active.root));
  const xYang = { type: "identityref", bases: exported.map((e) => e.base) };
  if (exported.length === 1) {
    return { $ref: exported[0].ref, [YANG_SCHEMA_KEYS.xYang]: xYang };
  }
  return { allOf: exported.map((e) => ({ $ref: e.ref })), [YANG_SCHEMA_KEYS.xYang]: xYang };
}
function basesText(bases) {
  return (Array.isArray(bases) ? bases : []).map((b) => coerceIdentifierRef(b)).filter((b) => Boolean(b)).map((b) => formatIdentifierRef(b));
}
function identityDef(module, name, only) {
  const identities = module.identities;
  const children2 = {};
  for (const [id, info] of Object.entries(identities)) {
    for (const base of basesText(info?.bases)) {
      (children2[base] ??= []).push(id);
    }
  }
  const out = /* @__PURE__ */ new Set([name]);
  const stack = [...children2[name] ?? []];
  while (stack.length > 0) {
    const next = stack.pop();
    if (!out.has(next)) {
      out.add(next);
      stack.push(...children2[next] ?? []);
    }
  }
  const prefix = ownPrefix(module);
  const names = [...out].filter((n) => !only || only.has(n)).sort();
  const bases = basesText(identities[name]?.bases);
  const description = identities[name]?.description;
  const ifFeatures = identities[name]?.if_features ?? [];
  return {
    type: "string",
    enum: names.map((n) => `${prefix}:${n}`),
    ...typeof description === "string" && description.length > 0 ? { description } : {},
    [YANG_SCHEMA_KEYS.xYang]: {
      type: "identity",
      bases,
      ...ifFeatures.length > 0 ? { "if-features": [...ifFeatures] } : {}
    }
  };
}
function stub(module, names) {
  const mine = names.get(module.name ?? "");
  const identities = {};
  const imports = {};
  const raw = module.identities;
  for (const name of [...mine].sort()) {
    identities[name] = identityDef(module, name, mine);
    for (const base of Array.isArray(raw[name]?.bases) ? raw[name].bases : []) {
      const ref = coerceIdentifierRef(base);
      const pair = ref ? resolveIdentityBaseRef(module, ref) : null;
      if (!ref || !pair) {
        throw new YangExportError(
          `cannot export identity '${name}' of module '${module.name}': base '${String(base)}' does not resolve there`
        );
      }
      if (pair.mod.name !== module.name) {
        imports[ref.prefix] = stub(pair.mod, names);
      }
    }
  }
  const sortedImports = Object.fromEntries(Object.entries(imports).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0));
  return {
    module: module.name,
    namespace: module.namespace ?? "",
    prefix: module.prefix ?? "",
    ...Object.keys(sortedImports).length > 0 ? { [XYANG_KEYS.imports]: sortedImports } : {},
    [XYANG_KEYS.identities]: identities
  };
}
function importsForJson(root, used) {
  const usedKeys = new Set(used.map((p) => `${p.mod.name}\0${p.local}`));
  const own = root.identities;
  for (const [name, info] of Object.entries(own)) {
    for (const base of Array.isArray(info?.bases) ? info.bases : []) {
      const ref = coerceIdentifierRef(base);
      if (!ref || !resolveIdentityBaseRef(root, ref)) {
        throw new YangExportError(
          `cannot export identity '${name}': base '${ref ? formatIdentifierRef(ref) : String(base)}' does not resolve in module '${root.name}'`
        );
      }
    }
  }
  const names = /* @__PURE__ */ new Map();
  const need = (pairs) => {
    for (const p of pairs) {
      const key2 = p.mod.name ?? "";
      if (!names.has(key2)) names.set(key2, /* @__PURE__ */ new Set());
      names.get(key2).add(p.local);
    }
  };
  const candidates = Object.keys(own).map((local2) => ({ mod: root, local: local2 }));
  for (const imported of Object.values(root.import_prefixes)) {
    for (const local2 of Object.keys(imported.identities)) {
      candidates.push({ mod: imported, local: local2 });
    }
  }
  for (const c of candidates) {
    const closure = identityAncestorClosure(c.mod, c.local);
    if (c.mod === root || closure.some((p) => usedKeys.has(`${p.mod.name}\0${p.local}`))) {
      need(closure);
    }
  }
  need(used);
  names.delete(root.name ?? "");
  const out = {};
  for (const module of [...Object.values(root.import_prefixes), ...used.map((p) => p.mod)]) {
    if (names.has(module.name ?? "")) {
      out[importKey(root, module)] = stub(module, names);
    }
  }
  return Object.fromEntries(Object.entries(out).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0));
}

// ts/src/types/registry.ts
var INT8 = "int8";
var INT16 = "int16";
var INT32 = "int32";
var INT64 = "int64";
var UINT8 = "uint8";
var UINT16 = "uint16";
var UINT32 = "uint32";
var UINT64 = "uint64";
var DECIMAL64 = "decimal64";
var STRING = "string";
var BOOLEAN = "boolean";
var EMPTY = "empty";
var ENUMERATION = "enumeration";
var BITS = "bits";
var BINARY = "binary";
var UNION = "union";
var LEAFREF = "leafref";
var IDENTITYREF = "identityref";
var INSTANCE_IDENTIFIER = "instance-identifier";
var INT64_PATTERN = "^-?[0-9]+$";
var UINT64_PATTERN = "^[0-9]+$";
var DECIMAL_PATTERN = "^-?[0-9]+(\\.[0-9]+)?$";
var INT64_MIN_TEXT = "-9223372036854775808";
var INT64_MAX_TEXT = "9223372036854775807";
var UINT64_MAX_TEXT = "18446744073709551615";
var table = /* @__PURE__ */ new Map();
function define(spec) {
  const builtin = {
    ...spec,
    toSchema(typeShape, nativeJson = false) {
      return emitSchema(builtin, typeShape, nativeJson);
    },
    fromSchema(fragment) {
      return readSchema(builtin, fragment);
    },
    checkValue(value, typeShape) {
      return checkBuiltin(builtin, value, typeShape);
    }
  };
  table.set(builtin.name, builtin);
  return builtin;
}
function integer(name, bounds, boundsText, jsonEncoding, pattern) {
  return define({ name, jsonEncoding, bounds, boundsText, pattern });
}
integer(INT8, [-128, 127], ["-128", "127"], "number", null);
integer(INT16, [-32768, 32767], ["-32768", "32767"], "number", null);
integer(INT32, [-2147483648, 2147483647], ["-2147483648", "2147483647"], "number", null);
integer(
  INT64,
  [-9223372036854776e3, 9223372036854776e3],
  [INT64_MIN_TEXT, INT64_MAX_TEXT],
  "string-number",
  INT64_PATTERN
);
integer(UINT8, [0, 255], ["0", "255"], "number", null);
integer(UINT16, [0, 65535], ["0", "65535"], "number", null);
integer(UINT32, [0, 4294967295], ["0", "4294967295"], "number", null);
integer(UINT64, [0, 18446744073709552e3], ["0", UINT64_MAX_TEXT], "string-number", UINT64_PATTERN);
define({ name: DECIMAL64, jsonEncoding: "string-number", bounds: null, boundsText: null, pattern: DECIMAL_PATTERN });
define({ name: STRING, jsonEncoding: "string", bounds: null, boundsText: null, pattern: null });
define({ name: BOOLEAN, jsonEncoding: "boolean", bounds: null, boundsText: null, pattern: null });
define({ name: EMPTY, jsonEncoding: "empty", bounds: null, boundsText: null, pattern: null });
define({ name: ENUMERATION, jsonEncoding: "string", bounds: null, boundsText: null, pattern: null });
define({ name: BITS, jsonEncoding: "string", bounds: null, boundsText: null, pattern: null });
define({ name: BINARY, jsonEncoding: "string", bounds: null, boundsText: null, pattern: null });
define({ name: UNION, jsonEncoding: "string", bounds: null, boundsText: null, pattern: null });
define({ name: LEAFREF, jsonEncoding: "string", bounds: null, boundsText: null, pattern: null });
define({ name: IDENTITYREF, jsonEncoding: "string", bounds: null, boundsText: null, pattern: null });
define({ name: INSTANCE_IDENTIFIER, jsonEncoding: "string", bounds: null, boundsText: null, pattern: null });
var REGISTRY = Object.fromEntries(table);
var TYPE_KINDS = {
  [STRING]: "string",
  [BINARY]: "binary",
  [DECIMAL64]: "decimal",
  [ENUMERATION]: "enumeration",
  [BITS]: "bits",
  [UNION]: "union",
  [LEAFREF]: "leafref",
  [IDENTITYREF]: "identityref",
  [INSTANCE_IDENTIFIER]: "instance-identifier",
  [BOOLEAN]: "plain",
  [EMPTY]: "plain",
  integer: "numeric",
  number: "decimal"
};
function typeStatementKind(name, prefix) {
  if (prefix) return "derived";
  if (Object.prototype.hasOwnProperty.call(REGISTRY, name) && REGISTRY[name].bounds) return "numeric";
  return TYPE_KINDS[name] ?? "derived";
}
var YANG_INTEGER_BOUNDS = Object.fromEntries(
  [...table.values()].filter((spec) => spec.bounds).map((spec) => [spec.name, spec.bounds])
);
var YANG_INTEGER_BUILTIN_NAMES = new Set(Object.keys(YANG_INTEGER_BOUNDS));
var QUOTED_INTEGER_NAMES = new Set(
  [...table.values()].filter((spec) => spec.jsonEncoding === "string-number" && spec.bounds).map((spec) => spec.name)
);
var NUMBER_INTEGER_NAMES = new Set(
  [...table.values()].filter((spec) => spec.jsonEncoding === "number").map((spec) => spec.name)
);
var DECIMAL_TYPE_NAMES = /* @__PURE__ */ new Set([DECIMAL64, JSON_TYPE_NUMBER]);
var STRINGISH_NAMES = new Set(
  [...table.values()].filter((spec) => spec.jsonEncoding === "string" && spec.name !== UNION).map((spec) => spec.name)
);
function isStringNumberBuiltin(name) {
  return REGISTRY[name]?.jsonEncoding === "string-number";
}
function isQuotedInteger(name) {
  const spec = REGISTRY[name];
  return spec?.jsonEncoding === "string-number" && spec.bounds != null;
}
function signedNames() {
  return [...table.values()].filter((spec) => spec.bounds != null && spec.bounds[0] < 0).map((spec) => spec.name);
}
function unsignedThenSigned() {
  const unsigned = [...table.values()].filter((spec) => spec.bounds != null && spec.bounds[0] >= 0).map((spec) => spec.name);
  return [...unsigned, ...signedNames()];
}
function parseRange(rangeStr) {
  const parts = rangeStr.split("..");
  const out = {};
  const rawLo = (parts[0] ?? "").trim();
  const rawHi = (parts[1] ?? "").trim();
  if (rawLo && rawLo.toLowerCase() !== "min") {
    const lo = Number.parseInt(rawLo, 10);
    if (!Number.isNaN(lo)) {
      out.lo = lo;
    }
  }
  if (rawHi && rawHi.toLowerCase() !== "max") {
    const hi = Number.parseInt(rawHi, 10);
    if (!Number.isNaN(hi)) {
      out.hi = hi;
    }
  }
  return out;
}
function jsonIntegerBoundsForBuiltin(yangType, rangeStr) {
  const bounds = YANG_INTEGER_BOUNDS[yangType];
  if (!bounds) {
    return {};
  }
  if (!rangeStr) {
    return { minimum: bounds[0], maximum: bounds[1] };
  }
  const { lo, hi } = parseRange(rangeStr);
  const parts = rangeStr.split("..");
  const loS = (parts[0] ?? "").trim();
  const hiS = (parts[1] ?? "").trim();
  const out = {};
  if (loS.toLowerCase() === "min") {
    out.minimum = bounds[0];
  } else if (lo !== void 0) {
    out.minimum = lo;
  }
  if (rangeStr.includes("..") && hiS.toLowerCase() === "max") {
    out.maximum = bounds[1];
  } else if (hi !== void 0) {
    out.maximum = hi;
  }
  return out;
}
function coerceInt(value) {
  if (value === null || value === void 0) {
    return void 0;
  }
  if (typeof value === "number" && Number.isInteger(value)) {
    return value;
  }
  return void 0;
}
function narrowestIntegerBuiltin(lo, hi) {
  const order = lo !== void 0 && lo < 0 ? signedNames() : unsignedThenSigned();
  const effectiveLo = lo ?? YANG_INTEGER_BOUNDS[order[0]][0];
  const effectiveHi = hi ?? YANG_INTEGER_BOUNDS[order[order.length - 1]][1];
  for (const name of order) {
    const [blo, bhi] = YANG_INTEGER_BOUNDS[name];
    if (effectiveLo >= blo && effectiveHi <= bhi) {
      return name;
    }
  }
  return INT64;
}
function yangIntegerFromJsonBounds(minVal, maxVal) {
  const lo = coerceInt(minVal);
  const hi = coerceInt(maxVal);
  if (lo === void 0 && hi === void 0) {
    return { name: "integer" };
  }
  if (lo === 0 && hi !== void 0) {
    for (const name2 of signedNames()) {
      if (hi === YANG_INTEGER_BOUNDS[name2][1]) {
        return { name: name2, range: "0..max" };
      }
    }
  }
  if (lo !== void 0 && hi !== void 0) {
    for (const [name2, [blo, bhi]] of Object.entries(YANG_INTEGER_BOUNDS)) {
      if (lo === blo && hi === bhi) {
        return { name: name2 };
      }
    }
  }
  let range;
  if (lo !== void 0 || hi !== void 0) {
    const minPart = lo !== void 0 ? String(lo) : "min";
    const maxPart = hi !== void 0 ? String(hi) : "max";
    range = `${minPart}..${maxPart}`;
  }
  const name = narrowestIntegerBuiltin(lo, hi);
  const canonical = YANG_INTEGER_BOUNDS[name];
  if (range && canonical && lo === canonical[0] && hi === canonical[1]) {
    return { name };
  }
  return range ? { name, range } : { name };
}
function stringSchema(typeShape) {
  const out = { type: JSON_TYPE_STRING };
  const rawPatterns = Array.isArray(typeShape.patterns) ? typeShape.patterns : [];
  const specs = rawPatterns.filter((x) => Boolean(x) && typeof x === "object" && !Array.isArray(x)).map((x) => ({
    pattern: typeof x.pattern === "string" ? x.pattern : "",
    invert_match: x.invert_match === true,
    error_message: typeof x.error_message === "string" ? x.error_message : void 0,
    error_app_tag: typeof x.error_app_tag === "string" ? x.error_app_tag : void 0
  })).filter((x) => x.pattern.length > 0);
  const anchored = (p) => p.startsWith("^") && p.endsWith("$") ? p : `^${p}$`;
  if (specs.length === 1 && !specs[0].invert_match) {
    out.pattern = anchored(specs[0].pattern);
  } else if (specs.length > 0) {
    out.allOf = specs.map(
      (spec) => spec.invert_match ? { not: { type: JSON_TYPE_STRING, pattern: anchored(spec.pattern) } } : { pattern: anchored(spec.pattern) }
    );
  }
  if (specs.length > 0) {
    const entries = specs.map((spec) => ({
      pattern: spec.pattern,
      "invert-match": spec.invert_match,
      ...spec.error_message ? { "pattern-error-message": spec.error_message } : {},
      ...spec.error_app_tag ? { "pattern-error-app-tag": spec.error_app_tag } : {}
    }));
    const xYang = { "string-patterns": entries };
    const last = entries[entries.length - 1];
    if (typeof last["pattern-error-message"] === "string") {
      xYang["pattern-error-message"] = last["pattern-error-message"];
    }
    if (typeof last["pattern-error-app-tag"] === "string") {
      xYang["pattern-error-app-tag"] = last["pattern-error-app-tag"];
    }
    out["x-yang"] = xYang;
  }
  if (typeof typeShape.length === "string") {
    const [rawMin, rawMax] = typeShape.length.split("..");
    const min = Number.parseInt((rawMin ?? "").trim(), 10);
    const maxRaw = (rawMax ?? "").trim().toLowerCase();
    const max = Number.parseInt((rawMax ?? "").trim(), 10);
    if (!Number.isNaN(min)) {
      out.minLength = min;
    }
    if (!Number.isNaN(max) && maxRaw !== "max") {
      out.maxLength = max;
    }
  }
  return out;
}
function emitSchema(spec, typeShape, nativeJson = false) {
  if (nativeJson && spec.jsonEncoding === "string-number") {
    const decimal = spec.name === DECIMAL64;
    const fd = typeShape.fraction_digits;
    if (decimal && typeof fd !== "number") throw new YangExportError("native decimal64 export requires fraction-digits");
    const scale = decimal ? 10 ** fd : 1;
    const [lo, hi] = decimal ? [-9223372036854776e3 / scale, 9223372036854776e3 / scale] : spec.bounds;
    const xy = { type: spec.name };
    const out = { type: decimal ? "number" : "integer" };
    if (decimal) {
      xy["fraction-digits"] = fd;
      out.multipleOf = 10 ** -fd;
    }
    const range = typeof typeShape.range === "string" && typeShape.range ? typeShape.range : void 0;
    if (range) xy.range = range;
    const bounds = (range ?? "min..max").split("|").map((part) => {
      const ends = part.trim().split("..").map((s) => s.trim());
      const value = (text) => text === "min" ? lo : text === "max" ? hi : Number(text);
      return { minimum: value(ends[0]), maximum: value(ends[1] ?? ends[0]) };
    });
    if (bounds.length === 1) Object.assign(out, bounds[0]);
    else out.anyOf = bounds;
    out["x-yang"] = xy;
    return out;
  }
  if (spec.bounds && spec.jsonEncoding === "string-number") {
    const xYang = { type: spec.name };
    if (typeof typeShape.range === "string" && typeShape.range) {
      xYang.range = typeShape.range;
    }
    return { type: JSON_TYPE_STRING, pattern: spec.pattern, "x-yang": xYang };
  }
  if (spec.jsonEncoding === "number") {
    const out = { type: JSON_TYPE_INTEGER };
    const rangeStr = typeof typeShape.range === "string" ? typeShape.range : void 0;
    const { minimum, maximum } = jsonIntegerBoundsForBuiltin(spec.name, rangeStr);
    if (minimum !== void 0) {
      out.minimum = minimum;
    }
    if (maximum !== void 0) {
      out.maximum = maximum;
    }
    return out;
  }
  if (spec.name === DECIMAL64) {
    const xYang = { type: DECIMAL64 };
    if (typeof typeShape.fraction_digits === "number") {
      xYang["fraction-digits"] = typeShape.fraction_digits;
    }
    if (typeof typeShape.range === "string" && typeShape.range) {
      xYang.range = typeShape.range;
    }
    return { type: JSON_TYPE_STRING, pattern: spec.pattern, "x-yang": xYang };
  }
  if (spec.name === STRING) {
    return stringSchema(typeShape);
  }
  if (spec.name === BOOLEAN) {
    return { type: JSON_TYPE_BOOLEAN };
  }
  if (spec.name === BINARY) {
    return { type: JSON_TYPE_STRING, contentEncoding: "base64" };
  }
  if (spec.name === EMPTY) {
    return { type: JSON_TYPE_OBJECT, maxProperties: 0 };
  }
  if (spec.name === ENUMERATION) {
    const enums = Array.isArray(typeShape.enums) ? typeShape.enums.filter((value) => typeof value === "string") : [];
    if (enums.length === 0) return { type: JSON_TYPE_STRING };
    const guards = typeShape.enum_if_features;
    const guardMap = guards && typeof guards === "object" && !Array.isArray(guards) ? guards : {};
    const recorded = enums.map((name) => {
      const feats = Array.isArray(guardMap[name]) ? guardMap[name].filter((item) => typeof item === "string" && item.length > 0) : [];
      return feats.length > 0 ? { name, "if-features": feats } : { name };
    });
    const out = { type: JSON_TYPE_STRING, enum: enums };
    if (recorded.some((entry) => "if-features" in entry)) {
      out["x-yang"] = { enums: recorded };
    }
    return out;
  }
  if (spec.name === IDENTITYREF) {
    return identityrefSchema(typeShape);
  }
  if (spec.name === LEAFREF || spec.name === INSTANCE_IDENTIFIER) {
    return { type: JSON_TYPE_STRING };
  }
  if (spec.name === UNION) {
    const members = Array.isArray(typeShape.types) ? typeShape.types : [];
    return { oneOf: members.map((member) => leafTypeToSchema(member, nativeJson)) };
  }
  return { type: JSON_TYPE_FREE_FORM };
}
function leafTypeToSchema(typeShape, nativeJson = false) {
  const typeName = typeof typeShape.name === "string" ? typeShape.name : STRING;
  if (typeName === JSON_TYPE_NUMBER) {
    return REGISTRY[DECIMAL64].toSchema(typeShape, nativeJson);
  }
  const spec = REGISTRY[typeName];
  if (!spec) {
    return { type: JSON_TYPE_FREE_FORM };
  }
  return spec.toSchema(typeShape, nativeJson);
}
function fractionDigitsFromMultipleOf(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0 || value >= 1) {
    return void 0;
  }
  let n = 0;
  let t = value;
  while (t < 1 && n < 18) {
    t *= 10;
    n += 1;
  }
  return t === 1 ? n : void 0;
}
function decimal64FractionDigitsFromSchema(schema) {
  return fractionDigitsFromMultipleOf(schema.multipleOf);
}
function quotedNumericTypeShape(xy) {
  const name = typeof xy.type === "string" ? xy.type : "";
  if (!isStringNumberBuiltin(name)) {
    return null;
  }
  const shape = { name };
  if (typeof xy.range === "string" && xy.range) {
    shape.range = xy.range;
  }
  if (name === DECIMAL64 && typeof xy["fraction-digits"] === "number") {
    shape.fraction_digits = xy["fraction-digits"];
  }
  return shape;
}
function readSchema(spec, fragment) {
  const xy = fragment["x-yang"] ?? fragment;
  if (spec.jsonEncoding === "string-number") {
    const named = quotedNumericTypeShape(xy);
    return named && named.name === spec.name ? named : null;
  }
  if (spec.jsonEncoding === "number" && fragment.type === JSON_TYPE_INTEGER) {
    const inferred = yangIntegerFromJsonBounds(fragment.minimum, fragment.maximum);
    if (inferred.name !== spec.name) {
      return null;
    }
    const shape = { name: inferred.name };
    if (inferred.range) {
      shape.range = inferred.range;
    }
    return shape;
  }
  if (spec.name === BOOLEAN && fragment.type === JSON_TYPE_BOOLEAN) {
    return { name: BOOLEAN };
  }
  if (spec.name === EMPTY && fragment.type === JSON_TYPE_OBJECT && fragment.maxProperties === 0) {
    return { name: EMPTY };
  }
  if (spec.name === DECIMAL64 && fragment.type === JSON_TYPE_NUMBER) {
    const shape = { name: DECIMAL64 };
    const fd = decimal64FractionDigitsFromSchema(fragment);
    if (typeof fd === "number") {
      shape.fraction_digits = fd;
    }
    return shape;
  }
  return null;
}
function checkBuiltin(spec, value, _typeShape) {
  if (spec.bounds) {
    if (typeof value === "string") {
      if (spec.jsonEncoding === "string-number") {
        return `Expected ${spec.name}`;
      }
      return "Expected integer, got string";
    }
    return null;
  }
  if (spec.name === DECIMAL64) {
    if (typeof value === "string") {
      return "Expected number";
    }
    return null;
  }
  if (spec.name === BOOLEAN) {
    if (typeof value === "boolean" || value === "true" || value === "false") {
      return null;
    }
    return "Expected boolean";
  }
  if (spec.name === EMPTY) {
    return value === null ? null : "Expected empty (null)";
  }
  if (spec.jsonEncoding === "string" && spec.name !== UNION && spec.name !== BITS) {
    return typeof value === "string" ? null : "Expected string";
  }
  return null;
}

// ts/src/typedef-scope.ts
function inScope(scope, context) {
  return scope === void 0 || context === scope || context.startsWith(scope + "/");
}
function scopePath(context, parent2) {
  const stmt = parent2;
  if (!stmt || !["container", "list", "grouping", "rpc", "action", "input", "output", "notification"].includes(stmt.keyword ?? "")) return context;
  const name = stmt.keyword === "grouping" ? `@grouping:${stmt.name}` : ["input", "output"].includes(stmt.keyword ?? "") ? stmt.keyword : stmt.name ?? "";
  return context + "/" + name.replace(/~/g, "~0").replace(/\//g, "~1");
}
function registerTypedef(typedefs, td) {
  for (const previous of Object.values(typedefs)) {
    if (previous.name === td.name && (inScope(previous.scope, td.scope ?? "") || inScope(td.scope, previous.scope ?? ""))) {
      throw new YangSemanticError(`Duplicate typedef '${td.name}' in lexical scope`);
    }
  }
  if (Object.prototype.hasOwnProperty.call(REGISTRY, td.name ?? "")) throw new YangSemanticError(`Duplicate typedef '${td.name}': built-in type`);
  typedefs[(td.scope ? td.scope + "/" : "") + td.name] = td;
}

// ts/src/parser/parser-context.ts
var YangTokenType = {
  LBRACE: "{",
  RBRACE: "}",
  SEMICOLON: ";",
  COLON: ":",
  EQUALS: "=",
  PLUS: "+",
  SLASH: "/",
  // Unquoted arguments keep '.' (`1..127`, `../foo`). Identifier and
  // dotted-number lexers still consume a dot that belongs to them.
  DOT: ".",
  STRING: "STRING",
  IDENTIFIER: "IDENTIFIER",
  INTEGER: "INTEGER",
  DOTTED_NUMBER: "DOTTED_NUMBER",
  // Any other non-whitespace character (`|`, `@`, `*`, …). Part of an
  // unquoted argument (RFC 7950 §6.1.3); a parse error anywhere else.
  OTHER: "OTHER",
  MODULE: "module",
  YANG_VERSION: "yang-version",
  NAMESPACE: "namespace",
  PREFIX: "prefix",
  ORGANIZATION: "organization",
  CONTACT: "contact",
  DESCRIPTION: "description",
  REVISION: "revision",
  TYPEDEF: "typedef",
  IDENTITY: "identity",
  BASE: "base",
  TYPE: "type",
  BINARY,
  BITS,
  BOOLEAN,
  DECIMAL64,
  EMPTY,
  ENUMERATION,
  IDENTITYREF,
  INSTANCE_IDENTIFIER,
  INT8,
  INT16,
  INT32,
  INT64,
  LEAFREF,
  STRING_KW: STRING,
  UINT8,
  UINT16,
  UINT32,
  UINT64,
  UNION,
  PATH: "path",
  REQUIRE_INSTANCE: "require-instance",
  ENUM: "enum",
  VALUE: "value",
  STATUS: "status",
  BIT: "bit",
  POSITION: "position",
  PATTERN: "pattern",
  LENGTH: "length",
  FRACTION_DIGITS: "fraction-digits",
  RANGE: "range",
  GROUPING: "grouping",
  USES: "uses",
  REFINE: "refine",
  CONTAINER: "container",
  LIST: "list",
  LEAF: "leaf",
  LEAF_LIST: "leaf-list",
  ANYDATA: "anydata",
  ANYXML: "anyxml",
  CHOICE: "choice",
  CASE: "case",
  MUST: "must",
  WHEN: "when",
  PRESENCE: "presence",
  KEY: "key",
  MIN_ELEMENTS: "min-elements",
  MAX_ELEMENTS: "max-elements",
  ORDERED_BY: "ordered-by",
  MANDATORY: "mandatory",
  DEFAULT: "default",
  ERROR_MESSAGE: "error-message",
  ERROR_APP_TAG: "error-app-tag",
  TRUE: "true",
  FALSE: "false",
  IMPORT: "import",
  INCLUDE: "include",
  REVISION_DATE: "revision-date",
  FEATURE: "feature",
  IF_FEATURE: "if-feature",
  AUGMENT: "augment",
  SUBMODULE: "submodule",
  BELONGS_TO: "belongs-to",
  REFERENCE: "reference",
  ARGUMENT: "argument",
  YIN_ELEMENT: "yin-element",
  DEVIATION: "deviation",
  EXTENSION: "extension",
  RPC: "rpc",
  ACTION: "action",
  NOTIFICATION: "notification",
  INPUT: "input",
  OUTPUT: "output"
};
function hasTokenType(value, allowed) {
  for (const item of allowed) {
    if (item === value) {
      return true;
    }
  }
  return false;
}
var PUNCTUATION = /* @__PURE__ */ new Set([
  YangTokenType.LBRACE,
  YangTokenType.RBRACE,
  YangTokenType.SEMICOLON,
  YangTokenType.COLON,
  YangTokenType.EQUALS,
  YangTokenType.PLUS,
  YangTokenType.SLASH,
  YangTokenType.DOT
]);
function diagnosticSourceLines(content) {
  if (!content) {
    return [];
  }
  return content.split("\n").map((segment) => segment.replace(/\r$/, ""));
}
function classifyKind(type) {
  if (type === YangTokenType.STRING) {
    return "string";
  }
  if (type === YangTokenType.INTEGER || type === YangTokenType.DOTTED_NUMBER) {
    return "number";
  }
  if (PUNCTUATION.has(type)) {
    return "symbol";
  }
  return "identifier";
}
var LEXICAL_TOKEN_TYPES = /* @__PURE__ */ new Set([
  YangTokenType.LBRACE,
  YangTokenType.RBRACE,
  YangTokenType.SEMICOLON,
  YangTokenType.COLON,
  YangTokenType.EQUALS,
  YangTokenType.PLUS,
  YangTokenType.SLASH,
  YangTokenType.DOT,
  YangTokenType.STRING,
  YangTokenType.IDENTIFIER,
  YangTokenType.INTEGER,
  YangTokenType.DOTTED_NUMBER,
  YangTokenType.OTHER
]);
function makeYangToken(type, value, line_num, char_pos) {
  return {
    type,
    value,
    line_num,
    char_pos,
    kind: classifyKind(type),
    line: line_num,
    column: char_pos + 1
  };
}
var TokenStream = class {
  token_list;
  tokens;
  positions;
  filename;
  index;
  source;
  diagnostic_lines;
  constructor(token_list, source, filename) {
    this.token_list = token_list;
    this.tokens = token_list.map((t) => t.value);
    this.positions = token_list.map((t) => [t.line_num, t.char_pos]);
    this.source = source;
    this.filename = filename;
    this.index = 0;
  }
  peek_token() {
    return this.token_list[this.index];
  }
  peek(offset = 0) {
    return this.token_list[this.index + offset]?.value;
  }
  consume(expected) {
    if (this.index >= this.tokens.length) {
      throw this._make_error("Unexpected end of input");
    }
    const tokenVal = this.tokens[this.index];
    if (expected !== void 0 && tokenVal !== expected) {
      throw this._make_error(`Expected '${expected}', got '${tokenVal}'`);
    }
    this.index += 1;
    return tokenVal;
  }
  consume_if(expected) {
    if (this.peek() === expected) {
      this.consume();
      return true;
    }
    return false;
  }
  peek_type() {
    if (this.index >= this.token_list.length) {
      throw this._make_error("Unexpected end of input");
    }
    return this.token_list[this.index].type;
  }
  peek_type_at(offset = 0) {
    return this.token_list[this.index + offset]?.type;
  }
  consume_type(expected) {
    if (this.index >= this.token_list.length) {
      throw this._make_error("Unexpected end of input");
    }
    const tok = this.token_list[this.index];
    if (typeof expected === "string" && !LEXICAL_TOKEN_TYPES.has(expected)) {
      if (tok.type !== YangTokenType.IDENTIFIER || tok.value !== expected) {
        throw this._make_error(`Expected '${expected}', got '${tok.value}'`);
      }
    } else if (tok.type !== expected) {
      throw this._make_error(`Expected ${expected}, got ${tok.type} ('${tok.value}')`);
    }
    this.index += 1;
    return tok.value;
  }
  consume_if_type(expected) {
    if (this.index >= this.token_list.length) {
      return false;
    }
    const tok = this.token_list[this.index];
    if (typeof expected === "string" && !LEXICAL_TOKEN_TYPES.has(expected)) {
      if (tok.type !== YangTokenType.IDENTIFIER || tok.value !== expected) {
        return false;
      }
    } else if (tok.type !== expected) {
      return false;
    }
    this.consume_type(expected);
    return true;
  }
  consume_oneof(allowed_types) {
    if (this.index >= this.token_list.length) {
      throw this._make_error("Unexpected end of input");
    }
    const tok = this.token_list[this.index];
    for (const allowed of allowed_types) {
      if (typeof allowed === "string") {
        if (!LEXICAL_TOKEN_TYPES.has(allowed)) {
          if (tok.type === YangTokenType.IDENTIFIER && tok.value === allowed) {
            this.index += 1;
            return [tok.value, allowed];
          }
        } else if (tok.type === allowed) {
          this.index += 1;
          return [tok.value, allowed];
        }
      } else if (tok.type === allowed) {
        this.index += 1;
        return [tok.value, allowed];
      }
    }
    throw this._make_error(
      `Expected one of (${allowed_types.join(", ")}), got ${tok.type} ('${tok.value}')`
    );
  }
  has_more() {
    return this.index < this.tokens.length;
  }
  // Compatibility for prior TS parser helpers.
  hasMore() {
    return this.has_more();
  }
  /** Throw {@link YangSyntaxError} at the current token position. */
  syntaxError(message) {
    throw this._make_error(message);
  }
  position() {
    if (this.index < this.positions.length) {
      return this.positions[this.index];
    }
    if (this.positions.length > 0) {
      return this.positions[this.positions.length - 1];
    }
    return [1, 0];
  }
  diagnostic_lines_once() {
    if (!this.diagnostic_lines) {
      this.diagnostic_lines = diagnosticSourceLines(this.source);
    }
    return this.diagnostic_lines;
  }
  _make_error(message, context_lines = 3) {
    const [line_num] = this.position();
    const lines = this.diagnostic_lines_once();
    const context = [];
    const startLine = Math.max(1, line_num - context_lines);
    const endLine = Math.min(lines.length, line_num + context_lines);
    for (let n = startLine; n <= endLine; n += 1) {
      if (n <= lines.length) {
        context.push([n, lines[n - 1]]);
      }
    }
    const line = line_num <= lines.length ? lines[line_num - 1] : "";
    return new YangSyntaxError(message, {
      line_num,
      line,
      context_lines: context,
      filename: this.filename
    });
  }
};
var ParserContext = class _ParserContext {
  module;
  current_parent;
  source_dir;
  typedef_context = "";
  /** Parent name from the keyword dispatch registry, when this context is a statement body. */
  dispatch_parent;
  /** Text used in ``Invalid or unknown statement in …``. */
  dispatch_error;
  constructor(init) {
    this.module = init.module;
    this.current_parent = init.current_parent;
    this.source_dir = init.source_dir;
  }
  push_parent(parent2) {
    const next = new _ParserContext({
      module: this.module,
      current_parent: parent2,
      source_dir: this.source_dir
    });
    next.typedef_context = parent2 === this.current_parent ? this.typedef_context : scopePath(this.typedef_context, parent2);
    return next;
  }
  /** Copy of this context whose ``parseStatement`` calls use *parent*'s allow-list. */
  with_dispatch(parent2, errorContext) {
    const next = this.push_parent(this.current_parent);
    next.dispatch_parent = parent2;
    next.dispatch_error = errorContext;
    return next;
  }
};

// ts/src/xsd-regex.ts
var MAX_CP = 1114111;
var GENERAL_CATEGORIES = {
  L: ["Lu", "Ll", "Lt", "Lm", "Lo"],
  M: ["Mn", "Mc", "Me"],
  N: ["Nd", "Nl", "No"],
  P: ["Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po"],
  Z: ["Zs", "Zl", "Zp"],
  S: ["Sm", "Sc", "Sk", "So"],
  C: ["Cc", "Cf", "Co", "Cn"]
};
var CATEGORY_NAMES = /* @__PURE__ */ new Set([
  ...Object.keys(GENERAL_CATEGORIES),
  ...Object.values(GENERAL_CATEGORIES).flat()
]);
var NAME_START = [
  [58, 58],
  [65, 90],
  [95, 95],
  [97, 122],
  [192, 214],
  [216, 246],
  [248, 767],
  [880, 893],
  [895, 8191],
  [8204, 8205],
  [8304, 8591],
  [11264, 12271],
  [12289, 55295],
  [63744, 64975],
  [65008, 65533],
  [65536, 983039]
];
var NAME_CHAR = [
  ...NAME_START,
  [45, 46],
  [48, 57],
  [183, 183],
  [768, 879],
  [8255, 8256]
];
var XSD_SPACE = [[9, 10], [13, 13], [32, 32]];
var XSD_DOT_EXCLUDED = [[10, 10], [13, 13]];
var SINGLE_ESCAPES = { n: 10, r: 13, t: 9 };
var SINGLE_ESCAPE_LITERALS = new Set("\\|.-^?*+{}()[]".split(""));
var XSD_W_EXCLUDED = "\\p{P}\\p{Z}\\p{C}";
function isLiteralPunctuation(ch) {
  if (SINGLE_ESCAPE_LITERALS.has(ch)) {
    return true;
  }
  const n = ch.charCodeAt(0);
  if (ch.length !== 1 || n < 32 || n > 126) {
    return false;
  }
  return !(n >= 48 && n <= 57 || n >= 65 && n <= 90 || n >= 97 && n <= 122);
}
function normalize(ranges) {
  const out = [];
  for (const [lo, hi] of [...ranges].sort((a, b) => a[0] - b[0] || a[1] - b[1])) {
    const last = out[out.length - 1];
    if (last && lo <= last[1] + 1) {
      last[1] = Math.max(last[1], hi);
    } else {
      out.push([lo, hi]);
    }
  }
  return out;
}
function complement(ranges) {
  const out = [];
  let next = 0;
  for (const [lo, hi] of normalize(ranges)) {
    if (lo > next) {
      out.push([next, lo - 1]);
    }
    next = hi + 1;
  }
  if (next <= MAX_CP) {
    out.push([next, MAX_CP]);
  }
  return out;
}
var cp = (n) => `\\u{${n.toString(16).toUpperCase()}}`;
function render(ranges) {
  return ranges.map(([lo, hi]) => lo === hi ? cp(lo) : `${cp(lo)}-${cp(hi)}`).join("");
}
var Translator = class {
  constructor(src) {
    this.src = src;
  }
  src;
  pos = 0;
  unsupported(construct) {
    return new YangSemanticError(
      `unsupported XSD regex construct '${construct}' in pattern '${this.src}'`
    );
  }
  peek(offset = 0) {
    return this.src[this.pos + offset] ?? "";
  }
  /** Escape at `pos` (after the backslash). */
  escape() {
    const ch = this.peek();
    if (!ch) {
      throw this.unsupported("\\");
    }
    this.pos += 1;
    if (ch === "p" || ch === "P") {
      if (this.peek() !== "{") {
        throw this.unsupported(`\\${ch}`);
      }
      const end = this.src.indexOf("}", this.pos);
      if (end < 0) {
        throw this.unsupported(this.src.slice(this.pos - 2));
      }
      const name = this.src.slice(this.pos + 1, end);
      this.pos = end + 1;
      if (!CATEGORY_NAMES.has(name)) {
        throw this.unsupported(`\\${ch}{${name}}`);
      }
      return { body: `\\${ch}{${name}}` };
    }
    if (ch in SINGLE_ESCAPES) {
      const n = SINGLE_ESCAPES[ch];
      return { body: cp(n), single: n };
    }
    if (isLiteralPunctuation(ch)) {
      const n = ch.codePointAt(0);
      return { body: cp(n), single: n };
    }
    switch (ch) {
      case "d":
        return { body: "\\p{Nd}" };
      case "D":
        return { body: "\\P{Nd}" };
      case "s":
        return { body: render(XSD_SPACE) };
      case "S":
        return { body: render(complement(XSD_SPACE)) };
      case "w":
        return { body: "", complementBody: XSD_W_EXCLUDED };
      case "W":
        return { body: XSD_W_EXCLUDED };
      case "i":
        return { body: render(NAME_START) };
      case "I":
        return { body: render(complement(NAME_START)) };
      case "c":
        return { body: render(NAME_CHAR) };
      case "C":
        return { body: render(complement(NAME_CHAR)) };
      default:
        throw this.unsupported(`\\${ch}`);
    }
  }
  classAtom() {
    const ch = this.peek();
    if (ch === "\\") {
      this.pos += 1;
      return this.escape();
    }
    if (ch === "[") {
      throw this.unsupported("[");
    }
    const n = this.src.codePointAt(this.pos);
    this.pos += String.fromCodePoint(n).length;
    return { body: cp(n), single: n };
  }
  /** `[...]` at `pos` (after `[`). */
  charClass() {
    const start = this.pos - 1;
    const negated = this.peek() === "^";
    if (negated) {
      this.pos += 1;
    }
    let body = "";
    const extra = [];
    let first = true;
    for (; ; ) {
      const ch = this.peek();
      if (!ch) {
        throw new YangSemanticError(`unterminated character class in pattern ${JSON.stringify(this.src)}`);
      }
      if (ch === "]" && !first) {
        this.pos += 1;
        break;
      }
      if (ch === "-" && this.peek(1) === "[") {
        const end = this.src.indexOf("]", this.pos);
        throw this.unsupported(this.src.slice(start, end >= 0 ? end + 2 : this.src.length));
      }
      first = false;
      const lo = this.classAtom();
      if (lo.single !== void 0 && this.peek() === "-" && this.peek(1) !== "]" && this.peek(1) !== "[") {
        this.pos += 1;
        const hi = this.classAtom();
        if (hi.single === void 0) {
          throw this.unsupported(this.src.slice(start, this.pos));
        }
        if (hi.single < lo.single) {
          throw new YangSemanticError(`invalid character range in pattern ${JSON.stringify(this.src)}`);
        }
        body += `${cp(lo.single)}-${cp(hi.single)}`;
      } else if (lo.complementBody !== void 0) {
        extra.push(`[^${lo.complementBody}]`);
      } else {
        body += lo.body;
      }
    }
    if (extra.length === 0) {
      return `[${negated ? "^" : ""}${body}]`;
    }
    const positive = `(?:${[...body ? [`[${body}]`] : [], ...extra].join("|")})`;
    return negated ? `(?:(?!${positive})[\\s\\S])` : positive;
  }
  translate() {
    let out = "";
    while (this.pos < this.src.length) {
      const ch = this.peek();
      if (ch === "\\") {
        this.pos += 1;
        const atom = this.escape();
        out += atom.complementBody !== void 0 ? `[^${atom.complementBody}]` : `[${atom.body}]`;
      } else if (ch === "[") {
        this.pos += 1;
        out += this.charClass();
      } else if (ch === ".") {
        this.pos += 1;
        out += `[^${render(XSD_DOT_EXCLUDED)}]`;
      } else if (ch === "(") {
        if (this.peek(1) === "?") {
          throw this.unsupported("(?");
        }
        this.pos += 1;
        out += "(?:";
      } else if ("|)*+?".includes(ch)) {
        this.pos += 1;
        out += ch;
      } else if (ch === "{") {
        const m = /\{\d+(,\d*)?\}/y;
        m.lastIndex = this.pos;
        const hit = m.exec(this.src);
        if (!hit) {
          throw this.unsupported("{");
        }
        this.pos += hit[0].length;
        out += hit[0];
      } else {
        const n = this.src.codePointAt(this.pos);
        this.pos += String.fromCodePoint(n).length;
        out += /[A-Za-z0-9]/.test(ch) ? ch : cp(n);
      }
    }
    return out;
  }
};
var cache = /* @__PURE__ */ new Map();
function translateXsdRegex(pattern) {
  const hit = cache.get(pattern);
  if (hit) {
    return hit;
  }
  const body = new Translator(pattern).translate();
  let rx;
  try {
    rx = new RegExp(`^(?:${body})$`, "u");
  } catch (e) {
    throw new YangSemanticError(`invalid pattern ${JSON.stringify(pattern)}: ${e instanceof Error ? e.message : String(e)}`);
  }
  cache.set(pattern, rx);
  return rx;
}

// ts/src/types.ts
var TypeConstraint = class {
  constructor(input = {}) {
    Object.assign(this, input);
  }
};
function decimalIssues(n, text, c) {
  if (c.range && !matchesRange(n, c.range)) {
    return [["range", restrictionMessage(`Number ${n} does not match ${c.range}`, c.range_error_message, c.range_error_app_tag)]];
  }
  if (typeof c.fraction_digits === "number") {
    const decimals = text.split(".")[1]?.length ?? 0;
    if (decimals > c.fraction_digits) {
      return [["fraction-digits", `Too many fraction digits (${decimals} > ${c.fraction_digits})`]];
    }
  }
  return [];
}
function restrictionMessage(defaultMsg, message, tag) {
  return patternEntryViolationMessage({ error_message: message, error_app_tag: tag }, defaultMsg);
}
function patternEntryViolationMessage(p, defaultMsg) {
  const msg = typeof p.error_message === "string" && p.error_message.trim().length > 0 ? p.error_message : defaultMsg;
  const tag = typeof p.error_app_tag === "string" ? p.error_app_tag.trim() : "";
  return tag.length > 0 ? `${msg} (error-app-tag: ${tag})` : msg;
}
function parseRangeText(raw) {
  const parseBound = (text, kind) => {
    const t = text.trim().toLowerCase();
    if (t === "min") {
      return Number.NEGATIVE_INFINITY;
    }
    if (t === "max") {
      return Number.POSITIVE_INFINITY;
    }
    const n = Number(t);
    if (Number.isNaN(n)) {
      return kind === "min" ? Number.NEGATIVE_INFINITY : Number.POSITIVE_INFINITY;
    }
    return n;
  };
  return raw.split("|").map((part) => part.trim()).filter(Boolean).map((part) => {
    const [minRaw, maxRaw] = part.split("..").map((x) => x.trim());
    if (!maxRaw) {
      const n = parseBound(minRaw, "min");
      return { min: n, max: n };
    }
    return { min: parseBound(minRaw, "min"), max: parseBound(maxRaw, "max") };
  });
}
function matchesRange(value, raw) {
  for (const band of parseRangeText(raw)) {
    if (value >= band.min && value <= band.max) {
      return true;
    }
  }
  return false;
}
function integerLike(value) {
  if (typeof value === "number" && Number.isFinite(value) && Number.isInteger(value)) {
    return value;
  }
  return null;
}
var ExactDecimal = class {
  constructor(text) {
    this.text = text;
  }
  text;
};
var INT64_MIN = BigInt("-9223372036854775808");
var INT64_MAX = BigInt("9223372036854775807");
var UINT64_MAX = BigInt("18446744073709551615");
function decimalLike(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && /^-?\d+(\.\d+)?$/.test(value)) {
    return Number(value);
  }
  return null;
}
function validateIntegerBuiltin(typeName, value, range, diag) {
  const bounds = YANG_INTEGER_BOUNDS[typeName];
  if (!bounds) {
    return [["type", `Unsupported integer type '${typeName}'`]];
  }
  if (typeof value === "string") {
    return [["type", REGISTRY[typeName].checkValue(value, null) ?? "Expected integer, got string"]];
  }
  if (typeof value === "bigint" && isQuotedInteger(typeName)) {
    const unsigned = YANG_INTEGER_BOUNDS[typeName]?.[0] === 0;
    const lo2 = unsigned ? BigInt(0) : INT64_MIN;
    const hi2 = unsigned ? UINT64_MAX : INT64_MAX;
    if (value < lo2 || value > hi2) {
      return [["type", `Value ${value} is outside ${typeName}`]];
    }
    if (range) {
      const asNumber = Number(value);
      if (!Number.isSafeInteger(asNumber) || !matchesRange(asNumber, range)) {
        if (!Number.isSafeInteger(asNumber)) {
          return [];
        }
        return [["range", restrictionMessage(`Integer ${value} does not match ${range}`, diag?.error_message, diag?.error_app_tag)]];
      }
    }
    return [];
  }
  const n = integerLike(value);
  if (n === null) {
    return [["type", `Expected ${typeName}`]];
  }
  if (range) {
    if (!matchesRange(n, range)) {
      return [["range", restrictionMessage(`Integer ${n} does not match ${range}`, diag?.error_message, diag?.error_app_tag)]];
    }
    return [];
  }
  const [lo, hi] = bounds;
  if (n < lo) {
    return [["range", `Value ${n} is less than minimum ${lo}`]];
  }
  if (n > hi) {
    return [["range", `Value ${n} exceeds maximum ${hi}`]];
  }
  return [];
}
function validateBinary(value, length, diag) {
  if (typeof value !== "string") {
    return [["type", "Expected base64 string"]];
  }
  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(value) || value.length % 4 !== 0) {
    return [["type", "Expected valid base64 string"]];
  }
  try {
    const bytes = Buffer.from(value, "base64");
    if (length && !matchesRange(bytes.length, length)) {
      return [["length", restrictionMessage(`Binary length ${bytes.length} does not match ${length}`, diag?.error_message, diag?.error_app_tag)]];
    }
  } catch {
    return [["type", "Expected valid base64 string"]];
  }
  return [];
}
function validateBits(value, bits) {
  if (typeof value !== "string") {
    return [["bits", "Bits values must be string tokens"]];
  }
  const allowed = new Set(bits.map((bit) => bit.name));
  if (value.trim() === "") {
    return [];
  }
  const seen = /* @__PURE__ */ new Set();
  for (const token of value.trim().split(/\s+/)) {
    if (!allowed.has(token)) {
      return [["bits", `Unknown bit token '${token}'`]];
    }
    if (seen.has(token)) {
      return [["bits", `Duplicate bit token '${token}'`]];
    }
    seen.add(token);
  }
  return [];
}
function stringIssues(value, c) {
  if (typeof value !== "string") {
    return [["type", "Expected string"]];
  }
  const errors = [];
  if (c.length && !matchesRange(value.length, c.length)) {
    errors.push([
      "length",
      restrictionMessage(
        `String length ${value.length} does not match ${c.length}`,
        c.length_error_message,
        c.length_error_app_tag
      )
    ]);
  }
  const patterns = Array.isArray(c.patterns) ? c.patterns : [];
  for (const p of patterns) {
    if (typeof p?.pattern !== "string" || p.pattern.length === 0) {
      continue;
    }
    const matched = translateXsdRegex(p.pattern).test(value);
    const invert = p.invert_match === true;
    if (!invert && !matched || invert && matched) {
      const defaultMsg = invert ? `String matches forbidden pattern ${p.pattern} (invert-match)` : `String does not match pattern ${p.pattern}`;
      errors.push(["pattern", patternEntryViolationMessage(p, defaultMsg)]);
    }
  }
  if (c.enums && c.enums.length > 0 && !c.enums.includes(value)) {
    errors.push(["enum", `Value '${value}' is not in enum`]);
  }
  return errors;
}
var TypeSystem = class {
  /**
   * Every restriction violation for this value.
   * Strings report length, then each failing pattern, then enum.
   * Other types still return at most one issue (a range miss does not also
   * report fraction-digits; a binary length miss does not also report pattern).
   */
  issues(value, typeName, constraint) {
    const c = constraint ?? new TypeConstraint();
    const normalizedType = typeName.trim();
    if (normalizedType === YangTokenType.UNION) {
      for (const member of c.types ?? []) {
        const memberName2 = typeof member.name === "string" ? member.name : YangTokenType.STRING_KW;
        if (this.issues(value, memberName2, new TypeConstraint(member)).length === 0) {
          return [];
        }
      }
      return [["union", "Value does not match any union member type"]];
    }
    if (normalizedType === YangTokenType.ENUMERATION) {
      if (typeof value !== "string") {
        return [["enum", "Expected enumeration value (string)"]];
      }
      if (c.enums && c.enums.length > 0 && !c.enums.includes(value)) {
        return [["enum", `Value '${value}' is not in enum`]];
      }
      return [];
    }
    if (normalizedType === YangTokenType.STRING_KW) {
      return stringIssues(value, c);
    }
    if (normalizedType === YangTokenType.BOOLEAN) {
      if (typeof value === "boolean") {
        return [];
      }
      if (value === YangTokenType.TRUE || value === YangTokenType.FALSE) {
        return [];
      }
      return [["type", "Expected boolean"]];
    }
    if (normalizedType === YangTokenType.EMPTY) {
      if (value === null) {
        return [];
      }
      return [["type", "Expected empty (null)"]];
    }
    if (normalizedType in YANG_INTEGER_BOUNDS) {
      return validateIntegerBuiltin(normalizedType, value, c.range, {
        error_message: c.range_error_message,
        error_app_tag: c.range_error_app_tag
      });
    }
    if (normalizedType === YangTokenType.BINARY) {
      return validateBinary(value, c.length, {
        error_message: c.length_error_message,
        error_app_tag: c.length_error_app_tag
      });
    }
    if (normalizedType === YangTokenType.BITS) {
      return validateBits(value, c.bits ?? []);
    }
    if (normalizedType === YangTokenType.DECIMAL64 || normalizedType === "number") {
      if (typeof value === "string") {
        return [["type", "Expected number"]];
      }
      if (value instanceof ExactDecimal) {
        const text = value.text.trim();
        const n2 = Number(text);
        if (!Number.isFinite(n2)) {
          return [["type", "Expected number"]];
        }
        return decimalIssues(n2, text, c);
      }
      const n = decimalLike(value);
      if (n === null) {
        return [["type", "Expected number"]];
      }
      return decimalIssues(n, `${n}`, c);
    }
    if (normalizedType === YangTokenType.INT64 || normalizedType === "integer") {
      if (typeof value === "string") {
        return [["type", "Expected integer, got string"]];
      }
      const n = integerLike(value);
      if (n === null) {
        return [["type", "Expected integer"]];
      }
      if (c.range && !matchesRange(n, c.range)) {
        return [["range", restrictionMessage(`Integer ${n} does not match ${c.range}`, c.range_error_message, c.range_error_app_tag)]];
      }
      return [];
    }
    if (typeof value === "string") {
      return [];
    }
    return [["type", `Unsupported type '${normalizedType}'`]];
  }
  /**
   * Public tuple kept for `@exergy-connect/xyang/types`.
   * Thin wrapper over {@link issues}: valid, or invalid with the first message.
   * Validation that must report every issue calls {@link issues}.
   */
  validate(value, typeName, constraint) {
    const found = this.issues(value, typeName, constraint);
    if (found.length === 0) {
      return [true, null];
    }
    return [false, found[0][1]];
  }
};

// ts/src/validator/type-validation-debug.ts
function summarizeValue(value) {
  if (value === null) {
    return "null";
  }
  const t = typeof value;
  if (t === "undefined") {
    return "undefined";
  }
  if (typeof value === "string") {
    const s = value;
    if (s.length > 100) {
      return `string(len=${s.length}):${JSON.stringify(s.slice(0, 80))}\u2026`;
    }
    return JSON.stringify(s);
  }
  if (t === "number" || t === "boolean" || t === "bigint") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return `Array(${value.length})`;
  }
  if (t === "object") {
    try {
      const j = JSON.stringify(value);
      return j.length > 160 ? `${j.slice(0, 160)}\u2026` : j;
    } catch {
      return "[object]";
    }
  }
  return String(value);
}
function traceTypeValidation(enabled, message, fields) {
  if (!enabled) {
    return;
  }
  console.debug(`[xYang:type-validation] ${message}`, fields);
}

// ts/src/validator/type-checker.ts
function hasTypeRestrictions(constraint) {
  if (!constraint) {
    return false;
  }
  if (typeof constraint.range === "string" && constraint.range.trim() !== "") {
    return true;
  }
  if (typeof constraint.length === "string" && constraint.length.trim() !== "") {
    return true;
  }
  return Array.isArray(constraint.patterns) && constraint.patterns.length > 0;
}
function asTypeRef(name, constraint) {
  const prefix = constraint && typeof constraint.prefix === "string" && constraint.prefix ? constraint.prefix : void 0;
  return prefix ? { prefix, name } : { name };
}
function resolveTypedef(host, type) {
  if (typeof type.name !== "string") return void 0;
  if (!type.prefix && Object.prototype.hasOwnProperty.call(REGISTRY, type.name)) return void 0;
  let scope = host;
  if (typeof type.scope_module === "string" && type.scope_module && type.scope_module !== host.name) {
    const loaded2 = host.module_registry?.[type.scope_module];
    if (!loaded2) {
      throw new Error(`type '${type.name}' is written in module '${type.scope_module}', which is not loaded`);
    }
    scope = loaded2;
  }
  const sourceFile = typeof type.source_file === "string" ? type.source_file : void 0;
  const target = typeof type.prefix === "string" && type.prefix ? resolvePrefixedModule(scope, type.prefix, sourceFile) : scope;
  const typedefs = target?.typedefs;
  if (!typedefs) return void 0;
  const direct = typedefs[type.name];
  const candidates = direct ? [direct] : Object.values(typedefs).filter((td) => td.name === type.name);
  return candidates.find((td) => td.type && typeof td.type.name === "string" && (type.prefix ? td.scope === void 0 : inScope(td.scope, typeof type.context === "string" ? type.context : "")));
}
var TypeChecker = class {
  constructor(module, options = {}) {
    this.module = module;
    this.typeValidationDebug = options.typeValidationDebug === true;
    this.enabledByModule = options.enabledByModule;
  }
  module;
  system = new TypeSystem();
  typeValidationDebug;
  enabledByModule;
  /** Resolve a local or prefixed typedef where the `type` was written (see `resolveTypedef`). */
  lookupTypedef(ref, constraint) {
    const scope = typeof constraint?.scope_module === "string" ? constraint.scope_module : void 0;
    return resolveTypedef(this.module, { ...constraint, name: ref.name, prefix: ref.prefix, scope_module: scope });
  }
  /**
   * Follow a typedef chain to the underlying builtin type name (stops at unions or unknown).
   */
  resolveUnderlyingBuiltinName(typeName, constraint) {
    const seen = /* @__PURE__ */ new Set();
    let ref = asTypeRef(typeName, constraint);
    let shape = constraint;
    while (seen.size < 64) {
      const typedef = this.lookupTypedef(ref, shape);
      if (!typedef?.type || typeof typedef.type.name !== "string") {
        return ref.name;
      }
      if (typedef.type.name === YangTokenType.UNION) {
        return formatIdentifierRef(ref);
      }
      if (seen.has(typedef)) return ref.name;
      seen.add(typedef);
      const next = asTypeRef(typedef.type.name, typedef.type);
      ref = next;
      shape = typedef.type;
    }
    return ref.name;
  }
  /** Every `(code, message)` issue. Empty means the value is valid. */
  validate(value, typeName, constraint) {
    let via;
    let result;
    const ref = asTypeRef(typeName, constraint);
    const typedef = this.lookupTypedef(ref, constraint);
    if (typedef?.type && typeof typedef.type.name === "string") {
      const typedefConstraint = new TypeConstraint(typedef.type);
      if (typedef.type.name === YangTokenType.UNION) {
        via = "typedef-union";
        result = this.validateUnion(value, typedefConstraint);
      } else if (this.lookupTypedef(asTypeRef(typedef.type.name, typedef.type), typedef.type)) {
        via = "typedef";
        result = this.validate(value, typedef.type.name, typedef.type);
      } else {
        via = "typedef";
        result = this.validateBuiltin(value, typedef.type.name, typedef.type, typedefConstraint);
      }
    } else {
      const merged = new TypeConstraint(constraint);
      if (typeName === YangTokenType.UNION && (merged.types?.length ?? 0) > 0) {
        via = "inline-union";
        result = this.validateUnion(value, merged);
      } else {
        via = "direct";
        result = this.validateBuiltin(value, typeName, constraint, merged);
      }
    }
    if (result.length === 0) {
      const checked = typedef?.type ?? constraint;
      const gated = this.gatedValueIssues(value, checked);
      if (gated.length > 0) result = gated;
    }
    if (result.length === 0 && via === "typedef") {
      const gated = this.gatedValueIssues(value, constraint);
      if (gated.length > 0) result = gated;
    }
    if (result.length === 0 && via === "typedef" && hasTypeRestrictions(constraint)) {
      result = this.system.issues(
        value,
        this.resolveUnderlyingBuiltinName(typeName, constraint),
        new TypeConstraint(constraint)
      );
    }
    if (this.typeValidationDebug) {
      traceTypeValidation(true, "TypeChecker.validate", {
        module: this.module.name ?? "(anonymous)",
        typeName,
        via,
        ok: result.length === 0,
        reason: result.length === 0 ? null : result.map(([, message]) => message).join("; "),
        value: summarizeValue(value)
      });
    }
    return result;
  }
  validateBuiltin(value, typeName, shape, constraint) {
    if (typeName === YangTokenType.IDENTITYREF) {
      return this.checkIdentityref(value, shape ?? {});
    }
    return this.system.issues(value, typeName, constraint);
  }
  /** The module that wrote `shape`, or the checker module when the type has no scope. */
  featureModule(shape) {
    const scope = shape?.scope_module;
    if (typeof scope === "string" && scope && scope !== this.module.name) {
      return this.module.module_registry?.[scope] ?? this.module;
    }
    return this.module;
  }
  guardIsFalse(feats, shape) {
    if (feats.length === 0 || !this.enabledByModule) return false;
    return !stmtIfFeaturesSatisfied(feats, this.featureModule(shape), this.enabledByModule);
  }
  /** Reject an enum or bit whose own ``if-feature`` is false (RFC 7950 §9.6.4, §9.7.4). */
  gatedValueIssues(value, shape) {
    const guards = shape?.enum_if_features;
    if (typeof value === "string" && guards && typeof guards === "object" && !Array.isArray(guards)) {
      const feats = guards[value];
      const expressions = Array.isArray(feats) ? feats.filter((item) => typeof item === "string" && item.length > 0) : [];
      if (this.guardIsFalse(expressions, shape)) {
        return [["if-feature", `Value '${value}' is not available: its 'if-feature' condition is false`]];
      }
    }
    const bits = shape?.bits;
    if (typeof value === "string" && value.trim() !== "" && Array.isArray(bits)) {
      const byName = /* @__PURE__ */ new Map();
      for (const bit of bits) {
        if (!bit || typeof bit !== "object") continue;
        const entry = bit;
        if (typeof entry.name !== "string") continue;
        const feats = Array.isArray(entry.if_features) ? entry.if_features.filter((item) => typeof item === "string" && item.length > 0) : [];
        byName.set(entry.name, feats);
      }
      for (const token of value.trim().split(/\s+/)) {
        const feats = byName.get(token) ?? [];
        if (this.guardIsFalse(feats, shape)) {
          return [["if-feature", `Bit '${token}' is not available: its 'if-feature' condition is false`]];
        }
      }
    }
    return [];
  }
  /** RFC 7951 §6.8 value, derived from every base (bases resolve in the module that wrote the `type`). */
  checkIdentityref(value, shape) {
    if (typeof value !== "string") {
      return [[
        "identityref",
        `identityref value must be a string, got ${value === null ? "null" : typeof value}`
      ]];
    }
    const bases = Array.isArray(shape.identityref_bases) ? shape.identityref_bases : [];
    if (bases.length === 0) {
      return [["identityref", "identityref type has no base identities"]];
    }
    const moduleData = this.module;
    if (!resolveIdentityValue(moduleData, value)) {
      return [["identityref", `identityref value '${value}' does not resolve to a known identity`]];
    }
    const scopeName = typeof shape.scope_module === "string" ? shape.scope_module : void 0;
    const baseScope = scopeName && scopeName !== moduleData.name ? moduleData.module_registry?.[scopeName] : void 0;
    if (!identityrefValueValid(moduleData, value, bases, baseScope ?? moduleData)) {
      const shown = bases.map((b) => `'${formatIdentifierRef(b)}'`).join(", ");
      return [["identityref", `identityref value '${value}' is not derived from all bases [${shown}]`]];
    }
    return [];
  }
  /** Union members may name typedefs; validate through this checker so typedefs resolve. */
  validateUnion(value, constraint) {
    if (this.typeValidationDebug) {
      traceTypeValidation(true, "TypeChecker.validateUnion", {
        module: this.module.name ?? "(anonymous)",
        memberCount: constraint.types?.length ?? 0,
        value: summarizeValue(value)
      });
    }
    for (const member of constraint.types ?? []) {
      const memberObj = member;
      const memberName2 = typeof memberObj.name === "string" ? memberObj.name : YangTokenType.STRING_KW;
      if (this.validate(value, memberName2, memberObj).length === 0) {
        return [];
      }
    }
    return [["union", "Value does not match any union member type"]];
  }
};

// ts/src/shims/node-fs-browser.ts
function existsSync() {
  throw new Error("parseYangFile() and YANG import resolution require Node.js (filesystem). Use parseYangString() in the browser.");
}
function readFileSync() {
  throw new Error("parseYangFile() requires Node.js (filesystem). Use parseYangString() in the browser.");
}
function readdirSync() {
  throw new Error("parseYangFile() requires Node.js (filesystem). Use parseYangString() in the browser.");
}

// ts/src/shims/node-url-browser.ts
function fileURLToPath() {
  throw new Error("File URLs require Node.js.");
}

// ts/src/core/model.ts
var RANGE_FIELDS = ["range", "range_error_message", "range_error_app_tag", "range_description", "range_reference"];
var LENGTH_FIELDS = ["length", "length_error_message", "length_error_app_tag", "length_description", "length_reference"];
var TYPE_FIELDS = {
  plain: [],
  numeric: RANGE_FIELDS,
  decimal: [...RANGE_FIELDS, "fraction_digits"],
  string: [...LENGTH_FIELDS, "patterns", "pattern"],
  binary: LENGTH_FIELDS,
  enumeration: ["enums", "enum_if_features"],
  bits: ["bits"],
  union: ["types"],
  leafref: ["path", "xpath_prefixes", "require_instance"],
  "instance-identifier": ["require_instance"],
  identityref: ["identityref_bases"],
  derived: [...RANGE_FIELDS, ...LENGTH_FIELDS, "patterns", "pattern", "enums", "enum_if_features", "bits", "require_instance"]
};
var COMMON_TYPE_FIELDS = /* @__PURE__ */ new Set(["name", "prefix", "scope_module", "source_file", "context", "units"]);
function normalizeTypeShape(input) {
  const name = input.name ?? "";
  const kind = typeStatementKind(name, typeof input.prefix === "string" ? input.prefix : void 0);
  const output = { kind, name };
  const fields = TYPE_FIELDS[kind];
  for (const [key2, value] of Object.entries(input)) {
    if (key2 === "kind" || value === void 0) continue;
    if (!COMMON_TYPE_FIELDS.has(key2) && !fields.includes(key2)) {
      throw new TypeError(`Attribute '${key2}' does not belong to type '${name}' (${kind})`);
    }
    output[key2] = key2 === "types" && Array.isArray(value) ? value.map((member) => normalizeTypeShape(member)) : value;
  }
  return output;
}
var STATEMENT_LIST_KEYS = /* @__PURE__ */ new Set(["statements", "refines", "augmentations", "local_groupings"]);
function isStatementInit(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
var YangStatement = class _YangStatement {
  statements = [];
  constructor(init = {}) {
    const raw = init;
    for (const key2 of Object.keys(raw)) {
      if (key2 === "__class__" || key2 === "type" || STATEMENT_LIST_KEYS.has(key2)) {
        continue;
      }
      this[key2] = raw[key2];
    }
    this.statements = statementList(init.statements);
    if (init.type) this.type = normalizeTypeShape(init.type);
    if (Array.isArray(init.refines)) {
      this.refines = statementList(init.refines);
    }
    if (Array.isArray(init.augmentations)) {
      this.augmentations = statementList(init.augmentations);
    }
    if (init.local_groupings && typeof init.local_groupings === "object") {
      const local2 = {};
      for (const [key2, value] of Object.entries(init.local_groupings)) {
        local2[key2] = value instanceof _YangStatement ? value : new _YangStatement(value);
      }
      this.local_groupings = local2;
    }
  }
  findStatement(name) {
    return this.statements.find((stmt) => stmt.name === name);
  }
};
function statementList(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  if (value.every((item) => item instanceof YangStatement)) {
    return value;
  }
  return value.map((item) => {
    if (item instanceof YangStatement) {
      return item;
    }
    if (!isStatementInit(item)) {
      throw new TypeError("Expected a YANG statement");
    }
    return new YangStatement(item);
  });
}
function nonEmpty(value) {
  return typeof value === "string" && value.length > 0 ? value : void 0;
}
var YangModule = class {
  name;
  /** YANG `yang-version` argument. The camelCase accessor is {@link yangVersion}. */
  yang_version;
  namespace;
  prefix;
  organization;
  contact;
  description;
  typedefs = {};
  identities = {};
  /** Prefix → imported module. The same object the parser cached for that file. */
  import_prefixes = {};
  /** Submodule name -> that file's import prefixes. The module file uses {@link import_prefixes}. */
  file_imports = {};
  extensions = {};
  extension_runtime = {};
  features = /* @__PURE__ */ new Set();
  feature_if_features = {};
  groupings = {};
  statements = [];
  source;
  constructor(init, source) {
    this.source = source;
    this.name = typeof init.name === "string" ? init.name : void 0;
    this.yang_version = typeof init.yang_version === "string" ? init.yang_version : void 0;
    this.namespace = typeof init.namespace === "string" ? init.namespace : void 0;
    this.prefix = typeof init.prefix === "string" ? init.prefix : void 0;
    this.organization = nonEmpty(init.organization);
    this.contact = nonEmpty(init.contact);
    this.description = typeof init.description === "string" ? init.description : void 0;
    this.typedefs = init.typedefs ?? {};
    this.identities = init.identities ?? {};
    this.import_prefixes = init.import_prefixes ?? {};
    this.file_imports = init.file_imports ?? {};
    this.extensions = init.extensions ?? {};
    this.extension_runtime = init.extension_runtime ?? {};
    this.features = init.features instanceof Set ? init.features : new Set(Array.isArray(init.features) ? init.features : []);
    this.feature_if_features = init.feature_if_features ?? {};
    this.statements = statementList(init.statements);
    const groupings = {};
    for (const [key2, value] of Object.entries(init.groupings ?? {})) {
      groupings[key2] = value instanceof YangStatement ? value : new YangStatement(value);
    }
    this.groupings = groupings;
  }
  get yangVersion() {
    return this.yang_version;
  }
  findStatement(name) {
    return this.statements.find((stmt) => stmt.name === name);
  }
};

// ts/src/parser/keywords.ts
var MODULE = "module";
var YANG_VERSION = "yang-version";
var NAMESPACE = "namespace";
var PREFIX = "prefix";
var ORGANIZATION = "organization";
var CONTACT = "contact";
var DESCRIPTION = "description";
var REVISION = "revision";
var TYPEDEF = "typedef";
var IDENTITY = "identity";
var BASE = "base";
var TYPE = "type";
var PATH = "path";
var REQUIRE_INSTANCE = "require-instance";
var ENUM = "enum";
var VALUE = "value";
var STATUS = "status";
var BIT = "bit";
var POSITION = "position";
var PATTERN = "pattern";
var MODIFIER = "modifier";
var LENGTH = "length";
var UNITS = "units";
var FRACTION_DIGITS = "fraction-digits";
var RANGE = "range";
var GROUPING = "grouping";
var USES = "uses";
var REFINE = "refine";
var CONTAINER = "container";
var LIST = "list";
var LEAF = "leaf";
var LEAF_LIST = "leaf-list";
var ANYDATA = "anydata";
var ANYXML = "anyxml";
var CHOICE = "choice";
var CASE = "case";
var MUST = "must";
var WHEN = "when";
var PRESENCE = "presence";
var KEY = "key";
var MIN_ELEMENTS = "min-elements";
var UNIQUE = "unique";
var MAX_ELEMENTS = "max-elements";
var ORDERED_BY = "ordered-by";
var MANDATORY = "mandatory";
var CONFIG = "config";
var DEFAULT = "default";
var ERROR_MESSAGE = "error-message";
var ERROR_APP_TAG = "error-app-tag";
var TRUE = "true";
var FALSE = "false";
var IMPORT = "import";
var INCLUDE = "include";
var REVISION_DATE = "revision-date";
var FEATURE = "feature";
var IF_FEATURE = "if-feature";
var AUGMENT = "augment";
var SUBMODULE = "submodule";
var BELONGS_TO = "belongs-to";
var REFERENCE = "reference";
var ARGUMENT = "argument";
var YIN_ELEMENT = "yin-element";
var DEVIATION = "deviation";
var DEVIATE = "deviate";
var NOT_SUPPORTED = "not-supported";
var ADD = "add";
var DELETE = "delete";
var REPLACE = "replace";
var DEVIATE_SUBSTATEMENTS = /* @__PURE__ */ new Map([
  [ADD, /* @__PURE__ */ new Set(["units", "must", "unique", "default", "config", "mandatory", "min-elements", "max-elements"])],
  [DELETE, /* @__PURE__ */ new Set(["units", "must", "unique", "default"])],
  [REPLACE, /* @__PURE__ */ new Set(["type", "units", "default", "config", "mandatory", "min-elements", "max-elements"])]
]);
var EXTENSION = "extension";
var RPC = "rpc";
var ACTION = "action";
var NOTIFICATION = "notification";
var INPUT = "input";
var OUTPUT = "output";
var UNSUPPORTED_CONSTRUCT_KEYWORDS = /* @__PURE__ */ new Set();

// ts/src/xpath/ast.ts
function stepPrefix(step) {
  if (step === "." || step === ".." || !step.includes(":")) return void 0;
  return step.slice(0, step.indexOf(":"));
}
function isWildcardStep(step) {
  return step === "*" || step.endsWith(":*");
}

// ts/src/xpath/functions.ts
var XPATH_FUNCTION_NAMES = /* @__PURE__ */ new Set([
  "boolean",
  "concat",
  "contains",
  "count",
  "current",
  "deref",
  "derived-from",
  "derived-from-or-self",
  "false",
  "not",
  "number",
  "starts-with",
  "string",
  "string-length",
  "substring",
  "substring-after",
  "substring-before",
  "translate",
  "true"
]);
var UNKNOWN_FUNCTION_CODE = "xpath-unknown-function";
function unknownFunctionError(name, expression) {
  const key2 = name.toLowerCase();
  return new UnsupportedXPathError(`${UNKNOWN_FUNCTION_CODE}: unknown XPath function '${key2}'`, {
    expression,
    construct: key2,
    code: UNKNOWN_FUNCTION_CODE
  });
}

// ts/src/xpath/tokenizer.ts
var OPERATOR_NAMES = /* @__PURE__ */ new Set(["and", "or", "div", "mod"]);
function starIsNameTest(tokens) {
  const prev = tokens[tokens.length - 1];
  if (!prev) return true;
  switch (prev.kind) {
    case "operator":
    case "slash":
    case "paren_open":
    case "bracket_open":
    case "comma":
      return true;
    case "identifier":
      return OPERATOR_NAMES.has(prev.value.toLowerCase());
    default:
      return false;
  }
}
var OPERATORS = ["<=", ">=", "!=", "==", "//", "=", "<", ">", "+", "-", "*", "/"];
function tokenizeXPath(expr) {
  const tokens = [];
  let position = 0;
  const add = (kind, value, at = position) => {
    tokens.push({ kind, value, position: at });
  };
  while (position < expr.length) {
    const ch = expr[position];
    if (/\s/.test(ch)) {
      position += 1;
      continue;
    }
    if (ch === '"' || ch === "'") {
      const quote = ch;
      const start = position;
      position += 1;
      let value = "";
      while (position < expr.length) {
        const c = expr[position];
        if (c === quote && expr[position - 1] !== "\\") {
          position += 1;
          break;
        }
        value += c;
        position += 1;
      }
      add("string", value, start);
      continue;
    }
    if (/\d/.test(ch) || ch === "-" && /\d/.test(expr[position + 1] ?? "")) {
      const start = position;
      let value = "";
      if (expr[position] === "-") {
        value += "-";
        position += 1;
      }
      while (position < expr.length && /\d/.test(expr[position])) {
        value += expr[position];
        position += 1;
      }
      if (expr[position] === "." && /\d/.test(expr[position + 1] ?? "")) {
        value += ".";
        position += 1;
        while (position < expr.length && /\d/.test(expr[position])) {
          value += expr[position];
          position += 1;
        }
      }
      add("number", value, start);
      continue;
    }
    if (/[A-Za-z_]/.test(ch)) {
      const start = position;
      let value = "";
      while (position < expr.length && /[A-Za-z0-9_:\-]/.test(expr[position])) {
        value += expr[position];
        position += 1;
      }
      if (value.endsWith(":") && expr[position] === "*") {
        value += "*";
        position += 1;
      }
      add("identifier", value, start);
      continue;
    }
    if (ch === "*" && starIsNameTest(tokens)) {
      add("identifier", "*");
      position += 1;
      continue;
    }
    if (ch === "/") {
      if (expr[position + 1] === "/") {
        add("operator", "//");
        position += 2;
      } else {
        add("slash", "/");
        position += 1;
      }
      continue;
    }
    if (ch === ".") {
      if (expr[position + 1] === ".") {
        add("dotdot", "..");
        position += 2;
      } else {
        add("dot", ".");
        position += 1;
      }
      continue;
    }
    if (ch === "(") {
      add("paren_open", "(");
      position += 1;
      continue;
    }
    if (ch === ")") {
      add("paren_close", ")");
      position += 1;
      continue;
    }
    if (ch === "[") {
      add("bracket_open", "[");
      position += 1;
      continue;
    }
    if (ch === "]") {
      add("bracket_close", "]");
      position += 1;
      continue;
    }
    if (ch === ",") {
      add("comma", ",");
      position += 1;
      continue;
    }
    const remaining = expr.slice(position);
    const op = OPERATORS.find((candidate) => remaining.startsWith(candidate));
    if (op) {
      add("operator", op);
      position += op.length;
      continue;
    }
    position += 1;
  }
  add("eof", "", position);
  return tokens;
}

// ts/src/xpath/parser.ts
var COMPARISON_OPS = /* @__PURE__ */ new Set(["=", "!=", "<", ">", "<=", ">="]);
var ADDITIVE_OPS = /* @__PURE__ */ new Set(["+", "-"]);
var XPathParser = class {
  constructor(expression) {
    this.expression = expression;
    this.tokens = tokenizeXPath(expression);
  }
  expression;
  tokens;
  position = 0;
  parse() {
    if (this.current().kind === "eof") {
      throw new XPathSyntaxError("Empty expression", { expression: this.expression, position: 0 });
    }
    const node2 = this.parseExpression();
    this.expectEof();
    return node2;
  }
  expectEof() {
    const token = this.current();
    if (token.kind !== "eof") {
      throw new XPathSyntaxError(`Unexpected token: ${token.value || token.kind}`, {
        expression: this.expression,
        position: token.position
      });
    }
  }
  current() {
    return this.tokens[this.position] ?? { kind: "eof", value: "", position: this.expression.length };
  }
  consume(expectedKind) {
    const token = this.current();
    if (expectedKind && token.kind !== expectedKind) {
      throw new XPathSyntaxError(`Expected ${expectedKind}, got ${token.kind} (${token.value})`, {
        expression: this.expression,
        position: token.position
      });
    }
    this.position += 1;
    return token;
  }
  isKeyword(value) {
    const token = this.current();
    return token.kind === "identifier" && token.value.toLowerCase() === value.toLowerCase();
  }
  parseExpression() {
    return this.parseLogicalOr();
  }
  parseLogicalOr() {
    let left = this.parseLogicalAnd();
    while (this.isKeyword("or")) {
      this.consume();
      const right = this.parseLogicalAnd();
      left = { kind: "binary", operator: "or", left, right };
    }
    return left;
  }
  parseLogicalAnd() {
    let left = this.parseComparison();
    while (this.isKeyword("and")) {
      this.consume();
      const right = this.parseComparison();
      left = { kind: "binary", operator: "and", left, right };
    }
    return left;
  }
  parseComparison() {
    let left = this.parseAdditive();
    const token = this.current();
    if (token.kind === "operator" && COMPARISON_OPS.has(token.value)) {
      const op = this.consume("operator").value;
      const right = this.parseAdditive();
      left = { kind: "binary", operator: op, left, right };
    }
    return left;
  }
  parseAdditive() {
    let left = this.parseMultiplicative();
    while (true) {
      const token = this.current();
      if (token.kind === "operator" && ADDITIVE_OPS.has(token.value)) {
        const op = this.consume("operator").value;
        const right = this.parseMultiplicative();
        left = { kind: "binary", operator: op, left, right };
      } else {
        return left;
      }
    }
  }
  parseMultiplicative() {
    let left = this.parseUnary();
    while (true) {
      const token = this.current();
      if (token.kind === "slash") {
        this.consume("slash");
        const right = this.parsePath(false);
        left = { kind: "binary", operator: "/", left, right };
      } else if (token.kind === "operator" && token.value === "*") {
        this.consume("operator");
        const right = this.parseUnary();
        left = { kind: "binary", operator: "*", left, right };
      } else if (this.isKeyword("div") || this.isKeyword("mod")) {
        const op = this.consume().value.toLowerCase();
        const right = this.parseUnary();
        left = { kind: "binary", operator: op, left, right };
      } else {
        return left;
      }
    }
  }
  parseUnary() {
    const token = this.current();
    if (token.kind === "operator" && token.value === "-") {
      this.consume("operator");
      const operand = this.parseUnary();
      return { kind: "binary", operator: "-", left: { kind: "literal", value: 0 }, right: operand };
    }
    if (token.kind === "operator" && token.value === "+") {
      this.consume("operator");
      return this.parseUnary();
    }
    if (this.isKeyword("not")) {
      this.consume();
      this.consume("paren_open");
      const arg = this.parseExpression();
      this.consume("paren_close");
      return { kind: "function", name: "not", args: [arg] };
    }
    return this.parsePrimary();
  }
  parsePrimary() {
    const token = this.current();
    if (token.kind === "string") {
      return { kind: "literal", value: this.consume("string").value };
    }
    if (token.kind === "number") {
      const raw = this.consume("number").value;
      const parsed = raw.includes(".") ? Number.parseFloat(raw) : Number.parseInt(raw, 10);
      if (Number.isNaN(parsed)) {
        throw new XPathSyntaxError(`Invalid number: ${raw}`, {
          expression: this.expression,
          position: token.position
        });
      }
      return { kind: "literal", value: parsed };
    }
    if (token.kind === "identifier") {
      if (this.isKeyword("true")) {
        this.consume();
        if (this.current().kind === "paren_open") {
          this.consume("paren_open");
          this.consume("paren_close");
        }
        return { kind: "literal", value: true };
      }
      if (this.isKeyword("false")) {
        this.consume();
        if (this.current().kind === "paren_open") {
          this.consume("paren_open");
          this.consume("paren_close");
        }
        return { kind: "literal", value: false };
      }
      const next = this.tokens[this.position + 1];
      if (next?.kind === "paren_open") {
        return this.parseFunctionCall();
      }
      return this.parsePath(false);
    }
    if (token.kind === "dot") {
      this.consume("dot");
      if (this.current().kind === "paren_open") {
        this.consume("paren_open");
        this.consume("paren_close");
        return { kind: "function", name: "current", args: [] };
      }
      return this.parsePath(false, ".");
    }
    if (token.kind === "dotdot") {
      return this.parsePath(false);
    }
    if (token.kind === "slash") {
      this.consume("slash");
      return this.parsePath(true);
    }
    if (token.kind === "paren_open") {
      this.consume("paren_open");
      if (this.current().kind === "string" || this.current().kind === "number") {
        const mark = this.position;
        const first = this.parsePrimary();
        if (first.kind === "literal" && this.current().kind === "comma") {
          const values = [first.value];
          while (this.current().kind === "comma") {
            this.consume("comma");
            const nextLiteral = this.parsePrimary();
            if (nextLiteral.kind !== "literal") {
              throw new XPathSyntaxError("Value list may only contain literals", {
                expression: this.expression,
                position: this.current().position
              });
            }
            values.push(nextLiteral.value);
          }
          this.consume("paren_close");
          return { kind: "literal", value: values };
        }
        if (this.current().kind === "paren_close") {
          this.consume("paren_close");
          return first;
        }
        this.position = mark;
      }
      const inner = this.parseExpression();
      this.consume("paren_close");
      return inner;
    }
    throw new XPathSyntaxError(`Unexpected token: ${token.value || token.kind}`, {
      expression: this.expression,
      position: token.position
    });
  }
  parseFunctionCall() {
    const name = this.consume("identifier").value;
    this.consume("paren_open");
    const args = [];
    if (this.current().kind !== "paren_close") {
      args.push(this.parseExpression());
      while (this.current().kind === "comma") {
        this.consume("comma");
        args.push(this.parseExpression());
      }
    }
    this.consume("paren_close");
    if (!XPATH_FUNCTION_NAMES.has(name.toLowerCase())) {
      throw unknownFunctionError(name, this.expression);
    }
    const node2 = { kind: "function", name, args };
    return node2;
  }
  parsePath(isAbsolute, firstStep, allowPredicate = true) {
    const segments = [];
    const pushStep = (step) => {
      const segment = { step };
      segments.push(segment);
      while (this.current().kind === "bracket_open") {
        if (!allowPredicate) {
          throw new XPathSyntaxError("Predicates are not allowed in this path context", {
            expression: this.expression,
            position: this.current().position
          });
        }
        this.consume("bracket_open");
        const pred = this.parseExpression();
        if (segment.predicate === void 0) {
          segment.predicate = pred;
        } else {
          segment.predicate = { kind: "binary", operator: "and", left: segment.predicate, right: pred };
        }
        this.consume("bracket_close");
      }
      if (this.current().kind === "slash") {
        this.consume("slash");
        return true;
      }
      return false;
    };
    if (firstStep !== void 0) {
      if (!pushStep(firstStep)) {
        const node3 = { kind: "path", segments, isAbsolute };
        return node3;
      }
    }
    while (this.current().kind === "dot" || this.current().kind === "dotdot" || this.current().kind === "identifier") {
      const step = this.consume().value;
      if (!pushStep(step)) {
        break;
      }
    }
    const node2 = { kind: "path", segments, isAbsolute };
    return node2;
  }
  parsePathExpression(options = {}) {
    const allowPredicate = options.allowPredicate ?? true;
    if (this.current().kind === "eof") {
      throw new XPathSyntaxError("Empty path expression", {
        expression: this.expression,
        position: 0
      });
    }
    let isAbsolute = false;
    if (this.current().kind === "slash") {
      isAbsolute = true;
      this.consume("slash");
    }
    const node2 = this.parsePath(isAbsolute, void 0, allowPredicate);
    this.expectEof();
    if (node2.kind === "path") {
      for (const segment of node2.segments) {
        if (isWildcardStep(segment.step)) {
          throw new XPathSyntaxError(`Wildcard '${segment.step}' is not allowed in a schema path`, {
            expression: this.expression
          });
        }
      }
    }
    return node2;
  }
};
function parseXPath(expression) {
  return new XPathParser(expression).parse();
}
function parseXPathPath(expression, options = {}) {
  return new XPathParser(expression).parsePathExpression(options);
}
function bindXPathPrefixes(node2, resolve2, expression = "") {
  if (!node2) return;
  switch (node2.kind) {
    case "path":
      for (const segment of node2.segments) {
        const prefix = stepPrefix(segment.step);
        if (prefix !== void 0) {
          const module = resolve2(prefix);
          if (module === void 0) {
            throw new YangSyntaxError(`xpath: unknown prefix '${prefix}' in '${segment.step}' of '${expression}'`);
          }
          segment.module = module;
        }
        bindXPathPrefixes(segment.predicate, resolve2, expression);
      }
      return;
    case "binary":
      bindXPathPrefixes(node2.left, resolve2, expression);
      bindXPathPrefixes(node2.right, resolve2, expression);
      return;
    case "function":
      for (const arg of node2.args) bindXPathPrefixes(arg, resolve2, expression);
      return;
    default:
  }
}
function xpathPrefixes(node2, found = /* @__PURE__ */ new Set()) {
  if (!node2) return found;
  switch (node2.kind) {
    case "path":
      for (const segment of node2.segments) {
        const prefix = stepPrefix(segment.step);
        if (prefix !== void 0) found.add(prefix);
        xpathPrefixes(segment.predicate, found);
      }
      break;
    case "binary":
      xpathPrefixes(node2.left, found);
      xpathPrefixes(node2.right, found);
      break;
    case "function":
      for (const arg of node2.args) xpathPrefixes(arg, found);
      break;
    default:
  }
  return found;
}

// ts/src/core/ast.ts
var YangStatementList = class {
  statements;
  constructor(statements = []) {
    this.statements = statements;
  }
  findStatement(name) {
    return this.statements.find((stmt) => stmt.name === name);
  }
  getAllLeaves() {
    const leaves = [];
    for (const stmt of this.statements) {
      leaves.push(...this.collectLeaves(stmt));
    }
    return leaves;
  }
  collectLeaves(stmt) {
    if (stmt instanceof YangLeafStmt) {
      return [stmt];
    }
    if (stmt instanceof YangContainerStmt || stmt instanceof YangListStmt) {
      const leaves = [];
      for (const child2 of stmt.statements) {
        leaves.push(...this.collectLeaves(child2));
      }
      return leaves;
    }
    return [];
  }
};
var YangStatement2 = class extends YangStatementList {
  keyword;
  name;
  description;
  reference;
  units;
  /** Submodule that contributed this statement. Absent on statements written in the module file. */
  included_from;
  constructor(init = {}) {
    super(init.statements ?? []);
    this.keyword = init.keyword ?? "";
    this.name = init.name ?? "";
    this.description = init.description ?? "";
    this.reference = init.reference ?? "";
    this.units = init.units ?? "";
    if (typeof init.included_from === "string" && init.included_from.length > 0) {
      this.included_from = init.included_from;
    }
  }
  get_schema_node() {
    return void 0;
  }
  getSchemaNode() {
    return this.get_schema_node();
  }
  child_names(_data) {
    return this.name ? /* @__PURE__ */ new Set([this.name]) : /* @__PURE__ */ new Set();
  }
  childNames(data) {
    return this.child_names(data);
  }
};
var YangStatementWithMust = class extends YangStatement2 {
  must_statements;
  constructor(init = {}) {
    super(init);
    this.must_statements = init.must_statements ?? [];
  }
};
var YangStatementWithWhen = class extends YangStatement2 {
  when;
  if_features;
  /** RFC 7950 §7.21.1; undefined means inherit from parent. */
  config;
  constructor(init = {}) {
    super(init);
    this.when = init.when;
    this.if_features = init.if_features ?? [];
    this.config = init.config;
  }
  get_schema_node() {
    return this.name || void 0;
  }
};
var YangTypedefStmt = class extends YangStatement2 {
  scope;
  type;
  default;
  constructor(init = {}) {
    super(init);
    this.keyword = "typedef";
    this.scope = init.scope;
    this.type = init.type;
    this.default = init.default;
  }
  get_schema_node() {
    return this.name || void 0;
  }
};
var YangIdentityStmt = class extends YangStatement2 {
  bases;
  if_features;
  constructor(init = {}) {
    super(init);
    this.keyword = "identity";
    this.bases = init.bases ?? [];
    this.if_features = init.if_features ?? [];
  }
  get_schema_node() {
    return void 0;
  }
};
var YangBitStmt = class {
  name;
  position;
  /** RFC 7950 §9.7.4. The bit is absent from the type when every expression is not satisfied. */
  if_features;
  constructor(init = {}) {
    this.name = init.name ?? "";
    this.position = init.position;
    this.if_features = init.if_features ?? [];
  }
};
var YangPatternSpec = class {
  pattern;
  invert_match;
  error_message;
  error_app_tag;
  /** Compiles the XSD regex, so an unsupported pattern fails when the module loads. */
  constructor(init = {}) {
    this.pattern = init.pattern ?? "";
    if (this.pattern) {
      translateXsdRegex(this.pattern);
    }
    this.invert_match = init.invert_match ?? false;
    this.error_message = init.error_message;
    this.error_app_tag = init.error_app_tag;
  }
};
var YangTypeStmt = class {
  name;
  constructor(init = {}) {
    this.name = init.name ?? "";
    if (init.prefix !== void 0) this.prefix = init.prefix;
    if (init.scope_module !== void 0) this.scope_module = init.scope_module;
    if (init.context !== void 0) this.context = init.context;
    if (init.units !== void 0) this.units = init.units;
  }
};
var YangRestriction = class {
  expression;
  constructor(expression, metadata = {}) {
    this.expression = expression;
    for (const key2 of ["error_message", "error_app_tag", "description", "reference"]) {
      if (metadata[key2] !== void 0 && metadata[key2] !== "") this[key2] = metadata[key2];
    }
  }
};
var YangNumericTypeStmt = class extends YangTypeStmt {
};
var YangDecimalTypeStmt = class extends YangNumericTypeStmt {
};
var YangBinaryTypeStmt = class extends YangTypeStmt {
};
var YangStringTypeStmt = class extends YangBinaryTypeStmt {
};
var YangEnumerationTypeStmt = class extends YangTypeStmt {
  enums = [];
  /** Enum name to ``if-feature`` expressions (RFC 7950 §9.6.4). */
  enum_if_features = {};
};
var YangBitsTypeStmt = class extends YangTypeStmt {
  bits = [];
};
var YangUnionTypeStmt = class extends YangTypeStmt {
  types = [];
};
var YangInstanceIdentifierTypeStmt = class extends YangTypeStmt {
  require_instance = true;
};
var YangLeafrefTypeStmt = class extends YangInstanceIdentifierTypeStmt {
};
var YangIdentityrefTypeStmt = class extends YangTypeStmt {
  identityref_bases = [];
};
var YangDerivedTypeStmt = class extends YangTypeStmt {
};
var TYPE_STATEMENT_CLASSES = {
  plain: YangTypeStmt,
  numeric: YangNumericTypeStmt,
  decimal: YangDecimalTypeStmt,
  binary: YangBinaryTypeStmt,
  string: YangStringTypeStmt,
  enumeration: YangEnumerationTypeStmt,
  bits: YangBitsTypeStmt,
  union: YangUnionTypeStmt,
  leafref: YangLeafrefTypeStmt,
  identityref: YangIdentityrefTypeStmt,
  "instance-identifier": YangInstanceIdentifierTypeStmt,
  derived: YangDerivedTypeStmt
};
function createTypeStmt(init) {
  const Constructor = TYPE_STATEMENT_CLASSES[typeStatementKind(init.name, init.prefix)];
  return new Constructor(init);
}
var YangContainerStmt = class extends YangStatementWithWhen {
  must_statements;
  presence;
  /** Groupings declared in this container. Visible here and in descendants only. */
  groupings;
  constructor(init = {}) {
    super(init);
    this.keyword = "container";
    this.must_statements = init.must_statements ?? [];
    this.presence = init.presence;
    this.groupings = init.groupings ?? {};
  }
};
var YangNotificationStmt = class extends YangContainerStmt {
  constructor(init = {}) {
    super(init);
    this.keyword = "notification";
  }
};
var YangInputStmt = class extends YangContainerStmt {
  constructor(init = {}) {
    super({ name: "input", ...init });
    this.keyword = "input";
  }
};
var YangOutputStmt = class extends YangContainerStmt {
  constructor(init = {}) {
    super({ name: "output", ...init });
    this.keyword = "output";
  }
};
var YangRpcStmt = class extends YangStatementWithWhen {
  must_statements;
  constructor(init = {}) {
    super(init);
    this.keyword = "rpc";
    this.must_statements = init.must_statements ?? [];
  }
};
var YangActionStmt = class extends YangRpcStmt {
  constructor(init = {}) {
    super(init);
    this.keyword = "action";
  }
};
var YangListStmt = class extends YangStatementWithWhen {
  must_statements;
  key;
  min_elements;
  max_elements;
  /** One entry per `unique` statement: descendant paths with prefixes stripped (`a/b`). */
  unique;
  constructor(init = {}) {
    super(init);
    this.keyword = "list";
    this.must_statements = init.must_statements ?? [];
    this.key = init.key;
    this.unique = init.unique ?? [];
    this.min_elements = init.min_elements;
    this.max_elements = init.max_elements;
  }
};
var YangLeafStmt = class extends YangStatementWithWhen {
  must_statements;
  type;
  mandatory;
  default;
  constructor(init = {}) {
    super(init);
    this.keyword = "leaf";
    this.must_statements = init.must_statements ?? [];
    this.type = init.type;
    this.mandatory = init.mandatory ?? false;
    this.default = init.default;
  }
};
var YangLeafListStmt = class extends YangStatementWithWhen {
  must_statements;
  type;
  min_elements;
  max_elements;
  defaults;
  constructor(init = {}) {
    super(init);
    this.keyword = "leaf-list";
    this.must_statements = init.must_statements ?? [];
    this.type = init.type;
    this.min_elements = init.min_elements;
    this.max_elements = init.max_elements;
    this.defaults = init.defaults ?? [];
  }
};
var YangAnydataStmt = class extends YangStatementWithWhen {
  must_statements;
  mandatory;
  constructor(init = {}) {
    super(init);
    this.keyword = "anydata";
    this.must_statements = init.must_statements ?? [];
    this.mandatory = init.mandatory ?? false;
  }
};
var YangAnyxmlStmt = class extends YangStatementWithWhen {
  must_statements;
  mandatory;
  constructor(init = {}) {
    super(init);
    this.keyword = "anyxml";
    this.must_statements = init.must_statements ?? [];
    this.mandatory = init.mandatory ?? false;
  }
};
var YangExtensionStmt = class extends YangStatement2 {
  argument_name;
  argument_yin_element;
  apply_callback;
  constructor(init = {}) {
    super(init);
    this.keyword = "extension";
    this.argument_name = init.argument_name ?? "";
    this.argument_yin_element = init.argument_yin_element;
    this.apply_callback = init.apply_callback;
  }
  apply(invocation, options) {
    if (!this.apply_callback) {
      return invocation;
    }
    return this.apply_callback(invocation, options.context_module);
  }
  get_schema_node() {
    return void 0;
  }
};
var YangExtensionInvocationStmt = class extends YangStatementWithWhen {
  must_statements;
  prefix;
  resolved_module;
  resolved_extension;
  argument;
  constructor(init) {
    super(init);
    this.keyword = "extension-invocation";
    this.must_statements = init.must_statements ?? [];
    this.prefix = init.prefix;
    this.resolved_module = init.resolved_module;
    this.resolved_extension = init.resolved_extension;
    this.argument = init.argument;
    if (!this.prefix) {
      throw new Error("extension invocation requires a non-empty prefix");
    }
    if (!this.resolved_module) {
      throw new Error("extension invocation requires resolved_module");
    }
    if (!this.resolved_extension) {
      throw new Error("extension invocation requires resolved_extension");
    }
  }
  get_schema_node() {
    return void 0;
  }
};
function modulePrefixResolver(module, file) {
  const scope = module;
  return (prefix) => {
    const own = (scope.prefix ?? "").replace(/^['"]|['"]$/g, "");
    const imports = file ? scope.file_imports?.[file] : scope.import_prefixes;
    const target = prefix === own ? scope : imports?.[prefix];
    return target ? target.belongs_to_module || target.name : void 0;
  };
}
var YangParsedXPathBase = class {
  expression;
  description;
  ast;
  /** Module each prefixed step (`prefix:name`, `prefix:*`) is bound to, by prefix; recorded by {@link bindPrefixes}. */
  xpath_prefixes;
  constructor(init) {
    this.expression = init.expression;
    this.description = init.description ?? "";
    if (this.expression) {
      this.ast = parseXPath(this.expression);
    }
  }
  /** Bind prefixed steps to the modules `module` maps their prefixes to in file *file*; an unknown prefix throws. */
  bindPrefixes(module, file) {
    const used = xpathPrefixes(this.ast);
    if (used.size === 0) return;
    const resolve2 = modulePrefixResolver(module, file);
    bindXPathPrefixes(this.ast, resolve2, this.expression);
    this.xpath_prefixes = Object.fromEntries([...used].map((prefix) => [prefix, resolve2(prefix)]));
  }
};
var YangMustStmt = class extends YangParsedXPathBase {
  error_message;
  error_app_tag;
  constructor(init) {
    super(init);
    this.error_message = init.error_message ?? "";
    this.error_app_tag = init.error_app_tag ?? "";
  }
};
var YangWhenStmt = class extends YangParsedXPathBase {
  evaluate_with_parent_context;
  constructor(init) {
    super(init);
    this.evaluate_with_parent_context = init.evaluate_with_parent_context ?? false;
  }
  get condition() {
    return this.expression;
  }
};
var YangGroupingStmt = class extends YangStatement2 {
  constructor(init = {}) {
    super(init);
    this.keyword = "grouping";
  }
};
var YangUsesStmt = class extends YangStatementWithWhen {
  /**
   * Local grouping identifier (never ``prefix:name``).
   * Optional import prefix is in {@link grouping_prefix}.
   */
  grouping_name;
  /** Import prefix when ``uses`` names a grouping from another module. */
  grouping_prefix;
  refines;
  augmentations;
  constructor(init = {}) {
    super(init);
    this.keyword = "uses";
    this.grouping_name = init.grouping_name ?? "";
    this.grouping_prefix = init.grouping_prefix;
    this.refines = init.refines ?? [];
    this.augmentations = init.augmentations ?? [];
  }
  /** Display / cycle-key form ``name`` or ``prefix:name``. */
  grouping_qname() {
    return this.grouping_prefix ? `${this.grouping_prefix}:${this.grouping_name}` : this.grouping_name;
  }
  get_schema_node() {
    return void 0;
  }
};
var YangAugmentStmt = class extends YangStatementWithWhen {
  /** Original path string (display / round-trip). */
  augment_path;
  /** Path segments parsed once from {@link augment_path}. */
  augment_path_segments;
  constructor(init = {}) {
    super(init);
    this.keyword = "augment";
    this.augment_path = init.augment_path ?? "";
    this.augment_path_segments = init.augment_path_segments ?? [];
  }
  get_schema_node() {
    return void 0;
  }
};
var YangRefineStmt = class extends YangStatementWithMust {
  target_path;
  type;
  min_elements;
  max_elements;
  refined_defaults;
  refined_mandatory;
  refined_config;
  if_features;
  constructor(init = {}) {
    super(init);
    this.keyword = "refine";
    this.target_path = init.target_path ?? "";
    this.type = init.type;
    this.min_elements = init.min_elements;
    this.max_elements = init.max_elements;
    this.refined_defaults = init.refined_defaults ?? [];
    this.refined_mandatory = init.refined_mandatory;
    this.refined_config = init.refined_config;
    this.if_features = init.if_features ?? [];
  }
};
var YangChoiceStmt = class extends YangStatementWithWhen {
  mandatory;
  cases;
  /** RFC 7950 §7.9.3 case name. */
  default;
  constructor(init = {}) {
    super(init);
    this.keyword = "choice";
    this.mandatory = init.mandatory ?? false;
    this.cases = init.cases ?? [];
    this.default = init.default;
  }
  child_names(data) {
    for (const c of this.cases) {
      if (c.statements.some((s) => s.name && s.name in data)) {
        return new Set(c.statements.map((s) => s.name).filter((name) => Boolean(name)));
      }
    }
    return /* @__PURE__ */ new Set();
  }
  validate_case_unique_child_names() {
    const seen = /* @__PURE__ */ new Map();
    for (const c of this.cases) {
      for (const sub of c.statements) {
        const seg = sub.get_schema_node();
        if (!seg) {
          continue;
        }
        if (seen.has(seg)) {
          const prevCase = seen.get(seg);
          throw new YangSemanticError(
            `Choice '${this.name}': schema node '${seg}' appears in case '${prevCase}' and again in case '${c.name}' (RFC 7950: names of nodes in the cases of a choice must be unique).`
          );
        }
        seen.set(seg, c.name);
      }
    }
  }
};
var YangCaseStmt = class extends YangStatementWithWhen {
  constructor(init = {}) {
    super(init);
    this.keyword = "case";
  }
  child_names(_data) {
    return new Set(this.statements.map((s) => s.name).filter((name) => Boolean(name)));
  }
};

// ts/src/parser/dispatch-registry.ts
var METADATA_SUBSTATEMENTS = /* @__PURE__ */ new Set([
  DESCRIPTION,
  REFERENCE,
  UNITS,
  STATUS
]);
var DATA_NODE_SUBSTATEMENTS = /* @__PURE__ */ new Set([
  ...METADATA_SUBSTATEMENTS,
  CONFIG,
  TYPEDEF
]);
var DATA_DEF_SUBSTATEMENTS = /* @__PURE__ */ new Set([
  LEAF,
  LEAF_LIST,
  CONTAINER,
  LIST,
  CHOICE,
  ANYDATA,
  ANYXML,
  USES
]);
function parent(rfc, ...parts) {
  const keywords = /* @__PURE__ */ new Set();
  for (const part of parts) {
    for (const keyword of part) {
      keywords.add(keyword);
    }
  }
  return { rfc, keywords };
}
var ioBody = parent(
  "7.14.2",
  METADATA_SUBSTATEMENTS,
  DATA_DEF_SUBSTATEMENTS,
  /* @__PURE__ */ new Set([TYPEDEF, WHEN, MUST, IF_FEATURE])
);
var BODY_STATEMENTS = /* @__PURE__ */ new Set([
  LEAF,
  LIST,
  LEAF_LIST,
  CONTAINER,
  NOTIFICATION,
  RPC,
  ANYDATA,
  ANYXML,
  TYPEDEF,
  GROUPING,
  USES,
  IMPORT,
  INCLUDE,
  REVISION,
  DESCRIPTION,
  REFERENCE,
  FEATURE,
  IDENTITY,
  EXTENSION,
  AUGMENT,
  DEVIATION,
  YANG_VERSION,
  ORGANIZATION,
  CONTACT
]);
var PARENTS = [
  ["module", parent("7.1.1", BODY_STATEMENTS, /* @__PURE__ */ new Set([NAMESPACE, PREFIX]))],
  ["submodule", parent("7.2.1", BODY_STATEMENTS)],
  ["belongs-to", parent("7.2.2", /* @__PURE__ */ new Set([PREFIX]))],
  ["import", parent("7.1.5", /* @__PURE__ */ new Set([PREFIX, REFERENCE, REVISION_DATE, DESCRIPTION]))],
  ["include", parent("7.1.6", /* @__PURE__ */ new Set([PREFIX, REFERENCE, REVISION_DATE, DESCRIPTION]))],
  ["typedef", parent("7.3.1", METADATA_SUBSTATEMENTS, /* @__PURE__ */ new Set([TYPE, DEFAULT]))],
  [
    "type",
    parent(
      "7.4.1",
      /* @__PURE__ */ new Set([
        TYPE,
        PATTERN,
        LENGTH,
        RANGE,
        FRACTION_DIGITS,
        ENUM,
        BIT,
        PATH,
        REQUIRE_INSTANCE,
        BASE,
        UNITS,
        DESCRIPTION,
        REFERENCE
      ])
    )
  ],
  [
    "pattern",
    parent(
      "9.4.5",
      /* @__PURE__ */ new Set([DESCRIPTION, REFERENCE, ERROR_MESSAGE, ERROR_APP_TAG, MODIFIER])
    )
  ],
  ["enum", parent("9.6.4", /* @__PURE__ */ new Set([DESCRIPTION, REFERENCE, IF_FEATURE, VALUE, STATUS]))],
  ["bit", parent("9.7.4", /* @__PURE__ */ new Set([POSITION, DESCRIPTION, REFERENCE, IF_FEATURE]))],
  ["identity", parent("7.18.1", METADATA_SUBSTATEMENTS, /* @__PURE__ */ new Set([BASE, IF_FEATURE]))],
  [
    "leaf",
    parent(
      "7.6.2",
      DATA_NODE_SUBSTATEMENTS,
      /* @__PURE__ */ new Set([TYPE, MANDATORY, DEFAULT, MUST, WHEN, IF_FEATURE])
    )
  ],
  [
    "leaf-list",
    parent(
      "7.7.3",
      DATA_NODE_SUBSTATEMENTS,
      /* @__PURE__ */ new Set([TYPE, MIN_ELEMENTS, MAX_ELEMENTS, ORDERED_BY, WHEN, MUST, IF_FEATURE])
    )
  ],
  [
    "list",
    parent(
      "7.8.1",
      DATA_NODE_SUBSTATEMENTS,
      DATA_DEF_SUBSTATEMENTS,
      /* @__PURE__ */ new Set([
        KEY,
        UNIQUE,
        MIN_ELEMENTS,
        MAX_ELEMENTS,
        ORDERED_BY,
        WHEN,
        MUST,
        IF_FEATURE,
        NOTIFICATION,
        ACTION
      ])
    )
  ],
  [
    "container",
    parent(
      "7.5.2",
      DATA_NODE_SUBSTATEMENTS,
      DATA_DEF_SUBSTATEMENTS,
      /* @__PURE__ */ new Set([PRESENCE, WHEN, MUST, GROUPING, IF_FEATURE, NOTIFICATION, ACTION])
    )
  ],
  [
    "grouping",
    parent(
      "7.12.1",
      METADATA_SUBSTATEMENTS,
      DATA_DEF_SUBSTATEMENTS,
      /* @__PURE__ */ new Set([TYPEDEF, GROUPING, IF_FEATURE, WHEN, MUST, NOTIFICATION, ACTION])
    )
  ],
  [
    "notification",
    parent(
      "7.16.1",
      METADATA_SUBSTATEMENTS,
      DATA_DEF_SUBSTATEMENTS,
      /* @__PURE__ */ new Set([TYPEDEF, WHEN, MUST, IF_FEATURE])
    )
  ],
  [
    "rpc",
    parent("7.14.1", METADATA_SUBSTATEMENTS, /* @__PURE__ */ new Set([WHEN, MUST, INPUT, OUTPUT, IF_FEATURE]))
  ],
  ["action", parent("7.15.1", METADATA_SUBSTATEMENTS, /* @__PURE__ */ new Set([INPUT, OUTPUT, IF_FEATURE]))],
  ["input", ioBody],
  ["output", { rfc: "7.14.3", keywords: ioBody.keywords }],
  [
    "choice",
    parent(
      "7.9.1",
      DATA_NODE_SUBSTATEMENTS,
      /* @__PURE__ */ new Set([WHEN, IF_FEATURE, CASE, MANDATORY, DEFAULT])
    )
  ],
  ["case", parent("7.9.2", DATA_NODE_SUBSTATEMENTS, DATA_DEF_SUBSTATEMENTS, /* @__PURE__ */ new Set([WHEN, IF_FEATURE]))],
  [
    "augment",
    parent(
      "7.17.1",
      DATA_NODE_SUBSTATEMENTS,
      DATA_DEF_SUBSTATEMENTS,
      /* @__PURE__ */ new Set([IF_FEATURE, CASE, WHEN, MUST, NOTIFICATION, ACTION])
    )
  ],
  ["uses", parent("7.13.1", METADATA_SUBSTATEMENTS, /* @__PURE__ */ new Set([WHEN, IF_FEATURE, REFINE, AUGMENT]))],
  [
    "refine",
    parent(
      "7.13.2",
      DATA_NODE_SUBSTATEMENTS,
      /* @__PURE__ */ new Set([
        MUST,
        MIN_ELEMENTS,
        MAX_ELEMENTS,
        ORDERED_BY,
        MANDATORY,
        DEFAULT,
        IF_FEATURE,
        TYPE
      ])
    )
  ],
  ["anydata", parent("7.10.1", DATA_NODE_SUBSTATEMENTS, /* @__PURE__ */ new Set([WHEN, MUST, IF_FEATURE, MANDATORY]))],
  ["anyxml", parent("7.11.1", DATA_NODE_SUBSTATEMENTS, /* @__PURE__ */ new Set([WHEN, MUST, IF_FEATURE, MANDATORY]))],
  ["must", parent("7.5.4", /* @__PURE__ */ new Set([ERROR_MESSAGE, ERROR_APP_TAG, DESCRIPTION, REFERENCE]))],
  ["when", parent("7.21.5", /* @__PURE__ */ new Set([DESCRIPTION, REFERENCE]))],
  ["feature", parent("7.20.1", /* @__PURE__ */ new Set([DESCRIPTION, IF_FEATURE, REFERENCE]))],
  ["if-feature", parent("7.20.2", /* @__PURE__ */ new Set([DESCRIPTION, REFERENCE]))],
  ["extension", parent("7.19.1", /* @__PURE__ */ new Set([ARGUMENT, DESCRIPTION, REFERENCE, IF_FEATURE]))],
  ["argument", parent("7.19.2", /* @__PURE__ */ new Set([YIN_ELEMENT]))],
  ["deviation", parent("7.20.3", /* @__PURE__ */ new Set([DESCRIPTION, REFERENCE, DEVIATE]))],
  ["revision", parent("7.1.9", /* @__PURE__ */ new Set([DESCRIPTION, REFERENCE]))],
  [
    "extension-invocation",
    parent(
      "6.3.1",
      /* @__PURE__ */ new Set([
        IF_FEATURE,
        WHEN,
        MUST,
        DESCRIPTION,
        REFERENCE,
        TYPE,
        USES,
        LEAF,
        LEAF_LIST,
        CONTAINER,
        LIST,
        CHOICE,
        CASE,
        ANYDATA,
        ANYXML
      ])
    )
  ],
  [
    "length",
    parent(
      "9.4.4",
      /* @__PURE__ */ new Set([ERROR_MESSAGE, ERROR_APP_TAG, DESCRIPTION, REFERENCE])
    )
  ],
  [
    "range",
    parent("9.2.4", /* @__PURE__ */ new Set([ERROR_MESSAGE, ERROR_APP_TAG, DESCRIPTION, REFERENCE]))
  ]
];
var DISPATCH_REGISTRY = Object.fromEntries(PARENTS);

// ts/src/parser/statements/anydata.ts
var AnydataStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_anydata(tokens, context) {
    tokens.consume(ANYDATA);
    const name = this.parsers.parse_identifier_argument(tokens, "anydata");
    const stmt = new YangAnydataStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child2, "anydata", `anydata '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
};

// ts/src/parser/statements/anyxml.ts
var AnyxmlStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_anyxml(tokens, context) {
    tokens.consume(ANYXML);
    const name = this.parsers.parse_identifier_argument(tokens, "anyxml");
    const stmt = new YangAnyxmlStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child2, "anyxml", `anyxml '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
};

// ts/src/parser/statements/augment.ts
function writingPrefix(module) {
  const raw = module?.prefix;
  if (typeof raw !== "string") return void 0;
  const prefix = raw.replace(/^['"]+|['"]+$/g, "");
  return prefix.length > 0 ? prefix : void 0;
}
var AugmentStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_augment(tokens, context) {
    tokens.consume(AUGMENT);
    const augment_path = this.parsers.parse_string_concatenation(tokens);
    let augment_path_segments = [];
    const raw = augment_path.replace(/^["']|["']$/g, "");
    if (raw.startsWith("/")) {
      try {
        augment_path_segments = parseAbsoluteSchemaPath(augment_path, writingPrefix(context.module));
      } catch (err) {
        throw new YangSyntaxError(err instanceof Error ? err.message : String(err));
      }
    }
    const stmt = new YangAugmentStmt({ name: "augment", augment_path, augment_path_segments });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child2, "augment", "augment");
      tokens.consume_type(YangTokenType.RBRACE);
    }
    const parent2 = context.current_parent;
    if (parent2 instanceof YangUsesStmt) {
      parent2.augmentations.push(stmt);
    } else {
      this.parsers.add_to_parent_or_module(context, stmt);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
};

// ts/src/parser/statements/deviation.ts
function writingPrefix2(module) {
  const raw = module?.prefix;
  if (typeof raw !== "string") return void 0;
  const prefix = raw.replace(/^['"]+|['"]+$/g, "");
  return prefix.length > 0 ? prefix : void 0;
}
var DeviationStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_deviation(tokens, context) {
    tokens.consume(DEVIATION);
    const path = this.parsers.parse_string_argument(tokens);
    let segments;
    try {
      segments = parseAbsoluteSchemaPath(path, writingPrefix2(context.module));
    } catch (err) {
      throw new YangSyntaxError(err instanceof Error ? err.message : String(err));
    }
    const holder = {
      description: "",
      reference: "",
      not_supported: false,
      target_path: path,
      deviates: []
    };
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const body = context.push_parent(holder);
      this.parsers.parseBody(tokens, body, "deviation", "deviation");
      tokens.consume_type(YangTokenType.RBRACE);
    }
    if (holder.not_supported && holder.deviates.length > 0) {
      tokens.syntaxError(
        `deviation '${path}': 'deviate not-supported' cannot be combined with other deviate statements (RFC 7950 \xA77.20.3.2)`
      );
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    const stmt = new YangStatement({
      keyword: "deviation",
      name: "deviation",
      argument: path,
      deviation_path: path,
      deviation_path_segments: segments,
      not_supported: holder.not_supported,
      deviates: holder.deviates,
      statements: []
    });
    if (holder.description) {
      stmt.description = holder.description;
    }
    if (holder.reference) {
      stmt.reference = holder.reference;
    }
    return stmt;
  }
  parse_deviate_substatement(tokens, context) {
    const holder = context.current_parent;
    tokens.consume(DEVIATE);
    const kind = this.parsers.parse_string_argument(tokens);
    if (kind === NOT_SUPPORTED) {
      if (tokens.peek_type() === YangTokenType.LBRACE) {
        tokens.consume_type(YangTokenType.LBRACE);
        tokens.consume_type(YangTokenType.RBRACE);
      }
      tokens.consume_if_type(YangTokenType.SEMICOLON);
      holder.not_supported = true;
      return;
    }
    const allowed = DEVIATE_SUBSTATEMENTS.get(kind);
    if (!allowed) {
      tokens.syntaxError(`Unknown deviate argument '${kind}'`);
    }
    const deviate = { kind, defaults: [], must: [], unique: [] };
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        const keyword = tokens.peek() ?? "";
        if (!allowed.has(keyword)) {
          tokens.syntaxError(`'${keyword}' is not allowed in 'deviate ${kind}' (RFC 7950 \xA77.20.3.2)`);
        }
        this.parseProperty(tokens, context, deviate, keyword);
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    holder.deviates.push(deviate);
  }
  parseProperty(tokens, context, deviate, keyword) {
    const p = this.parsers;
    if (keyword === MUST) {
      deviate.must.push(p.mustStatement(p.must_parser.parse_must(tokens, context)));
      return;
    }
    if (keyword === TYPE) {
      if (deviate.type !== void 0) {
        tokens.syntaxError(`duplicate 'type' in 'deviate ${deviate.kind}'`);
      }
      deviate.type = p.typeShape(p.type_parser.parse_type(tokens, context));
      return;
    }
    tokens.consume(keyword);
    const named = {
      config: deviate.config !== void 0,
      mandatory: deviate.mandatory !== void 0,
      "min-elements": deviate.min_elements !== void 0,
      "max-elements": deviate.max_elements_set === true,
      units: deviate.units !== void 0
    };
    if (named[keyword]) {
      tokens.syntaxError(`duplicate '${keyword}' in 'deviate ${deviate.kind}'`);
    }
    if (keyword === CONFIG) {
      deviate.config = p.parse_boolean_argument(tokens, "config");
    } else if (keyword === MANDATORY) {
      deviate.mandatory = p.parse_boolean_argument(tokens, "mandatory");
    } else if (keyword === MIN_ELEMENTS) {
      const value = p.parse_integer_or_unbounded(tokens, "min-elements");
      if (value === void 0) {
        tokens.syntaxError("min-elements cannot be 'unbounded'");
      }
      deviate.min_elements = value;
    } else if (keyword === MAX_ELEMENTS) {
      const value = p.parse_integer_or_unbounded(tokens, "max-elements");
      if (value !== void 0) {
        deviate.max_elements = value;
      }
      deviate.max_elements_set = true;
    } else if (keyword === UNITS) {
      deviate.units = p.parse_string_argument(tokens);
    } else if (keyword === DEFAULT) {
      deviate.defaults.push(p.parse_default_value_tokens(tokens));
    } else if (keyword === UNIQUE) {
      const arg = p.parse_string_argument(tokens);
      const paths = arg.split(/\s+/).filter(Boolean).map(
        (path) => path.split("/").filter(Boolean).map((seg) => seg.includes(":") ? seg.slice(seg.indexOf(":") + 1) : seg).join("/")
      );
      if (paths.length === 0) {
        tokens.syntaxError("unique requires at least one descendant path");
      }
      deviate.unique.push(paths);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
};

// ts/src/parser/statements/bits.ts
var BitsStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_type_bit(tokens, context, type_stmt) {
    if (!(type_stmt instanceof YangBitsTypeStmt || type_stmt instanceof YangDerivedTypeStmt)) tokens.syntaxError("bit requires a bits or derived type");
    const bits = type_stmt.bits ??= [];
    tokens.consume(BIT);
    const name = this.parsers.parse_identifier_argument(tokens, "bit");
    const bit = new YangBitStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(bit);
      this.parsers.parseBody(tokens, child2, "bit", "bit");
      tokens.consume_type(YangTokenType.RBRACE);
    }
    if (bits.some((existing) => existing.name === name)) {
      tokens.syntaxError(`Duplicate bit name '${name}' in bits type`);
    }
    bits.push(bit);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_bit_position(tokens, context) {
    tokens.consume(POSITION);
    const parent2 = context.current_parent;
    if (parent2 instanceof YangBitStmt && parent2.position !== void 0) {
      tokens.syntaxError("Duplicate position in bit statement");
    }
    const position = this.parsers.parse_integer_argument(tokens, "position");
    if (parent2 instanceof YangBitStmt) {
      parent2.position = position;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  finalize_bits_type(type_stmt) {
    let max = -1;
    for (const bit of type_stmt.bits) {
      if (bit.position === void 0) {
        bit.position = max + 1;
      }
      max = Math.max(max, bit.position);
    }
  }
};

// ts/src/parser/statements/choice.ts
var INLINE_CHOICE_SCHEMA_KEYS = /* @__PURE__ */ new Set([
  LEAF,
  LEAF_LIST,
  CONTAINER,
  LIST,
  ANYDATA,
  ANYXML,
  CHOICE
]);
var ChoiceStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_choice(tokens, context) {
    tokens.consume(CHOICE);
    const name = this.parsers.parse_identifier_argument(tokens, "choice");
    const stmt = new YangChoiceStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parse_choice_substatement(tokens, child2, name);
      }
      tokens.consume_type(YangTokenType.RBRACE);
      stmt.validate_case_unique_child_names();
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
  parse_choice_substatement(tokens, context, choiceName) {
    const key2 = this.parsers.dispatch_key(tokens);
    if (typeof key2 === "string" && INLINE_CHOICE_SCHEMA_KEYS.has(key2)) {
      this.parse_choice_implicit_case(tokens, context);
      return;
    }
    this.parsers.dispatchSubstatement(tokens, context, "choice", `choice '${choiceName}'`);
  }
  parse_choice_implicit_case(tokens, context) {
    const choice = context.current_parent;
    if (!(choice instanceof YangChoiceStmt)) {
      tokens.syntaxError("internal: implicit choice case outside choice body");
    }
    const caseStmt = new YangCaseStmt({ name: "" });
    const caseCtx = context.push_parent(caseStmt);
    const key2 = this.parsers.dispatch_key(tokens);
    const handler = typeof key2 === "string" ? this.parsers.handlerFor("case", key2) : void 0;
    if (!handler) {
      tokens.syntaxError(`internal: unsupported implicit choice schema '${String(tokens.peek())}'`);
    }
    handler(tokens, caseCtx);
    if (caseStmt.statements.length === 0) {
      tokens.syntaxError("Expected a schema node in implicit choice case (RFC 7950 \xA77.9.2)");
    }
    const first = caseStmt.statements[0];
    const caseName = first.name || first.get_schema_node();
    if (!caseName) {
      tokens.syntaxError("Implicit choice case requires a named schema node (RFC 7950 \xA77.9.2)");
    }
    caseStmt.name = caseName;
    choice.cases.push(caseStmt);
  }
  parse_case(tokens, context) {
    tokens.consume(CASE);
    const name = this.parsers.parse_identifier_argument(tokens, "case");
    const stmt = new YangCaseStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child2, "case", `case '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    const parent2 = context.current_parent;
    if (parent2 instanceof YangChoiceStmt) {
      parent2.cases.push(stmt);
    } else {
      this.parsers.add_to_parent_or_module(context, stmt);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
  parse_choice_mandatory(tokens, context) {
    tokens.consume(MANDATORY);
    const value = this.parsers.parse_boolean_argument(tokens, "mandatory");
    const parent2 = context.current_parent;
    if (parent2 instanceof YangChoiceStmt) {
      parent2.mandatory = value;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_choice_default(tokens, context) {
    tokens.consume(DEFAULT);
    const name = this.parsers.parse_identifier_argument(tokens, "default");
    const parent2 = context.current_parent;
    if (parent2 instanceof YangChoiceStmt) {
      parent2.default = name;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
};

// ts/src/parser/statements/container.ts
var ContainerStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_container(tokens, context) {
    tokens.consume(CONTAINER);
    const name = this.parsers.parse_identifier_argument(tokens, "container");
    const stmt = new YangContainerStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child2, "container", `container '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
};

// ts/src/ext/capabilities.ts
var callbacks = /* @__PURE__ */ new Map();
function key(moduleName2, extensionName) {
  return `${moduleName2}:${extensionName}`;
}
function registerExtensionApplyCallback(moduleName2, extensionName, callback) {
  callbacks.set(key(moduleName2, extensionName), callback);
}
function getExtensionApplyCallback(moduleName2, extensionName) {
  return callbacks.get(key(moduleName2, extensionName));
}
var loaded = false;
function ensureBuiltinExtensionsLoaded() {
  if (loaded) {
    return;
  }
  loaded = true;
  const marker = (invocation) => invocation;
  registerExtensionApplyCallback("ietf-yang-structure-ext", "structure", marker);
  registerExtensionApplyCallback("ietf-yang-structure-ext", "augment-structure", marker);
}

// ts/src/parser/statements/extension.ts
var ExtensionStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_extension_stmt(tokens, context) {
    tokens.consume(EXTENSION);
    const name = this.parsers.parse_identifier_argument(tokens, "extension");
    const ext2 = new YangExtensionStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(ext2);
      this.parsers.parseBody(tokens, child2, "extension", `extension '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    ensureBuiltinExtensionsLoaded();
    const moduleName2 = String(context.module.name ?? "");
    const callback = getExtensionApplyCallback(moduleName2, name);
    if (callback) {
      ext2.apply_callback = callback;
    }
    context.module.extensions[name] = ext2;
    this.parsers.add_to_parent_or_module(context, ext2);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return ext2;
  }
  parse_extension_argument_stmt(tokens, context) {
    tokens.consume(ARGUMENT);
    const arg = this.parsers.parse_identifier_argument(tokens, "argument");
    const parent2 = context.current_parent;
    if (parent2 instanceof YangExtensionStmt) {
      parent2.argument_name = arg;
    }
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      this.parsers.parseBody(tokens, context, "argument", "extension argument");
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_yin_element(tokens, context) {
    tokens.consume(YIN_ELEMENT);
    const value = this.parsers.parse_boolean_argument(tokens, "yin-element");
    const parent2 = context.current_parent;
    if (parent2 instanceof YangExtensionStmt) {
      parent2.argument_yin_element = value;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
};

// ts/src/parser/statements/feature.ts
var FeatureStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_feature_stmt(tokens, context) {
    tokens.consume(FEATURE);
    const name = this.parsers.parse_identifier_argument(tokens, "feature");
    (context.module.features ??= /* @__PURE__ */ new Set()).add(name);
    const featParent = { if_features: [] };
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(featParent);
      this.parsers.parseBody(tokens, child2, "feature", `feature '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    if (featParent.if_features.length > 0) {
      const mod = context.module;
      const fif = mod.feature_if_features ??= {};
      fif[name] = [...featParent.if_features];
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_if_feature_stmt(tokens, context) {
    tokens.consume(IF_FEATURE);
    let expression = this.parsers.parse_string_argument(tokens);
    if (tokens.has_more() && tokens.peek_type() === YangTokenType.COLON) {
      tokens.consume_type(YangTokenType.COLON);
      expression = `${expression}:${tokens.consume()}`;
    }
    const parent2 = context.current_parent;
    if (parent2 && Array.isArray(parent2.if_features)) {
      parent2.if_features.push(expression);
    }
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      this.parsers.parseBody(tokens, context, "if-feature", "if-feature substatement");
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
};

// ts/src/parser/statements/grouping.ts
var GroupingStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_grouping(tokens, context) {
    tokens.consume(GROUPING);
    const name = this.parsers.parse_identifier_argument(tokens, "grouping");
    const stmt = new YangGroupingStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child2, "grouping", `grouping '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    const parent2 = context.current_parent;
    if (parent2 && parent2.keyword === "container" && parent2 !== context.module) {
      (parent2.groupings ??= {})[name] = stmt;
    } else {
      context.module.groupings[name] = stmt;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
};

// ts/src/parser/statements/identity.ts
var IdentityStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_identity(tokens, context) {
    tokens.consume(IDENTITY);
    const name = this.parsers.parse_identifier_argument(tokens, "identity");
    const stmt = new YangIdentityStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child2, "identity", `identity '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    context.module.identities[name] = stmt;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_identity_base(tokens, context) {
    tokens.consume(BASE);
    const base = this.parsers.consume_identifier_ref(tokens);
    const parent2 = context.current_parent;
    if (parent2 instanceof YangIdentityStmt) {
      parent2.bases.push(base);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
};

// ts/src/parser/statements/leaf.ts
var LeafStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_leaf(tokens, context) {
    tokens.consume(LEAF);
    const name = this.parsers.parse_identifier_argument(tokens, "leaf");
    const stmt = new YangLeafStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child2, "leaf", `leaf '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
};

// ts/src/parser/statements/leaf_list.ts
var LeafListStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_leaf_list(tokens, context) {
    tokens.consume(LEAF_LIST);
    const name = this.parsers.parse_identifier_argument(tokens, "leaf-list");
    const stmt = new YangLeafListStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child2, "leaf-list", `leaf-list '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
};

// ts/src/parser/statements/list.ts
var ListStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_list(tokens, context) {
    tokens.consume(LIST);
    const name = this.parsers.parse_identifier_argument(tokens, "list");
    const stmt = new YangListStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child2, "list", `list '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
};

// ts/src/parser/statements/module.ts
var ModuleStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_module(tokens, context) {
    tokens.consume(MODULE);
    context.module.name = this.parsers.parse_identifier_argument(tokens, "module");
    tokens.consume_type(YangTokenType.LBRACE);
    const scoped = context.with_dispatch("module", "module body");
    while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
      this.parsers.parseStatement(tokens, scoped);
    }
    tokens.consume_type(YangTokenType.RBRACE);
  }
  parse_yang_version(tokens, context) {
    tokens.consume(YANG_VERSION);
    const version = this.parsers.parse_string_argument(tokens);
    if (version !== "1" && version !== "1.1") {
      tokens.syntaxError(`yang-version argument must be '1' or '1.1', got '${version}'`);
    }
    context.module.yang_version = version;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_namespace(tokens, context) {
    tokens.consume(NAMESPACE);
    context.module.namespace = this.parsers.parse_string_argument(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_prefix(tokens, context) {
    tokens.consume(PREFIX);
    context.module.prefix = this.parsers.parse_identifier_argument(tokens, "prefix");
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_organization(tokens, context) {
    tokens.consume(ORGANIZATION);
    context.module.organization = this.parsers.parse_string_argument(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_contact(tokens, context) {
    tokens.consume(CONTACT);
    context.module.contact = this.parsers.parse_string_argument(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_import_stmt(tokens, context) {
    tokens.consume(IMPORT);
    const moduleName2 = this.parsers.parse_identifier_argument(tokens, "import");
    let localPrefix;
    let revisionDate;
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const acc = {};
      this.parsers.importAcc = acc;
      try {
        while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
          const tt = this.parsers.dispatch_key(tokens);
          if (typeof tt === "string" && DISPATCH_REGISTRY.import.keywords.has(tt)) {
            this.parsers.dispatchSubstatement(tokens, context, "import", "import");
          } else {
            this.skip_nested_statement(tokens);
          }
        }
      } finally {
        this.parsers.importAcc = void 0;
      }
      localPrefix = acc.localPrefix;
      revisionDate = acc.revisionDate;
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    if (!localPrefix || localPrefix.trim().length === 0) {
      throw new YangSemanticError(`Import '${moduleName2}' is missing required prefix substatement`);
    }
    this.parsers.register_import(context, moduleName2, localPrefix, revisionDate, tokens);
  }
  parse_include_stmt(tokens, context) {
    tokens.consume(INCLUDE);
    const name = this.parsers.parse_identifier_argument(tokens, "include");
    let revisionDate;
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      this.parsers.includeRevisionDate = void 0;
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        const tt = this.parsers.dispatch_key(tokens);
        if (typeof tt === "string" && DISPATCH_REGISTRY.include.keywords.has(tt)) {
          this.parsers.dispatchSubstatement(tokens, context, "include", "include");
        } else {
          this.skip_nested_statement(tokens);
        }
      }
      revisionDate = this.parsers.includeRevisionDate;
      this.parsers.includeRevisionDate = void 0;
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    this.parsers.resolveInclude(context, name, revisionDate, tokens);
  }
  parse_prefix_value_stmt(tokens) {
    tokens.consume(PREFIX);
    this.parsers.parse_identifier_argument(tokens, "prefix");
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  skip_nested_statement(tokens) {
    let depth = 0;
    while (tokens.has_more()) {
      const tt = this.parsers.dispatch_key(tokens);
      if (tt === YangTokenType.LBRACE) {
        depth += 1;
        tokens.consume_type(YangTokenType.LBRACE);
        continue;
      }
      if (tt === YangTokenType.RBRACE) {
        if (depth === 0) {
          return;
        }
        depth -= 1;
        tokens.consume_type(YangTokenType.RBRACE);
        continue;
      }
      if (tt === YangTokenType.SEMICOLON && depth === 0) {
        tokens.consume_type(YangTokenType.SEMICOLON);
        return;
      }
      tokens.consume();
    }
  }
};

// ts/src/parser/statements/notification.ts
var NotificationStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_notification(tokens, context) {
    tokens.consume(NOTIFICATION);
    const name = this.parsers.parse_identifier_argument(tokens, "notification");
    const stmt = new YangNotificationStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child2, "notification", `notification '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
};

// ts/src/parser/statements/rpc.ts
var RpcStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parseIoBlock(tokens, context, keyword, ioStmt) {
    tokens.consume(keyword);
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(ioStmt);
      this.parsers.parseBody(tokens, child2, keyword, `${keyword} block`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, ioStmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return ioStmt;
  }
  parse_input(tokens, context) {
    return this.parseIoBlock(tokens, context, INPUT, new YangInputStmt());
  }
  parse_output(tokens, context) {
    return this.parseIoBlock(tokens, context, OUTPUT, new YangOutputStmt());
  }
  parse_rpc(tokens, context) {
    return this.parseOperation(tokens, context, RPC, new YangRpcStmt());
  }
  /** ``action`` under a container, list, grouping or augment (RFC 7950 §7.15). */
  parse_action(tokens, context) {
    return this.parseOperation(tokens, context, ACTION, new YangActionStmt());
  }
  parseOperation(tokens, context, keyword, stmt) {
    tokens.consume(keyword);
    const name = this.parsers.parse_identifier_argument(tokens, keyword);
    stmt.name = name;
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child2, keyword, `${keyword} '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
};

// ts/src/parser/statements/must.ts
var MustStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_must(tokens, context) {
    tokens.consume(MUST);
    const expression = this.parsers.parse_string_concatenation(tokens);
    const stmt = new YangMustStmt({ expression });
    stmt.bindPrefixes(context.module, this.parsers.includingSubmoduleName);
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child2, "must", "must");
      tokens.consume_type(YangTokenType.RBRACE);
    }
    const parent2 = context.current_parent;
    if (Array.isArray(parent2?.must_statements)) {
      parent2.must_statements.push(stmt);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
  parse_must_error_message(tokens, context) {
    tokens.consume(ERROR_MESSAGE);
    const value = this.parsers.parse_string_argument(tokens);
    const parent2 = context.current_parent;
    if (parent2 instanceof YangMustStmt) {
      parent2.error_message = value;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_must_error_app_tag(tokens, context) {
    tokens.consume(ERROR_APP_TAG);
    const value = this.parsers.parse_string_argument(tokens);
    const parent2 = context.current_parent;
    if (parent2 instanceof YangMustStmt) {
      parent2.error_app_tag = value;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
};

// ts/src/parser/statements/refine.ts
var RefineStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_refine(tokens, context) {
    tokens.consume(REFINE);
    const target_path = this.parsers.parse_string_argument(tokens);
    const stmt = new YangRefineStmt({ name: "refine", target_path });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child2, "refine", `refine '${target_path}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    if (context.current_parent instanceof YangUsesStmt) {
      context.current_parent.refines.push(stmt);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
};

// ts/src/parser/statements/revision.ts
var RevisionStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_revision(tokens, context) {
    tokens.consume(REVISION);
    const date = this.parsers.parse_string_argument(tokens);
    const rev = {
      date,
      description: "",
      reference: ""
    };
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const body = { description: "", reference: "" };
      const child2 = context.push_parent(body);
      this.parsers.parseBody(tokens, child2, "revision", "revision");
      rev.description = body.description;
      rev.reference = body.reference;
      tokens.consume_type(YangTokenType.RBRACE);
    }
    (context.module.revisions ??= []).push(rev);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_revision_date_statement(tokens) {
    tokens.consume(REVISION_DATE);
    const date = this.parsers.parse_string_argument(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return date;
  }
};

// ts/src/parser/statements/submodule.ts
var INCLUDED_STATEMENT_SKIP = /* @__PURE__ */ new Set([
  "yang-version",
  "namespace",
  "prefix",
  "organization",
  "contact",
  "description",
  "reference",
  "revision",
  "import",
  "include",
  "unsupported"
]);
var SubmoduleStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_submodule(tokens, context) {
    tokens.consume(SUBMODULE);
    context.module.name = this.parsers.parse_identifier_argument(tokens, "submodule");
    tokens.consume_type(YangTokenType.LBRACE);
    const scoped = context.with_dispatch("submodule", "submodule body");
    while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
      if (tokens.peek() === BELONGS_TO) {
        this.parse_belongs_to(tokens, context);
      } else {
        const stmt = this.parsers.parseStatement(tokens, scoped);
        if (!INCLUDED_STATEMENT_SKIP.has(stmt.keyword ?? "")) {
          this.parsers.pushIncludedStatement(context, stmt);
        }
      }
    }
    tokens.consume_type(YangTokenType.RBRACE);
  }
  parse_belongs_to(tokens, context) {
    tokens.consume(BELONGS_TO);
    context.module.belongs_to_module = this.parsers.parse_identifier_argument(tokens, "belongs-to");
    tokens.consume_type(YangTokenType.LBRACE);
    this.parsers.parseBody(tokens, context, "belongs-to", "belongs-to");
    tokens.consume_type(YangTokenType.RBRACE);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
};

// ts/src/parser/statements/type.ts
var TypeStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  patternBody;
  restrictionBody;
  parse_type(tokens, context) {
    tokens.consume(TYPE);
    const ref = this.parsers.consume_identifier_ref(tokens);
    const prefix = ref.prefix;
    const name = ref.name;
    const type_stmt = createTypeStmt({ name, prefix, context: context.typedef_context });
    const writer = context.module;
    const scope = writer.belongs_to_module || writer.name;
    if (scope) type_stmt.scope_module = scope;
    if (this.parsers.includingSubmoduleName) {
      type_stmt.source_file = this.parsers.includingSubmoduleName;
    }
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(type_stmt);
      this.parsers.parseBody(tokens, child2, "type", `type '${name}'`, type_stmt);
      tokens.consume_type(YangTokenType.RBRACE);
      if (type_stmt instanceof YangEnumerationTypeStmt && type_stmt.enums.length === 0) {
        tokens.syntaxError("enumeration type must contain at least one enum statement");
      }
    }
    const parent2 = context.current_parent;
    if (parent2 && "type" in parent2 && !parent2.type) {
      parent2.type = type_stmt;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return type_stmt;
  }
  parse_type_base(tokens, _context, type_stmt) {
    if (!(type_stmt instanceof YangIdentityrefTypeStmt)) tokens.syntaxError("base requires an identityref type");
    tokens.consume(BASE);
    type_stmt.identityref_bases.push(this.parsers.consume_identifier_ref(tokens));
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_type_pattern(tokens, _context, type_stmt) {
    if (!(type_stmt instanceof YangStringTypeStmt || type_stmt instanceof YangDerivedTypeStmt)) tokens.syntaxError("pattern requires a string or derived type");
    tokens.consume(PATTERN);
    const pattern = this.parsers.parse_string_concatenation(tokens);
    let invertMatch = false;
    let patternErrorMessage;
    let patternErrorAppTag;
    this.patternBody = { invert: false };
    try {
      if (tokens.consume_if_type(YangTokenType.LBRACE)) {
        this.parsers.parseBody(tokens, _context, "pattern", "pattern");
        tokens.consume_type(YangTokenType.RBRACE);
      }
      invertMatch = this.patternBody.invert;
      patternErrorMessage = this.patternBody.errorMessage;
      patternErrorAppTag = this.patternBody.errorAppTag;
    } finally {
      this.patternBody = void 0;
    }
    (type_stmt.patterns ??= []).push(
      new YangPatternSpec({
        pattern,
        invert_match: invertMatch,
        error_message: patternErrorMessage,
        error_app_tag: patternErrorAppTag
      })
    );
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_type_length(tokens, context, type_stmt) {
    if (!(type_stmt instanceof YangBinaryTypeStmt || type_stmt instanceof YangDerivedTypeStmt)) tokens.syntaxError("length requires a string, binary or derived type");
    tokens.consume(LENGTH);
    const expression = this.parsers.parse_string_argument(tokens);
    const meta = this.parseRestrictionBody(tokens, context, "length");
    type_stmt.length_restriction = new YangRestriction(expression, {
      error_message: meta.errorMessage,
      error_app_tag: meta.errorAppTag,
      description: meta.description,
      reference: meta.reference
    });
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_type_range(tokens, context, type_stmt) {
    if (!(type_stmt instanceof YangNumericTypeStmt || type_stmt instanceof YangDerivedTypeStmt)) tokens.syntaxError("range requires a numeric or derived type");
    tokens.consume(RANGE);
    const expression = this.parsers.parse_string_argument(tokens);
    const meta = this.parseRestrictionBody(tokens, context, "range");
    type_stmt.range_restriction = new YangRestriction(expression, {
      error_message: meta.errorMessage,
      error_app_tag: meta.errorAppTag,
      description: meta.description,
      reference: meta.reference
    });
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parseRestrictionBody(tokens, context, parent2) {
    const holder = { description: "", reference: "", errorMessage: void 0, errorAppTag: void 0 };
    if (!tokens.consume_if_type(YangTokenType.LBRACE)) {
      return holder;
    }
    const body = context.push_parent(holder);
    this.restrictionBody = holder;
    try {
      this.parsers.parseBody(tokens, body, parent2, parent2);
    } finally {
      this.restrictionBody = void 0;
    }
    tokens.consume_type(YangTokenType.RBRACE);
    return holder;
  }
  parse_restriction_error_message(tokens, _context) {
    tokens.consume(ERROR_MESSAGE);
    this.restrictionBody.errorMessage = this.parsers.parse_string_concatenation(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_restriction_error_app_tag(tokens, _context) {
    tokens.consume(ERROR_APP_TAG);
    this.restrictionBody.errorAppTag = this.parsers.parse_string_concatenation(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_type_fraction_digits(tokens, _context, type_stmt) {
    if (!(type_stmt instanceof YangDecimalTypeStmt)) tokens.syntaxError("fraction-digits requires decimal64");
    tokens.consume(FRACTION_DIGITS);
    type_stmt.fraction_digits = this.parsers.parse_integer_argument(tokens, "fraction-digits");
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_type_enum(tokens, context, type_stmt) {
    if (!(type_stmt instanceof YangEnumerationTypeStmt || type_stmt instanceof YangDerivedTypeStmt)) tokens.syntaxError("enum requires an enumeration or derived type");
    tokens.consume(ENUM);
    const enumName = this.parsers.parse_string_argument(tokens);
    (type_stmt.enums ??= []).push(enumName);
    const holder = { if_features: [] };
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      this.parsers.parseBody(tokens, context.push_parent(holder), "enum", `enum '${enumName}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    if (holder.if_features.length > 0) {
      const guards = type_stmt.enum_if_features ??= {};
      guards[enumName] = [...holder.if_features];
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_type_path(tokens, context, type_stmt) {
    if (!(type_stmt instanceof YangLeafrefTypeStmt)) tokens.syntaxError("path requires leafref");
    tokens.consume(PATH);
    const path = this.parsers.parse_string_argument(tokens);
    const ast = parseXPathPath(path);
    if (ast.kind === "path") ast.source = path;
    const used = xpathPrefixes(ast);
    if (used.size > 0) {
      const resolve2 = modulePrefixResolver(context.module, this.parsers.includingSubmoduleName);
      bindXPathPrefixes(ast, resolve2, path);
      type_stmt.xpath_prefixes = Object.fromEntries([...used].map((prefix) => [prefix, resolve2(prefix)]));
    }
    type_stmt.path = ast;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_type_require_instance(tokens, _context, type_stmt) {
    if (!(type_stmt instanceof YangInstanceIdentifierTypeStmt || type_stmt instanceof YangDerivedTypeStmt)) tokens.syntaxError("require-instance requires a reference type");
    tokens.consume(REQUIRE_INSTANCE);
    type_stmt.require_instance = this.parsers.parse_boolean_argument(tokens, "require-instance");
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_pattern_error_message(tokens, _context) {
    tokens.consume(ERROR_MESSAGE);
    this.patternBody.errorMessage = this.parsers.parse_string_concatenation(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_pattern_error_app_tag(tokens, _context) {
    tokens.consume(ERROR_APP_TAG);
    this.patternBody.errorAppTag = this.parsers.parse_string_concatenation(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_pattern_modifier(tokens, _context) {
    tokens.consume(MODIFIER);
    this.parsers.parse_keyword_argument(tokens, "modifier", ["invert-match"]);
    this.patternBody.invert = true;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_enum_value(tokens, _context) {
    tokens.consume(VALUE);
    this.parsers.parse_integer_argument(tokens, "value");
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_enum_status(tokens, _context) {
    this.parsers.parse_status_argument(tokens);
  }
};

// ts/src/parser/statements/typedef.ts
var TypedefStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_typedef(tokens, context) {
    tokens.consume(TYPEDEF);
    const name = this.parsers.parse_identifier_argument(tokens, "typedef");
    const stmt = new YangTypedefStmt({ name, scope: context.typedef_context || void 0 });
    const unsupportedCtx = `typedef '${name}'`;
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child2, "typedef", unsupportedCtx);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    const typedefs = context.module.typedefs;
    const key2 = (stmt.scope ? stmt.scope + "/" : "") + name;
    if (this.parsers.includingSubmoduleName && key2 in typedefs) {
      typedefs[key2] = stmt;
    } else {
      registerTypedef(typedefs, stmt);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
};

// ts/src/parser/statements/uses.ts
var UsesStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_uses(tokens, context) {
    tokens.consume(USES);
    const ref = this.parsers.consume_identifier_ref(tokens);
    const grouping_prefix = ref.prefix;
    const grouping_name = ref.name;
    const stmt = new YangUsesStmt({
      name: "uses",
      grouping_name,
      grouping_prefix
    });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child2, "uses", `uses '${grouping_name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
};

// ts/src/parser/statements/when.ts
var WhenStatementParser = class {
  constructor(parsers) {
    this.parsers = parsers;
  }
  parsers;
  parse_when(tokens, context) {
    tokens.consume(WHEN);
    const expression = this.parsers.parse_string_concatenation(tokens);
    const whenStmt = new YangWhenStmt({ expression });
    whenStmt.bindPrefixes(context.module, this.parsers.includingSubmoduleName);
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child2 = context.push_parent(whenStmt);
      this.parsers.parseBody(tokens, child2, "when", "when");
      tokens.consume_type(YangTokenType.RBRACE);
    }
    if (context.current_parent instanceof YangStatementWithWhen) {
      context.current_parent.when = whenStmt;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
};

// ts/src/parser/unsupported-skip.ts
var UNSUPPORTED_CONSTRUCT_TYPES = UNSUPPORTED_CONSTRUCT_KEYWORDS;
function _consume_balanced_braces(tokens) {
  let depth = 0;
  while (tokens.has_more()) {
    const pt = tokens.peek_type();
    if (pt === YangTokenType.LBRACE) {
      depth += 1;
      tokens.consume_type(YangTokenType.LBRACE);
    } else if (pt === YangTokenType.RBRACE) {
      depth -= 1;
      tokens.consume_type(YangTokenType.RBRACE);
      if (depth === 0) {
        return;
      }
    } else {
      tokens.consume();
    }
  }
}
function skip_unsupported_construct(tokens, { context }) {
  const tok = tokens.peek_token();
  if (!tok || !UNSUPPORTED_CONSTRUCT_TYPES.has(tok.value)) {
    return;
  }
  const kw = tok.value;
  const [line_num, char_pos] = tokens.position();
  const where = tokens.filename ?? "<string>";
  console.warn(`Ignoring unsupported YANG statement '${kw}' (${context}) at ${where}:${line_num}:${char_pos}`);
  tokens.consume();
  while (tokens.has_more()) {
    const pt = tokens.peek_type();
    if (pt === YangTokenType.LBRACE) {
      _consume_balanced_braces(tokens);
      break;
    }
    if (pt === YangTokenType.SEMICOLON) {
      tokens.consume_type(YangTokenType.SEMICOLON);
      return;
    }
    if (pt === YangTokenType.RBRACE) {
      return;
    }
    tokens.consume();
  }
  tokens.consume_if_type(YangTokenType.SEMICOLON);
}
function is_unsupported_construct_start(tokens) {
  const tok = tokens.peek_token();
  return tok !== void 0 && UNSUPPORTED_CONSTRUCT_TYPES.has(tok.value);
}

// ts/src/parser/statement-parsers.ts
function isIdentifierText(text) {
  return /^[A-Za-z_][A-Za-z0-9_.\-]*$/.test(text);
}
function serializedKeywordFromAstStatement(stmt) {
  if (typeof stmt.keyword === "string" && stmt.keyword.trim().length > 0) {
    return stmt.keyword;
  }
  throw new YangSemanticError("Internal error: cannot serialize AST statement without a keyword");
}
var StatementParsers = class {
  /** Set while an ``include``d submodule is being merged into its parent. */
  includingSubmoduleName;
  importResolver;
  includeResolver;
  anydata_parser = new AnydataStatementParser(this);
  anyxml_parser = new AnyxmlStatementParser(this);
  augment_parser = new AugmentStatementParser(this);
  deviation_parser = new DeviationStatementParser(this);
  bits_parser = new BitsStatementParser(this);
  choice_parser = new ChoiceStatementParser(this);
  container_parser = new ContainerStatementParser(this);
  extension_parser = new ExtensionStatementParser(this);
  feature_parser = new FeatureStatementParser(this);
  grouping_parser = new GroupingStatementParser(this);
  identity_parser = new IdentityStatementParser(this);
  leaf_parser = new LeafStatementParser(this);
  leaf_list_parser = new LeafListStatementParser(this);
  list_parser = new ListStatementParser(this);
  module_parser = new ModuleStatementParser(this);
  notification_parser = new NotificationStatementParser(this);
  rpc_parser = new RpcStatementParser(this);
  must_parser = new MustStatementParser(this);
  refine_parser = new RefineStatementParser(this);
  revision_parser = new RevisionStatementParser(this);
  submodule_parser = new SubmoduleStatementParser(this);
  type_parser = new TypeStatementParser(this);
  typedef_parser = new TypedefStatementParser(this);
  uses_parser = new UsesStatementParser(this);
  when_parser = new WhenStatementParser(this);
  /** Captures ``prefix`` / ``revision-date`` while an ``import`` body is open. */
  importAcc;
  /** ``revision-date`` captured while an ``include`` body is open. */
  includeRevisionDate;
  runtimeDispatch = {};
  statementKeywordHandlers = {
    [LEAF]: (tokens, context) => this.fromAst(this.leaf_parser.parse_leaf(tokens, context)),
    [LEAF_LIST]: (tokens, context) => this.fromAst(this.leaf_list_parser.parse_leaf_list(tokens, context)),
    [CONTAINER]: (tokens, context) => this.fromAst(this.container_parser.parse_container(tokens, context)),
    [LIST]: (tokens, context) => this.fromAst(this.list_parser.parse_list(tokens, context)),
    [NOTIFICATION]: (tokens, context) => this.fromAst(this.notification_parser.parse_notification(tokens, context)),
    [RPC]: (tokens, context) => this.fromAst(this.rpc_parser.parse_rpc(tokens, context)),
    [ACTION]: (tokens, context) => this.fromAst(this.rpc_parser.parse_action(tokens, context)),
    [ANYDATA]: (tokens, context) => this.fromAst(this.anydata_parser.parse_anydata(tokens, context)),
    [ANYXML]: (tokens, context) => this.fromAst(this.anyxml_parser.parse_anyxml(tokens, context)),
    [CHOICE]: (tokens, context) => this.fromAst(this.choice_parser.parse_choice(tokens, context)),
    [CASE]: () => {
      throw new YangSyntaxError("'case' is only valid as a substatement of 'choice' (RFC 7950)");
    },
    [INPUT]: () => {
      throw new YangSyntaxError("'input' is only valid as a substatement of 'rpc' or 'action' (RFC 7950)");
    },
    [OUTPUT]: () => {
      throw new YangSyntaxError("'output' is only valid as a substatement of 'rpc' or 'action' (RFC 7950)");
    },
    [TYPEDEF]: (tokens, context) => this.fromAst(this.typedef_parser.parse_typedef(tokens, context)),
    [TYPE]: (tokens, context) => this.fromType(this.type_parser.parse_type(tokens, context)),
    [USES]: (tokens, context) => this.fromAst(this.uses_parser.parse_uses(tokens, context)),
    [REFINE]: (tokens, context) => {
      this.refine_parser.parse_refine(tokens, context);
      return new YangStatement({ keyword: "refine", statements: [] });
    },
    [MUST]: (tokens, context) => this.fromMust(this.must_parser.parse_must(tokens, context)),
    [WHEN]: (tokens, context) => {
      this.when_parser.parse_when(tokens, context);
      return new YangStatement({ keyword: "when", statements: [] });
    },
    [EXTENSION]: (tokens, context) => this.fromAst(this.extension_parser.parse_extension_stmt(tokens, context)),
    [FEATURE]: (tokens, context) => {
      this.feature_parser.parse_feature_stmt(tokens, context);
      return new YangStatement({ keyword: "feature", statements: [] });
    },
    [IF_FEATURE]: (tokens, context) => {
      this.feature_parser.parse_if_feature_stmt(tokens, context);
      return new YangStatement({ keyword: "if-feature", statements: [] });
    },
    [IDENTITY]: (tokens, context) => {
      this.identity_parser.parse_identity(tokens, context);
      return new YangStatement({ keyword: "identity", statements: [] });
    },
    [GROUPING]: (tokens, context) => {
      this.grouping_parser.parse_grouping(tokens, context);
      return new YangStatement({ keyword: "grouping", statements: [] });
    },
    [AUGMENT]: (tokens, context) => this.fromAst(this.augment_parser.parse_augment(tokens, context)),
    [DEVIATION]: (tokens, context) => this.deviation_parser.parse_deviation(tokens, context),
    [REVISION]: (tokens, context) => {
      this.revision_parser.parse_revision(tokens, context);
      return new YangStatement({ keyword: "revision", statements: [] });
    },
    [DESCRIPTION]: (tokens, context) => {
      const desc = this.parse_description(tokens, context);
      return new YangStatement({
        keyword: "description",
        argument: desc,
        name: "description",
        statements: []
      });
    },
    [MANDATORY]: (tokens, context) => {
      this.parse_leaf_mandatory(tokens, context);
      return new YangStatement({ keyword: "mandatory", statements: [] });
    },
    [DEFAULT]: (tokens, context) => {
      this.parse_leaf_default(tokens, context);
      return new YangStatement({ keyword: "default", statements: [] });
    },
    [KEY]: (tokens, context) => {
      this.parse_list_key(tokens, context);
      return new YangStatement({ keyword: "key", statements: [] });
    },
    [UNIQUE]: (tokens, context) => {
      this.parse_list_unique(tokens, context);
      return new YangStatement({ keyword: "unique", statements: [] });
    },
    [MIN_ELEMENTS]: (tokens, context) => {
      this.parse_min_elements(tokens, context);
      return new YangStatement({ keyword: "min-elements", statements: [] });
    },
    [MAX_ELEMENTS]: (tokens, context) => {
      this.parse_max_elements(tokens, context);
      return new YangStatement({ keyword: "max-elements", statements: [] });
    },
    [ORDERED_BY]: (tokens, context) => {
      this.parse_ordered_by(tokens);
      return new YangStatement({ keyword: "ordered-by", statements: [] });
    },
    [PRESENCE]: (tokens, context) => {
      this.parse_presence(tokens, context);
      return new YangStatement({ keyword: "presence", statements: [] });
    },
    [REFERENCE]: (tokens, context) => {
      this.parse_reference(tokens, context);
      return new YangStatement({ keyword: "reference", statements: [] });
    },
    [CONFIG]: (tokens, context) => {
      this.parse_config(tokens, context);
      return new YangStatement({ keyword: "config", statements: [] });
    }
  };
  constructor(options = {}) {
    this.importResolver = options.importResolver;
    this.includeResolver = options.includeResolver;
    this.runtimeDispatch = this.buildRuntimeDispatch();
  }
  /** Parse a ``submodule`` file into *context* (the including module). */
  parseSubmodule(tokens, context) {
    this.submodule_parser.parse_submodule(tokens, context);
  }
  pushIncludedStatement(context, stmt) {
    const mod = context.module;
    (mod.__included_statements ??= []).push(stmt);
  }
  drainIncludedStatements(context) {
    const mod = context.module;
    const pending = mod.__included_statements ?? [];
    mod.__included_statements = [];
    return pending;
  }
  resolveInclude(context, submoduleName, revisionDate, tokens) {
    if (!this.includeResolver) {
      throw new YangSemanticError("Include resolution is not configured for this parser instance");
    }
    this.includeResolver(submoduleName, revisionDate, context, tokens);
  }
  dispatch_key(tokens) {
    return tokens.peek_type() === YangTokenType.IDENTIFIER ? tokens.peek() ?? "" : tokens.peek_type();
  }
  assertStatementStartAllowed(tokens, allowed, restrictionContext) {
    const set = allowed instanceof Set ? allowed : new Set(allowed);
    const kw = this.dispatch_key(tokens);
    if (set.has(kw)) {
      return;
    }
    if (tokens.peek_type() === YangTokenType.IDENTIFIER && tokens.peek_type_at(1) === YangTokenType.COLON) {
      return;
    }
    const ctx = restrictionContext ? ` ${restrictionContext}` : "";
    const got = tokens.peek() ?? "<end>";
    const allowedLabels = [...set].map((t) => String(t)).sort().join(", ");
    throw new YangSyntaxError(
      `Invalid statement starting with '${got}'${ctx}. Allowed here: ${allowedLabels}; prefixed extension statements (identifier:keyword) are also allowed.`
    );
  }
  parseModule(tokens, context) {
    const root = this.parseStatement(tokens, context);
    if (root.keyword !== "module") {
      throw new YangSemanticError("Expected top-level 'module' statement");
    }
    return root;
  }
  /** Serialize an in-memory AST statement (e.g. under `grouping`) for module data / uses expansion. */
  serializeAstStatement(stmt) {
    return this.fromAst(stmt);
  }
  parseStatement(tokens, context, options) {
    if (options?.allowedStatementStarts) {
      this.assertStatementStartAllowed(tokens, options.allowedStatementStarts, options.restrictionContext);
    }
    const parent2 = context.dispatch_parent;
    if (parent2) {
      const key3 = this.dispatch_key(tokens);
      const allowed = DISPATCH_REGISTRY[parent2]?.keywords;
      if (typeof key3 === "string" && allowed?.has(key3)) {
        const allowedHandler = this.statementKeywordHandlers[key3];
        if (allowedHandler) {
          return allowedHandler(tokens, context);
        }
        return this.parse_statement_generic(tokens, context);
      }
      if (this.is_prefixed_extension_start(tokens)) {
        return this.parse_prefixed_extension_statement(tokens, context);
      }
      this.skip_unsupported_or_raise_unknown(tokens, context.dispatch_error ?? parent2);
    }
    if (this.is_prefixed_extension_start(tokens)) {
      return this.parse_prefixed_extension_statement(tokens, context);
    }
    const key2 = this.dispatch_key(tokens);
    const handler = this.statementKeywordHandlers[key2];
    if (handler) {
      return handler(tokens, context);
    }
    return this.parse_statement_generic(tokens, context);
  }
  parse_statement_generic(tokens, context) {
    const tokenType = this.dispatch_key(tokens);
    if (tokenType === MODULE) {
      return this.parse_top_level_module(tokens, context);
    }
    if (tokenType === SUBMODULE) {
      this.submodule_parser.parse_submodule(tokens, context);
      return new YangStatement({ keyword: "submodule", statements: [] });
    }
    if (tokenType === YANG_VERSION) {
      this.module_parser.parse_yang_version(tokens, context);
      return new YangStatement({
        keyword: "yang-version",
        argument: context.module.yang_version,
        name: "yang-version",
        statements: []
      });
    }
    if (tokenType === NAMESPACE) {
      this.module_parser.parse_namespace(tokens, context);
      return new YangStatement({
        keyword: "namespace",
        argument: context.module.namespace,
        name: "namespace",
        statements: []
      });
    }
    if (tokenType === PREFIX) {
      this.module_parser.parse_prefix(tokens, context);
      return new YangStatement({
        keyword: "prefix",
        argument: context.module.prefix,
        name: "prefix",
        statements: []
      });
    }
    if (tokenType === ORGANIZATION) {
      this.module_parser.parse_organization(tokens, context);
      return new YangStatement({ keyword: "organization", statements: [] });
    }
    if (tokenType === CONTACT) {
      this.module_parser.parse_contact(tokens, context);
      return new YangStatement({ keyword: "contact", statements: [] });
    }
    if (tokenType === IMPORT) {
      this.module_parser.parse_import_stmt(tokens, context);
      return new YangStatement({ keyword: "import", statements: [] });
    }
    if (tokenType === INCLUDE) {
      this.module_parser.parse_include_stmt(tokens, context);
      return new YangStatement({ keyword: "include", statements: [] });
    }
    if (this.skip_unsupported_if_present(tokens, "generic")) {
      return new YangStatement({ keyword: "unsupported", statements: [] });
    }
    const peek = tokens.peek();
    if (peek === INPUT || peek === OUTPUT) {
      tokens.syntaxError(
        `'${peek}' is only valid as a substatement of 'rpc' or 'action' (RFC 7950)`
      );
    }
    if (context.dispatch_parent) {
      this.skip_unsupported_or_raise_unknown(tokens, context.dispatch_error ?? context.dispatch_parent);
    }
    const first = tokens.consume();
    let keyword = first;
    if (tokens.peek_type() === YangTokenType.COLON) {
      tokens.consume_type(YangTokenType.COLON);
      keyword = `${keyword}:${tokens.consume_type(YangTokenType.IDENTIFIER)}`;
    }
    const argument = this.parse_argument(tokens);
    const statements = [];
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        statements.push(this.parseStatement(tokens, context));
      }
      tokens.consume_type(YangTokenType.RBRACE);
      tokens.consume_if_type(YangTokenType.SEMICOLON);
    } else {
      tokens.consume_if_type(YangTokenType.SEMICOLON);
    }
    const out = new YangStatement({ keyword, name: argument, argument, statements });
    if (keyword === "type") {
      out.type = normalizeTypeShape(this.extract_type_shape(out));
    }
    return out;
  }
  parse_argument(tokens) {
    if (!tokens.has_more()) {
      return "";
    }
    const t = tokens.peek_type();
    if (t === YangTokenType.SEMICOLON || t === YangTokenType.LBRACE || t === YangTokenType.RBRACE) {
      return "";
    }
    return this.parse_string_argument(tokens);
  }
  parse_string_concatenation(tokens) {
    if (!tokens.has_more() || tokens.peek_type() !== YangTokenType.STRING) {
      return this.parse_string_argument(tokens);
    }
    const parts = [tokens.consume_type(YangTokenType.STRING)];
    while (tokens.has_more() && tokens.peek_type() === YangTokenType.PLUS) {
      tokens.consume_type(YangTokenType.PLUS);
      if (!tokens.has_more() || tokens.peek_type() !== YangTokenType.STRING) {
        tokens.syntaxError("Expected quoted string after '+'");
      }
      parts.push(tokens.consume_type(YangTokenType.STRING));
    }
    return parts.join("");
  }
  parse_string_argument(tokens) {
    if (!tokens.has_more()) {
      tokens.syntaxError("Expected statement argument, got 'end'");
    }
    if (tokens.peek_type() === YangTokenType.STRING) {
      return this.parse_string_concatenation(tokens);
    }
    return this.read_unquoted_argument(tokens);
  }
  /** Exact lexical `true` or `false`, quoted or unquoted. */
  parse_boolean_argument(tokens, statement) {
    const tt = tokens.peek_type();
    if (!tokens.has_more() || tt === YangTokenType.SEMICOLON || tt === YangTokenType.LBRACE || tt === YangTokenType.RBRACE) {
      tokens.syntaxError(`${statement} argument must be 'true' or 'false', got ''`);
    }
    const raw = this.parse_string_argument(tokens);
    if (raw === TRUE) {
      return true;
    }
    if (raw === FALSE) {
      return false;
    }
    tokens.syntaxError(`${statement} argument must be 'true' or 'false', got '${raw}'`);
  }
  /** Adjacent lexemes up to whitespace, `;`, or `{` (RFC 7950 §6.1.3). */
  read_unquoted_argument(tokens) {
    const stop = /* @__PURE__ */ new Set([
      YangTokenType.SEMICOLON,
      YangTokenType.LBRACE,
      YangTokenType.RBRACE,
      YangTokenType.STRING
    ]);
    const parts = [];
    let prevLine;
    let prevEnd;
    while (tokens.has_more()) {
      const tok = tokens.peek_token();
      if (!tok || stop.has(tok.type)) {
        break;
      }
      if (prevEnd !== void 0 && (tok.line_num !== prevLine || tok.char_pos !== prevEnd)) {
        break;
      }
      parts.push(tok.value);
      prevLine = tok.line_num;
      prevEnd = tok.char_pos + tok.value.length;
      tokens.consume();
    }
    if (parts.length === 0) {
      const got = tokens.has_more() ? tokens.peek() : "end";
      tokens.syntaxError(`Expected statement argument, got '${got}'`);
    }
    return parts.join("");
  }
  /** One argument, then reject text that is not an identifier. */
  parse_identifier_argument(tokens, statement) {
    const raw = this.parse_string_argument(tokens);
    if (!isIdentifierText(raw)) {
      tokens.syntaxError(`${statement} argument must be an identifier, got '${raw}'`);
    }
    return raw;
  }
  /** One argument, then reject text outside the statement's keyword grammar. */
  parse_keyword_argument(tokens, statement, allowed) {
    const raw = this.parse_string_argument(tokens);
    if (!allowed.includes(raw)) {
      tokens.syntaxError(`${statement} argument must be ${allowed.map((item) => `'${item}'`).join(" or ")}, got '${raw}'`);
    }
    return raw;
  }
  /** One argument that is a signed decimal integer. */
  parse_integer_argument(tokens, statement) {
    const raw = this.parse_string_argument(tokens);
    if (!/^[+-]?\d+$/.test(raw)) {
      tokens.syntaxError(`${statement} argument must be an integer, got '${raw}'`);
    }
    return Number.parseInt(raw, 10);
  }
  /** ``status current|deprecated|obsolete``, quoted or unquoted. */
  parse_status_argument(tokens) {
    tokens.consume(STATUS);
    const value = this.parse_keyword_argument(tokens, "status", ["current", "deprecated", "obsolete"]);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return value;
  }
  /** `min-elements` / `max-elements`: an integer, or `unbounded` (no bound). */
  parse_integer_or_unbounded(tokens, statement) {
    const raw = this.parse_string_argument(tokens);
    if (raw === "unbounded") {
      return void 0;
    }
    if (!/^[+-]?\d+$/.test(raw)) {
      tokens.syntaxError(`${statement} argument must be an integer or 'unbounded', got '${raw}'`);
    }
    return Number.parseInt(raw, 10);
  }
  substatement_handler(tokens, dispatch) {
    const key2 = this.dispatch_key(tokens);
    if (typeof key2 === "string") {
      return dispatch[key2];
    }
    return void 0;
  }
  is_prefixed_extension_start(tokens) {
    return tokens.peek_type_at(0) === YangTokenType.IDENTIFIER && tokens.peek_type_at(1) === YangTokenType.COLON && tokens.peek_type_at(2) === YangTokenType.IDENTIFIER;
  }
  handlerFor(parent2, keyword) {
    return this.runtimeDispatch[parent2]?.[keyword];
  }
  dispatchSubstatement(tokens, context, parent2, errorContext, ...handlerArgs) {
    const key2 = this.dispatch_key(tokens);
    const handler = typeof key2 === "string" ? this.runtimeDispatch[parent2]?.[key2] : void 0;
    if (handler) {
      handler(tokens, context, ...handlerArgs);
      return;
    }
    if (this.is_prefixed_extension_start(tokens)) {
      this.parse_prefixed_extension_statement(tokens, context);
      return;
    }
    this.skip_unsupported_or_raise_unknown(tokens, errorContext);
  }
  parseBody(tokens, context, parent2, errorContext, ...handlerArgs) {
    while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
      this.dispatchSubstatement(tokens, context, parent2, errorContext, ...handlerArgs);
    }
  }
  parseDiscardedDescription(tokens, context) {
    this.parse_optional_description(tokens, context.push_parent({}));
  }
  buildRuntimeDispatch() {
    const drop = (fn) => (tokens, context) => {
      fn(tokens, context);
    };
    const mod = this.module_parser;
    const typ = this.type_parser;
    const bits = this.bits_parser;
    const choice = this.choice_parser;
    const defaults = {
      [LEAF]: (t, c) => {
        this.leaf_parser.parse_leaf(t, c);
      },
      [LIST]: (t, c) => {
        this.list_parser.parse_list(t, c);
      },
      [LEAF_LIST]: (t, c) => {
        this.leaf_list_parser.parse_leaf_list(t, c);
      },
      [CONTAINER]: (t, c) => {
        this.container_parser.parse_container(t, c);
      },
      [NOTIFICATION]: (t, c) => {
        this.notification_parser.parse_notification(t, c);
      },
      [RPC]: (t, c) => {
        this.rpc_parser.parse_rpc(t, c);
      },
      [ACTION]: (t, c) => {
        this.rpc_parser.parse_action(t, c);
      },
      [ANYDATA]: (t, c) => {
        this.anydata_parser.parse_anydata(t, c);
      },
      [ANYXML]: (t, c) => {
        this.anyxml_parser.parse_anyxml(t, c);
      },
      [TYPEDEF]: (t, c) => {
        this.typedef_parser.parse_typedef(t, c);
      },
      [GROUPING]: (t, c) => {
        this.grouping_parser.parse_grouping(t, c);
      },
      [IMPORT]: (t, c) => {
        mod.parse_import_stmt(t, c);
      },
      [INCLUDE]: (t, c) => {
        mod.parse_include_stmt(t, c);
      },
      [REVISION]: (t, c) => {
        this.revision_parser.parse_revision(t, c);
      },
      [DESCRIPTION]: (t, c) => {
        this.parse_description(t, c);
      },
      [REFERENCE]: (t, c) => {
        this.parse_reference(t, c);
      },
      [FEATURE]: (t, c) => {
        this.feature_parser.parse_feature_stmt(t, c);
      },
      [IDENTITY]: (t, c) => {
        this.identity_parser.parse_identity(t, c);
      },
      [EXTENSION]: (t, c) => {
        this.extension_parser.parse_extension_stmt(t, c);
      },
      [AUGMENT]: (t, c) => {
        this.augment_parser.parse_augment(t, c);
      },
      [DEVIATION]: (t, c) => {
        this.deviation_parser.parse_deviation(t, c);
      },
      [YANG_VERSION]: (t, c) => {
        mod.parse_yang_version(t, c);
      },
      [NAMESPACE]: (t, c) => {
        mod.parse_namespace(t, c);
      },
      [PREFIX]: (t, c) => {
        mod.parse_prefix(t, c);
      },
      [ORGANIZATION]: (t, c) => {
        mod.parse_organization(t, c);
      },
      [CONTACT]: (t, c) => {
        mod.parse_contact(t, c);
      },
      [TYPE]: (t, c) => {
        this.type_parser.parse_type(t, c);
      },
      [UNITS]: (t, c) => {
        this.parse_units(t, c);
      },
      [DEFAULT]: (t, c) => {
        this.parse_leaf_default(t, c);
      },
      [STATUS]: (t, c) => {
        this.parse_status_ignored(t, c);
      },
      [CONFIG]: (t, c) => {
        this.parse_config(t, c);
      },
      [WHEN]: (t, c) => {
        this.when_parser.parse_when(t, c);
      },
      [MUST]: (t, c) => {
        this.must_parser.parse_must(t, c);
      },
      [IF_FEATURE]: (t, c) => {
        this.feature_parser.parse_if_feature_stmt(t, c);
      },
      [PRESENCE]: (t, c) => {
        this.parse_presence(t, c);
      },
      [USES]: (t, c) => {
        this.uses_parser.parse_uses(t, c);
      },
      [REFINE]: (t, c) => {
        this.refine_parser.parse_refine(t, c);
      },
      [CHOICE]: (t, c) => {
        this.choice_parser.parse_choice(t, c);
      },
      [CASE]: (t, c) => {
        this.choice_parser.parse_case(t, c);
      },
      [KEY]: (t, c) => {
        this.parse_list_key(t, c);
      },
      [UNIQUE]: (t, c) => {
        this.parse_list_unique(t, c);
      },
      [MIN_ELEMENTS]: (t, c) => {
        this.parse_min_elements(t, c);
      },
      [MAX_ELEMENTS]: (t, c) => {
        this.parse_max_elements(t, c);
      },
      [ORDERED_BY]: (t) => {
        this.parse_ordered_by(t);
      },
      [MANDATORY]: (t, c) => {
        this.parse_leaf_mandatory(t, c);
      },
      [INPUT]: (t, c) => {
        this.rpc_parser.parse_input(t, c);
      },
      [OUTPUT]: (t, c) => {
        this.rpc_parser.parse_output(t, c);
      }
    };
    const importPrefix = (tokens) => {
      tokens.consume(PREFIX);
      const acc = this.importAcc;
      if (!acc) {
        tokens.syntaxError("internal: import prefix outside import block");
        return;
      }
      acc.localPrefix = this.parse_identifier_argument(tokens, "prefix");
      tokens.consume_if_type(YangTokenType.SEMICOLON);
    };
    const importRevision = (tokens) => {
      const acc = this.importAcc;
      if (!acc) {
        tokens.syntaxError("internal: revision-date outside import block");
        return;
      }
      acc.revisionDate = this.revision_parser.parse_revision_date_statement(tokens);
    };
    const overrides = {
      import: {
        [PREFIX]: importPrefix,
        [DESCRIPTION]: (t, c) => {
          this.parseDiscardedDescription(t, c);
        },
        [REVISION_DATE]: importRevision
      },
      include: {
        [PREFIX]: (t) => {
          mod.parse_prefix_value_stmt(t);
        },
        [DESCRIPTION]: (t, c) => {
          this.parseDiscardedDescription(t, c);
        },
        [REVISION_DATE]: (t) => {
          this.includeRevisionDate = this.revision_parser.parse_revision_date_statement(t);
        }
      },
      "belongs-to": {
        [PREFIX]: (t, c) => {
          t.consume(PREFIX);
          c.module.prefix = this.parse_identifier_argument(t, "prefix");
          t.consume_if_type(YangTokenType.SEMICOLON);
        }
      },
      typedef: {
        [DEFAULT]: (t, c) => {
          this.parse_typedef_default(t, c);
        }
      },
      choice: {
        [MANDATORY]: (t, c) => {
          choice.parse_choice_mandatory(t, c);
        },
        [DEFAULT]: (t, c) => {
          choice.parse_choice_default(t, c);
        }
      },
      refine: {
        [MANDATORY]: (t, c) => {
          this.parse_leaf_mandatory(t, c);
        },
        [DEFAULT]: (t, c) => {
          this.parse_leaf_default(t, c);
        }
      },
      identity: {
        [BASE]: (t, c) => {
          this.identity_parser.parse_identity_base(t, c);
        }
      },
      "if-feature": {
        [DESCRIPTION]: (t, c) => {
          this.parseDiscardedDescription(t, c);
        }
      },
      must: {
        [ERROR_MESSAGE]: (t, c) => {
          this.must_parser.parse_must_error_message(t, c);
        },
        [ERROR_APP_TAG]: (t, c) => {
          this.must_parser.parse_must_error_app_tag(t, c);
        }
      },
      extension: {
        [ARGUMENT]: (t, c) => {
          this.extension_parser.parse_extension_argument_stmt(t, c);
        }
      },
      argument: {
        [YIN_ELEMENT]: (t, c) => {
          this.extension_parser.parse_yin_element(t, c);
        }
      },
      deviation: {
        [DEVIATE]: (t, c) => {
          this.deviation_parser.parse_deviate_substatement(t, c);
        }
      },
      pattern: {
        [ERROR_MESSAGE]: (t, c) => {
          typ.parse_pattern_error_message(t, c);
        },
        [ERROR_APP_TAG]: (t, c) => {
          typ.parse_pattern_error_app_tag(t, c);
        },
        [MODIFIER]: (t, c) => {
          typ.parse_pattern_modifier(t, c);
        }
      },
      enum: {
        [VALUE]: (t, c) => {
          typ.parse_enum_value(t, c);
        },
        [STATUS]: (t, c) => {
          typ.parse_enum_status(t, c);
        }
      },
      bit: {
        [POSITION]: (t, c) => {
          bits.parse_bit_position(t, c);
        }
      },
      length: {
        [ERROR_MESSAGE]: (t, c) => {
          typ.parse_restriction_error_message(t, c);
        },
        [ERROR_APP_TAG]: (t, c) => {
          typ.parse_restriction_error_app_tag(t, c);
        }
      },
      range: {
        [ERROR_MESSAGE]: (t, c) => {
          typ.parse_restriction_error_message(t, c);
        },
        [ERROR_APP_TAG]: (t, c) => {
          typ.parse_restriction_error_app_tag(t, c);
        }
      },
      type: {
        [TYPE]: (t, c, typeStmt) => {
          const nested = typ.parse_type(t, c);
          if (!(typeStmt instanceof YangUnionTypeStmt)) throw new YangSemanticError("nested type requires union");
          typeStmt.types.push(nested);
        },
        [PATTERN]: (t, c, typeStmt) => {
          typ.parse_type_pattern(t, c, typeStmt);
        },
        [LENGTH]: (t, c, typeStmt) => {
          typ.parse_type_length(t, c, typeStmt);
        },
        [RANGE]: (t, c, typeStmt) => {
          typ.parse_type_range(t, c, typeStmt);
        },
        [FRACTION_DIGITS]: (t, c, typeStmt) => {
          typ.parse_type_fraction_digits(t, c, typeStmt);
        },
        [ENUM]: (t, c, typeStmt) => {
          typ.parse_type_enum(t, c, typeStmt);
        },
        [BIT]: (t, c, typeStmt) => {
          bits.parse_type_bit(t, c, typeStmt);
        },
        [PATH]: (t, c, typeStmt) => {
          typ.parse_type_path(t, c, typeStmt);
        },
        [REQUIRE_INSTANCE]: (t, c, typeStmt) => {
          typ.parse_type_require_instance(t, c, typeStmt);
        },
        [BASE]: (t, c, typeStmt) => {
          typ.parse_type_base(t, c, typeStmt);
        },
        [UNITS]: drop((t, c) => {
          this.parse_units(t, c);
        }),
        [DESCRIPTION]: drop((t, c) => {
          this.parse_description(t, c);
        }),
        [REFERENCE]: drop((t, c) => {
          this.parse_reference(t, c);
        })
      }
    };
    const runtime = {};
    for (const [parent2, spec] of Object.entries(DISPATCH_REGISTRY)) {
      const over = overrides[parent2] ?? {};
      const table2 = {};
      const missing = [];
      for (const keyword of spec.keywords) {
        const handler = over[keyword] ?? defaults[keyword];
        if (!handler) {
          missing.push(keyword);
        } else {
          table2[keyword] = handler;
        }
      }
      const extra = Object.keys(over).filter((keyword) => !spec.keywords.has(keyword));
      if (extra.length > 0) {
        throw new Error(`handler override for keywords not allowed under ${parent2}: ${extra.sort().join(", ")}`);
      }
      if (missing.length > 0) {
        throw new Error(`no handler for ${parent2}: ${missing.sort().join(", ")}`);
      }
      runtime[parent2] = table2;
    }
    return runtime;
  }
  skip_unsupported_or_raise_unknown(tokens, context) {
    const peek = tokens.peek();
    if (peek === INPUT || peek === OUTPUT) {
      tokens.syntaxError(
        `'${peek}' is only valid as a substatement of 'rpc' or 'action' (RFC 7950)`
      );
    }
    if (this.skip_unsupported_if_present(tokens, context)) {
      return true;
    }
    const bad = tokens.peek() ?? "";
    tokens.syntaxError(`Invalid or unknown statement in ${context}: '${bad}'`);
  }
  parse_prefixed_extension_statement_public(tokens, context) {
    this.parse_prefixed_extension_statement(tokens, context);
  }
  /**
   * ``name`` or ``prefix:name``, quoted or unquoted (RFC 7950 identifier-ref-arg-str).
   * The argument is read by {@link parse_string_argument}, then checked.
   */
  consume_identifier_ref(tokens) {
    const raw = this.parse_string_argument(tokens);
    const colon = raw.indexOf(":");
    if (colon < 0) {
      if (!isIdentifierText(raw)) {
        tokens.syntaxError(`Expected an identifier, got '${raw}'`);
      }
      return { name: raw };
    }
    const prefix = raw.slice(0, colon);
    const name = raw.slice(colon + 1);
    if (prefix && name && !name.includes(":") && isIdentifierText(prefix) && isIdentifierText(name)) {
      return { prefix, name };
    }
    tokens.syntaxError(`Expected an identifier or prefix:identifier, got '${raw}'`);
  }
  /** Joined ``prefix:name`` form; prefer {@link consume_identifier_ref} for new code. */
  consume_qname_from_identifier(tokens) {
    const ref = this.consume_identifier_ref(tokens);
    return ref.prefix ? `${ref.prefix}:${ref.name}` : ref.name;
  }
  add_to_parent_or_module(context, stmt) {
    const file = this.includingSubmoduleName;
    if (file && stmt && typeof stmt === "object" && !("included_from" in stmt && stmt.included_from)) {
      stmt.included_from = file;
    }
    const parent2 = context.current_parent;
    if (parent2 && Array.isArray(parent2.statements)) {
      parent2.statements.push(stmt);
      return;
    }
    const module = context.module;
    if (Array.isArray(module.statements)) {
      module.statements.push(stmt);
    }
  }
  skip_unsupported_if_present(tokens, context) {
    if (!is_unsupported_construct_start(tokens)) {
      return false;
    }
    skip_unsupported_construct(tokens, { context });
    return true;
  }
  parse_top_level_module(tokens, context) {
    tokens.consume(MODULE);
    const moduleName2 = this.parse_identifier_argument(tokens, "module");
    context.module.name = moduleName2;
    tokens.consume_type(YangTokenType.LBRACE);
    const moduleStatements = [];
    const scoped = context.with_dispatch("module", "module body");
    while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
      const stmt = this.parseStatement(tokens, scoped);
      if (stmt.keyword !== "include") {
        moduleStatements.push(stmt);
      }
      const included = this.drainIncludedStatements(context);
      if (included.length > 0) {
        moduleStatements.push(...included);
      }
    }
    tokens.consume_type(YangTokenType.RBRACE);
    return new YangStatement({
      keyword: "module",
      name: moduleName2,
      argument: moduleName2,
      statements: moduleStatements
    });
  }
  fromAst(stmt) {
    const keyword = serializedKeywordFromAstStatement(stmt);
    const children2 = [
      ...this.serializeAstChildren(stmt.statements ?? []),
      ...this.serializeAstChildren(stmt.cases ?? [])
    ];
    const out = new YangStatement({
      keyword,
      name: stmt.name,
      argument: stmt.name,
      statements: children2
    });
    const includedFrom = stmt.included_from;
    if (includedFrom) out.included_from = includedFrom;
    if (keyword === "typedef" && stmt.scope) {
      out.scope = stmt.scope;
    }
    if (stmt.type) {
      out.type = normalizeTypeShape(this.fromTypeShape(stmt.type));
    }
    if (stmt.mandatory !== void 0) {
      out.mandatory = stmt.mandatory;
    }
    if (stmt.default !== void 0) {
      out.default = stmt.default;
    }
    const config = stmt.config;
    if (typeof config === "boolean") {
      out.config = config;
    }
    if (keyword === "leaf-list") {
      const llDefaults = stmt.defaults;
      if (Array.isArray(llDefaults) && llDefaults.length > 0) {
        out.defaults = [...llDefaults];
      }
    }
    if (stmt.key !== void 0) {
      out.key = stmt.key;
    }
    const unique = stmt.unique;
    if (Array.isArray(unique) && unique.length > 0) {
      out.unique = unique.map((paths) => [...paths]);
    }
    const minElements = stmt.min_elements;
    if (typeof minElements === "number") {
      out.min_elements = minElements;
    }
    const maxElements = stmt.max_elements;
    if (typeof maxElements === "number") {
      out.max_elements = maxElements;
    }
    if (stmt.description) {
      out.description = stmt.description;
    }
    const units = stmt.units;
    if (units) {
      out.units = units;
    }
    if (keyword === "container") {
      const groupings = stmt.groupings;
      if (groupings && Object.keys(groupings).length > 0) {
        const local2 = {};
        for (const [gname, grouping] of Object.entries(groupings)) {
          local2[gname] = this.fromAst(grouping);
        }
        out.local_groupings = local2;
      }
    }
    const reference = stmt.reference;
    if (reference) {
      out.reference = reference;
    }
    if (Array.isArray(stmt.if_features) && stmt.if_features.length > 0) {
      out.if_features = [...stmt.if_features];
    }
    if (keyword === "extension") {
      if (typeof stmt.argument_name === "string") {
        out.argument_name = stmt.argument_name;
      }
      if (typeof stmt.argument_yin_element === "boolean") {
        out.argument_yin_element = stmt.argument_yin_element;
      }
    }
    if (keyword === "augment" && typeof stmt.augment_path === "string") {
      out.argument = stmt.augment_path;
      out.augment_path = stmt.augment_path;
      const segs = stmt.augment_path_segments;
      if (Array.isArray(segs) && segs.length > 0) {
        out.augment_path_segments = segs.map(
          (s) => s.prefix ? { prefix: s.prefix, name: s.name } : { name: s.name }
        );
      }
    }
    if (keyword === "extension-invocation") {
      out.keyword = stmt.name ?? "extension-invocation";
      out.argument = stmt.argument;
      out.prefix = stmt.prefix;
      out.resolved_module_name = stmt.resolved_module?.name;
      out.resolved_extension_name = stmt.resolved_extension?.name;
      if (stmt.resolved_extension?.apply_callback) {
        out.has_apply_callback = true;
      }
    }
    if (stmt.when && typeof stmt.when.expression === "string") {
      out.when = {
        expression: stmt.when.expression,
        description: stmt.when.description ?? "",
        evaluate_with_parent_context: stmt.when.evaluate_with_parent_context ?? false,
        ...stmt.when.xpath_prefixes ? { xpath_prefixes: stmt.when.xpath_prefixes } : {}
      };
    }
    if (Array.isArray(stmt.must_statements) && stmt.must_statements.length > 0) {
      out.statements = [
        ...out.statements ?? [],
        ...stmt.must_statements.map((mustStmt) => this.fromMust(mustStmt))
      ];
    }
    if (keyword === "uses") {
      const u = stmt;
      if (typeof u.grouping_name === "string" && u.grouping_name.length > 0) {
        out.grouping_name = u.grouping_name;
        if (typeof u.grouping_prefix === "string" && u.grouping_prefix.length > 0) {
          out.grouping_prefix = u.grouping_prefix;
        }
        out.argument = u.grouping_qname();
      }
      if (Array.isArray(u.refines) && u.refines.length > 0) {
        out.refines = u.refines.map((r) => this.serializeRefineStmt(r));
      }
      if (Array.isArray(u.augmentations) && u.augmentations.length > 0) {
        out.augmentations = u.augmentations.map((aug) => {
          const serialized = this.fromAst(aug);
          serialized.path = aug.augment_path;
          return serialized;
        });
      }
    }
    const presence = stmt.presence;
    if (typeof presence === "string" && presence.length > 0) {
      out.presence = presence;
    }
    return out;
  }
  serializeRefineStmt(r) {
    const out = new YangStatement({
      keyword: "refine",
      name: "refine",
      argument: r.target_path,
      refine_target_path: r.target_path,
      statements: []
    });
    if (typeof r.min_elements === "number") {
      out.min_elements = r.min_elements;
    }
    if (typeof r.max_elements === "number") {
      out.max_elements = r.max_elements;
    }
    if (typeof r.refined_mandatory === "boolean") {
      out.refined_mandatory = r.refined_mandatory;
    }
    if (Array.isArray(r.refined_defaults) && r.refined_defaults.length > 0) {
      out.refined_defaults = [...r.refined_defaults];
    }
    if (typeof r.refined_config === "boolean") {
      out.refined_config = r.refined_config;
    }
    if (Array.isArray(r.if_features) && r.if_features.length > 0) {
      out.if_features = [...r.if_features];
    }
    if (typeof r.description === "string" && r.description.length > 0) {
      out.description = r.description;
    }
    if (Array.isArray(r.must_statements) && r.must_statements.length > 0) {
      out.statements = r.must_statements.map((m) => this.fromMust(m));
    }
    return out;
  }
  serializeAstChildren(children2) {
    const out = [];
    for (const child2 of children2) {
      if (!child2 || typeof child2 !== "object") {
        continue;
      }
      out.push(this.fromAst(child2));
    }
    return out;
  }
  /** Generic ``must`` statement for a parsed ``must`` (a ``deviate`` keeps these). */
  mustStatement(must_stmt) {
    return this.fromMust(must_stmt);
  }
  /** Type shape for a parsed ``type`` (a ``deviate replace`` keeps this). */
  typeShape(type_stmt) {
    return normalizeTypeShape(this.fromTypeShape(type_stmt));
  }
  fromType(type_stmt) {
    const qname = formatIdentifierRef({ name: type_stmt.name, prefix: type_stmt.prefix });
    return new YangStatement({
      keyword: "type",
      name: type_stmt.name,
      argument: qname,
      type: this.fromTypeShape(type_stmt),
      statements: []
    });
  }
  fromMust(must_stmt) {
    return new YangStatement({
      keyword: "must",
      name: must_stmt.expression,
      argument: must_stmt.expression,
      error_message: must_stmt.error_message,
      ...must_stmt.error_app_tag ? { error_app_tag: must_stmt.error_app_tag } : {},
      description: must_stmt.description,
      xpath_prefixes: must_stmt.xpath_prefixes,
      statements: []
    });
  }
  fromTypeShape(type_stmt) {
    const shape = { name: type_stmt.name };
    if (type_stmt.prefix !== void 0) shape.prefix = type_stmt.prefix;
    if (type_stmt.scope_module !== void 0) shape.scope_module = type_stmt.scope_module;
    const sourceFile = type_stmt.source_file;
    if (sourceFile) shape.source_file = sourceFile;
    if (type_stmt.context !== void 0) shape.context = type_stmt.context;
    if (type_stmt instanceof YangStringTypeStmt || type_stmt instanceof YangDerivedTypeStmt) {
      if (type_stmt.patterns?.length) shape.patterns = type_stmt.patterns.map((p) => ({
        pattern: p.pattern,
        invert_match: p.invert_match,
        ...p.error_message !== void 0 ? { error_message: p.error_message } : {},
        ...p.error_app_tag !== void 0 ? { error_app_tag: p.error_app_tag } : {}
      }));
    }
    for (const kind of ["range", "length"]) {
      const restriction = kind === "range" ? type_stmt instanceof YangNumericTypeStmt || type_stmt instanceof YangDerivedTypeStmt ? type_stmt.range_restriction : void 0 : type_stmt instanceof YangBinaryTypeStmt || type_stmt instanceof YangDerivedTypeStmt ? type_stmt.length_restriction : void 0;
      if (restriction) {
        shape[kind] = restriction.expression;
        for (const key2 of ["error_message", "error_app_tag", "description", "reference"]) {
          if (restriction[key2] !== void 0) shape[`${kind}_${key2}`] = restriction[key2];
        }
      }
    }
    if (type_stmt instanceof YangDecimalTypeStmt && type_stmt.fraction_digits !== void 0) shape.fraction_digits = type_stmt.fraction_digits;
    if (type_stmt instanceof YangEnumerationTypeStmt || type_stmt instanceof YangDerivedTypeStmt) {
      if (type_stmt.enums) shape.enums = [...type_stmt.enums];
      const guards = type_stmt.enum_if_features;
      if (guards && Object.keys(guards).length > 0) {
        shape.enum_if_features = Object.fromEntries(Object.entries(guards).map(([name, feats]) => [name, [...feats]]));
      }
    }
    if (type_stmt instanceof YangBitsTypeStmt || type_stmt instanceof YangDerivedTypeStmt) {
      if (type_stmt.bits) shape.bits = type_stmt.bits.map((b) => ({
        name: b.name,
        position: b.position ?? 0,
        ...b.if_features.length > 0 ? { if_features: [...b.if_features] } : {}
      }));
    }
    if (type_stmt instanceof YangUnionTypeStmt) shape.types = type_stmt.types.map((member) => this.fromTypeShape(member));
    if (type_stmt instanceof YangIdentityrefTypeStmt) shape.identityref_bases = type_stmt.identityref_bases.map((base) => ({ ...base }));
    if (type_stmt instanceof YangInstanceIdentifierTypeStmt || type_stmt instanceof YangDerivedTypeStmt) {
      if (type_stmt.require_instance !== void 0) shape.require_instance = type_stmt.require_instance;
    }
    if (type_stmt instanceof YangLeafrefTypeStmt) {
      if (type_stmt.path !== void 0) shape.path = type_stmt.path;
      if (type_stmt.xpath_prefixes) shape.xpath_prefixes = type_stmt.xpath_prefixes;
    }
    return shape;
  }
  extract_type_shape(typeStmt) {
    const name = typeStmt.argument ?? "string";
    const shape = { name };
    for (const child2 of typeStmt.statements ?? []) {
      if (child2.keyword === "pattern" && child2.argument) {
        const patterns = shape.patterns ?? [];
        patterns.push({ pattern: child2.argument, invert_match: false });
        shape.patterns = patterns;
      }
      if (child2.keyword === "length" && child2.argument) shape.length = child2.argument;
      if (child2.keyword === "range" && child2.argument) shape.range = child2.argument;
      if (child2.keyword === "fraction-digits" && child2.argument) {
        const n = Number.parseInt(child2.argument, 10);
        if (!Number.isNaN(n)) shape.fraction_digits = n;
      }
      if (child2.keyword === "enum" && child2.argument) {
        shape.enums = [...shape.enums ?? [], child2.argument];
        const feats = (child2.statements ?? []).filter((stmt) => stmt.keyword === "if-feature" && typeof stmt.argument === "string" && stmt.argument.length > 0).map((stmt) => stmt.argument);
        if (feats.length > 0) {
          shape.enum_if_features = { ...shape.enum_if_features ?? {}, [child2.argument]: feats };
        }
      }
      if (child2.keyword === "bit" && child2.argument) {
        const bits = shape.bits ?? [];
        const feats = (child2.statements ?? []).filter((stmt) => stmt.keyword === "if-feature" && typeof stmt.argument === "string" && stmt.argument.length > 0).map((stmt) => stmt.argument);
        bits.push({
          name: child2.argument,
          position: bits.length === 0 ? 0 : Math.max(...bits.map((b) => b.position)) + 1,
          ...feats.length > 0 ? { if_features: feats } : {}
        });
        shape.bits = bits;
      }
      if (name === "union" && child2.keyword === "type") {
        shape.types = [...shape.types ?? [], this.extract_type_shape(child2)];
      }
    }
    return shape;
  }
  parse_description(tokens, context) {
    tokens.consume(DESCRIPTION);
    const desc = this.parse_string_argument(tokens);
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        tokens.consume();
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    const parent2 = context.current_parent;
    if (parent2 && "description" in parent2) {
      parent2.description = desc;
    }
    return desc;
  }
  parse_optional_description(tokens, context) {
    if (tokens.has_more() && tokens.peek() === DESCRIPTION) {
      this.parse_description(tokens, context);
    }
  }
  parse_units(tokens, context) {
    tokens.consume(UNITS);
    const units = this.parse_string_argument(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    const parent2 = context.current_parent;
    if (parent2 && "units" in parent2) {
      parent2.units = units;
    }
  }
  parse_reference(tokens, context) {
    tokens.consume(REFERENCE);
    const ref = this.parse_string_argument(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    const parent2 = context.current_parent;
    if (parent2 && typeof parent2 === "object" && "reference" in parent2) {
      parent2.reference = ref;
    }
  }
  parse_reference_string_only(tokens, context) {
    this.parse_reference(tokens, context);
  }
  parse_status_ignored(tokens, _context) {
    this.parse_status_argument(tokens);
  }
  parse_config(tokens, context) {
    tokens.consume(CONFIG);
    const value = this.parse_boolean_argument(tokens, "config");
    const parent2 = context.current_parent;
    if (parent2 instanceof YangRefineStmt) {
      parent2.refined_config = value;
    } else if (parent2 && typeof parent2 === "object" && "config" in parent2) {
      parent2.config = value;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_typedef_default(tokens, context) {
    tokens.consume(DEFAULT);
    const parent2 = context.current_parent;
    if (parent2 instanceof YangTypedefStmt) {
      parent2.default = this.parse_default_value_tokens(tokens);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  register_import(context, moduleName2, localPrefix, revisionDate, tokens) {
    const module = context.module;
    const ownPrefix2 = String(module.prefix ?? "").replace(/^['"]|['"]$/g, "");
    if (localPrefix === ownPrefix2) {
      throw new YangSemanticError(`Import prefix '${localPrefix}' must differ from this module's prefix`);
    }
    const includedFrom = this.includingSubmoduleName;
    let imports;
    if (includedFrom) {
      const maps = module.file_imports ?? {};
      module.file_imports = maps;
      imports = maps[includedFrom] ?? {};
      maps[includedFrom] = imports;
    } else {
      imports = module.import_prefixes ?? {};
      module.import_prefixes = imports;
    }
    if (imports[localPrefix]) {
      throw new YangSemanticError(`Duplicate import prefix '${localPrefix}'`);
    }
    if (!this.importResolver) {
      throw new YangSemanticError("Import resolution is not configured for this parser instance");
    }
    imports[localPrefix] = this.importResolver(moduleName2, localPrefix, revisionDate, context, tokens);
  }
  parse_ordered_by(tokens) {
    tokens.consume(ORDERED_BY);
    this.parse_keyword_argument(tokens, "ordered-by", ["user", "system"]);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_list_key(tokens, context) {
    tokens.consume(KEY);
    const value = this.parse_string_argument(tokens);
    const parent2 = context.current_parent;
    if (parent2 && "key" in parent2) parent2.key = value;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  /** `unique "<descendant-path> ..."` (RFC 7950 §7.8.3). */
  parse_list_unique(tokens, context) {
    tokens.consume(UNIQUE);
    const arg = this.parse_string_argument(tokens);
    const paths = arg.split(/\s+/).filter(Boolean).map(
      (path) => path.split("/").filter(Boolean).map((seg) => seg.slice(seg.indexOf(":") + 1)).join("/")
    );
    if (paths.length === 0) {
      tokens.syntaxError("unique requires at least one descendant path");
    }
    const parent2 = context.current_parent;
    if (parent2 instanceof YangListStmt) {
      parent2.unique.push(paths);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_min_elements(tokens, context) {
    tokens.consume(MIN_ELEMENTS);
    const value = this.parse_integer_or_unbounded(tokens, "min-elements");
    const parent2 = context.current_parent;
    if (parent2 && "min_elements" in parent2) parent2.min_elements = value;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_max_elements(tokens, context) {
    tokens.consume(MAX_ELEMENTS);
    const value = this.parse_integer_or_unbounded(tokens, "max-elements");
    const parent2 = context.current_parent;
    if (parent2 && "max_elements" in parent2) parent2.max_elements = value;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_leaf_mandatory(tokens, context) {
    tokens.consume(MANDATORY);
    const value = this.parse_boolean_argument(tokens, "mandatory");
    const parent2 = context.current_parent;
    if (parent2 instanceof YangRefineStmt) {
      parent2.refined_mandatory = value;
      tokens.consume_if_type(YangTokenType.SEMICOLON);
      return;
    }
    if (parent2 && typeof parent2 === "object" && "mandatory" in parent2) {
      parent2.mandatory = value;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_leaf_default(tokens, context) {
    tokens.consume(DEFAULT);
    const value = this.parse_default_value_tokens(tokens);
    const parent2 = context.current_parent;
    if (parent2 instanceof YangRefineStmt) {
      parent2.refined_defaults.push(value);
    } else if (parent2 instanceof YangLeafListStmt) {
      parent2.defaults.push(value);
    } else if (parent2 && typeof parent2 === "object" && "default" in parent2) {
      parent2.default = value;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_presence(tokens, context) {
    tokens.consume(PRESENCE);
    const parent2 = context.current_parent;
    const value = this.parse_string_argument(tokens);
    if (parent2 && "presence" in parent2) parent2.presence = value;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
  parse_default_value_tokens(tokens) {
    return this.parse_string_argument(tokens);
  }
  parse_prefixed_extension_statement(tokens, context) {
    const prefix = tokens.consume_type(YangTokenType.IDENTIFIER);
    tokens.consume_type(YangTokenType.COLON);
    const extensionName = tokens.consume_type(YangTokenType.IDENTIFIER);
    const resolvedModule = this.resolve_prefixed_module(context, prefix);
    if (!resolvedModule) {
      throw new YangSemanticError(`Unknown extension prefix '${prefix}' in invocation ${prefix}:${extensionName}`);
    }
    const resolvedExtension = this.resolve_extension_definition(resolvedModule, extensionName);
    if (!resolvedExtension) {
      throw new YangSemanticError(
        `Unknown extension '${extensionName}' in module '${resolvedModule.name ?? ""}' for invocation ${prefix}:${extensionName}`
      );
    }
    const argument = this.consume_optional_extension_argument(tokens);
    const invocation = new YangExtensionInvocationStmt({
      name: `${prefix}:${extensionName}`,
      prefix,
      resolved_module: resolvedModule,
      resolved_extension: resolvedExtension,
      argument
    });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const childContext = context.push_parent(invocation);
      this.parseBody(
        tokens,
        childContext,
        "extension-invocation",
        `extension invocation '${invocation.name}'`
      );
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    this.add_to_parent_or_module(context, invocation);
    return this.fromAst(invocation);
  }
  consume_optional_extension_argument(tokens) {
    if (!tokens.has_more()) {
      return void 0;
    }
    const tt = tokens.peek_type();
    if (tt === YangTokenType.LBRACE || tt === YangTokenType.SEMICOLON || tt === YangTokenType.RBRACE) {
      return void 0;
    }
    return this.parse_string_argument(tokens);
  }
  resolve_prefixed_module(context, prefix) {
    return resolvePrefixedModule(context.module, prefix, this.includingSubmoduleName);
  }
  resolve_extension_definition(resolvedModule, extensionName) {
    const direct = resolvedModule.extensions?.[extensionName];
    if (direct) {
      return direct;
    }
    const statements = Array.isArray(resolvedModule.statements) ? resolvedModule.statements : [];
    const extStmt = statements.find((stmt) => stmt.keyword === "extension" && stmt.name === extensionName);
    if (!extStmt) {
      return void 0;
    }
    return new YangExtensionStmt({
      name: extensionName,
      argument_name: typeof extStmt.argument_name === "string" ? extStmt.argument_name : "",
      argument_yin_element: typeof extStmt.argument_yin_element === "boolean" ? extStmt.argument_yin_element : void 0
    });
  }
};

// ts/src/parser/yang-strings.ts
function unescapeYangQuotedString(content, quote) {
  if (quote !== "'" && quote !== '"') {
    throw new Error(`quote must be "'" or '"', got ${JSON.stringify(quote)}`);
  }
  const out = [];
  let i = 0;
  const n = content.length;
  while (i < n) {
    const ch = content[i];
    if (ch !== "\\" || i + 1 >= n) {
      out.push(ch);
      i += 1;
      continue;
    }
    const nxt = content[i + 1];
    if (nxt === "\\") {
      out.push("\\");
      i += 2;
      continue;
    }
    if (nxt === "n") {
      out.push("\n");
      i += 2;
      continue;
    }
    if (nxt === "t") {
      out.push("	");
      i += 2;
      continue;
    }
    if (quote === '"' && nxt === '"') {
      out.push('"');
      i += 2;
      continue;
    }
    if (quote === "'" && nxt === "'") {
      out.push("'");
      i += 2;
      continue;
    }
    if (nxt === "\r" || nxt === "\n") {
      i += 2;
      if (nxt === "\r" && i < n && content[i] === "\n") {
        i += 1;
      }
      while (i < n && (content[i] === " " || content[i] === "	")) {
        i += 1;
      }
      continue;
    }
    out.push("\\", nxt);
    i += 2;
  }
  return out.join("");
}

// ts/src/parser/tokenizer.ts
var isWhitespace = (ch) => ch === " " || ch === "	" || ch === "\n" || ch === "\r";
var isDigit = (ch) => ch >= "0" && ch <= "9";
var isIdentifierStart = (ch) => ch >= "A" && ch <= "Z" || ch >= "a" && ch <= "z" || ch === "_";
var isIdentifierCont = (ch) => isIdentifierStart(ch) || isDigit(ch) || ch === "-" || ch === ".";
var PUNCTUATION2 = new Map(
  Object.values(YangTokenType).filter((v) => v.length === 1).map((v) => [v, v])
);
var YangTokenizer = class {
  tokenize(content, filename) {
    const token_list = [];
    let i = 0;
    const content_len = content.length;
    let current_line = 1;
    let line_start = 0;
    const advance = () => {
      if (i < content_len && content[i] === "\n") {
        current_line += 1;
        line_start = i + 1;
      }
      i += 1;
    };
    const add_token = (tok_type, value, token_start, line_num, line_start_pos) => {
      const char_pos = token_start - line_start_pos;
      token_list.push(makeYangToken(tok_type, value, line_num, char_pos));
    };
    while (i < content_len) {
      const ch = content[i];
      if (isWhitespace(ch)) {
        advance();
        continue;
      }
      if (ch === "/" && i + 1 < content_len && content[i + 1] === "*") {
        advance();
        advance();
        while (i < content_len) {
          if (i + 1 < content_len && content[i] === "*" && content[i + 1] === "/") {
            advance();
            advance();
            break;
          }
          advance();
        }
        continue;
      }
      if (ch === "/" && i + 1 < content_len && content[i + 1] === "/") {
        advance();
        advance();
        while (i < content_len && content[i] !== "\n") {
          advance();
        }
        continue;
      }
      if (ch === '"' || ch === "'") {
        const quote = ch;
        const token_start = i;
        const token_line = current_line;
        const token_line_start = line_start;
        advance();
        const start = i;
        while (i < content_len) {
          if (content[i] === quote) {
            break;
          }
          if (content[i] === "\\" && i + 1 < content_len) {
            advance();
          }
          advance();
        }
        const value = unescapeYangQuotedString(content.slice(start, i), quote);
        if (token_list.at(-1)?.type === YangTokenType.PLUS && token_list.at(-2)?.type === YangTokenType.STRING) {
          token_list[token_list.length - 2].value += value;
          token_list.pop();
        } else {
          add_token(
            YangTokenType.STRING,
            value,
            token_start,
            token_line,
            token_line_start
          );
        }
        advance();
        continue;
      }
      if (ch === "-" && i + 1 < content_len && isDigit(content[i + 1])) {
        const token_start = i;
        const token_line = current_line;
        const token_line_start = line_start;
        advance();
        const start = i;
        while (i < content_len && isDigit(content[i])) {
          advance();
        }
        add_token(
          YangTokenType.INTEGER,
          `-${content.slice(start, i)}`,
          token_start,
          token_line,
          token_line_start
        );
        continue;
      }
      if (isDigit(ch)) {
        const token_start = i;
        const token_line = current_line;
        const token_line_start = line_start;
        const start = i;
        while (i < content_len && isDigit(content[i])) {
          advance();
        }
        if (i < content_len && content[i] === "." && i + 1 < content_len && isDigit(content[i + 1])) {
          advance();
          while (i < content_len && isDigit(content[i])) {
            advance();
          }
          add_token(
            YangTokenType.DOTTED_NUMBER,
            content.slice(start, i),
            token_start,
            token_line,
            token_line_start
          );
        } else {
          add_token(
            YangTokenType.INTEGER,
            content.slice(start, i),
            token_start,
            token_line,
            token_line_start
          );
        }
        continue;
      }
      if (isIdentifierStart(ch)) {
        const token_start = i;
        const token_line = current_line;
        const token_line_start = line_start;
        const start = i;
        advance();
        while (i < content_len && isIdentifierCont(content[i])) {
          advance();
        }
        const lexeme = content.slice(start, i);
        add_token(YangTokenType.IDENTIFIER, lexeme, token_start, token_line, token_line_start);
        continue;
      }
      if (!/\s/u.test(ch)) {
        add_token(PUNCTUATION2.get(ch) ?? YangTokenType.OTHER, ch, i, current_line, line_start);
      }
      advance();
    }
    return new TokenStream(token_list, content, filename);
  }
};

// ts/src/ext/rfc8791.ts
var STRUCTURE_INDEX_KEY = "ietf-yang-structure-ext:structure-index";
var FOREIGN_AUGMENTS = "ietf-yang-structure-ext:foreign-augment-structure";
var FOREIGN_SLOTS = "ietf-yang-structure-ext:foreign-augment-structure-slots";
var exportView = false;
function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
function asStatements(value) {
  return Array.isArray(value) ? value : [];
}
function deepCloneStatement(stmt) {
  return new YangStatement(JSON.parse(JSON.stringify(stmt)));
}
function mergeRootIfFeatures(stmt, inherited) {
  if (inherited.length === 0) {
    return;
  }
  const current = Array.isArray(stmt.if_features) ? stmt.if_features : [];
  stmt.if_features = [...inherited, ...current];
}
function mergeRootWhen(stmt, inheritedWhen) {
  if (!inheritedWhen || typeof inheritedWhen.expression !== "string") {
    return;
  }
  const inheritedExpr = inheritedWhen.expression;
  const existing = isObject(stmt.when) ? stmt.when : void 0;
  const existingExpr = typeof existing?.expression === "string" ? existing.expression : void 0;
  if (existingExpr) {
    const existingDescription = typeof existing?.description === "string" ? existing.description : "";
    stmt.when = {
      expression: `(${inheritedExpr}) and (${existingExpr})`,
      description: existingDescription,
      evaluate_with_parent_context: true
    };
    return;
  }
  stmt.when = {
    expression: inheritedExpr,
    description: typeof inheritedWhen.description === "string" ? inheritedWhen.description : "",
    evaluate_with_parent_context: true
  };
}
function parsePrefixedPath(path, kind) {
  try {
    return parseAbsoluteSchemaPath(path);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new YangSemanticError(`${kind}: ${msg}`);
  }
}
function resolvePrefixedModule2(ctxModule, prefix, fullPath, kind, file) {
  const resolved = resolvePrefixedModule(ctxModule, prefix, file);
  if (!resolved) {
    throw new YangSemanticError(`${kind}: unknown prefix '${prefix}' in path '${fullPath}'`);
  }
  return resolved;
}
function findNamedChild(owner, name) {
  const children2 = asStatements(owner.statements);
  return children2.find((child2) => child2.name === name);
}
function findTopLevelStructure(moduleData, name) {
  const runtime = isObject(moduleData.extension_runtime) ? moduleData.extension_runtime : void 0;
  const structureIndex = runtime && isObject(runtime[STRUCTURE_INDEX_KEY]) ? runtime[STRUCTURE_INDEX_KEY] : void 0;
  const indexed = structureIndex?.[name];
  if (isObject(indexed)) {
    return indexed;
  }
  const statements = asStatements(moduleData.statements);
  return statements.find((stmt) => {
    const extName = typeof stmt.resolved_extension_name === "string" ? stmt.resolved_extension_name : "";
    return extName === "structure" && String(stmt.argument ?? "").trim() === name;
  });
}
function resolveAugmentStructureTarget(ctxModule, path, file) {
  const segments = parsePrefixedPath(path, "augment-structure");
  const first = segments[0];
  const pref0 = first.prefix;
  const firstModule = resolvePrefixedModule2(ctxModule, pref0, path, "augment-structure", file);
  let current = findTopLevelStructure(firstModule, first.name);
  if (!current) {
    throw new YangSemanticError(`augment-structure: no top-level structure '${first.name}' in path '${path}'`);
  }
  for (const segment of segments.slice(1)) {
    resolvePrefixedModule2(ctxModule, segment.prefix, path, "augment-structure", file);
    const next = findNamedChild(current, segment.name);
    if (!next) {
      throw new YangSemanticError(`augment-structure: no child '${segment.name}' in path '${path}'`);
    }
    current = next;
  }
  return current;
}
function targetModule(ctxModule, path, file) {
  const segments = parsePrefixedPath(path, "augment-structure");
  return resolvePrefixedModule2(ctxModule, segments[0].prefix, path, "augment-structure", file);
}
function applyRFC8791Invocation(stmt, contextModule) {
  const moduleName2 = String(stmt.resolved_module_name ?? "");
  const extName = String(stmt.resolved_extension_name ?? "");
  if (moduleName2 !== "ietf-yang-structure-ext") {
    return stmt;
  }
  const applied = stmt._rfc8791_applied === true;
  if (extName === "structure") {
    if (applied) {
      return stmt;
    }
    const runtime = isObject(contextModule.extension_runtime) ? contextModule.extension_runtime : contextModule.extension_runtime = {};
    const idx = isObject(runtime[STRUCTURE_INDEX_KEY]) ? runtime[STRUCTURE_INDEX_KEY] : runtime[STRUCTURE_INDEX_KEY] = {};
    const structureName = String(stmt.argument ?? "").trim();
    if (structureName.length > 0) {
      idx[structureName] = stmt;
      stmt.name = structureName;
    }
    if (stmt._rfc8791_root === true) {
      stmt.data_node_kind = "container";
    }
    stmt._rfc8791_applied = true;
    return stmt;
  }
  if (extName === "augment-structure") {
    if (applied) {
      return void 0;
    }
    const targetPath2 = String(stmt.argument ?? "");
    const foreign = targetModule(contextModule, targetPath2, stmt.included_from) !== contextModule;
    const target = resolveAugmentStructureTarget(contextModule, targetPath2, stmt.included_from);
    if (foreign && exportView) {
      return stmt;
    }
    const copies = asStatements(stmt.statements).map((child2) => deepCloneStatement(child2));
    const inheritedIfFeatures = Array.isArray(stmt.if_features) ? stmt.if_features : [];
    const inheritedWhen = isObject(stmt.when) ? { ...stmt.when } : void 0;
    for (const copy of copies) {
      mergeRootIfFeatures(copy, inheritedIfFeatures);
      mergeRootWhen(copy, inheritedWhen);
      copy.augment_structure = targetPath2;
      copy.augment_structure_module = contextModule.name;
      const targetChildren = asStatements(target.statements);
      targetChildren.push(copy);
      target.statements = targetChildren;
    }
    stmt._rfc8791_applied = true;
    if (foreign && stmt._rfc8791_root === true) {
      stmt._rfc8791_foreign = true;
    }
    return void 0;
  }
  return stmt;
}
function walkAndApply(owner, contextModule, atRoot) {
  const statements = asStatements(owner.statements);
  const out = [];
  let keptExtensions = 0;
  for (const statement of statements) {
    let current = statement;
    const invocation = typeof statement.resolved_module_name === "string" && typeof statement.resolved_extension_name === "string";
    if (invocation) {
      if (atRoot) {
        statement._rfc8791_root = true;
      }
      current = applyRFC8791Invocation(statement, contextModule);
      if (!current && atRoot && statement._rfc8791_foreign === true && !exportView) {
        const runtime = isObject(contextModule.extension_runtime) ? contextModule.extension_runtime : contextModule.extension_runtime = {};
        const saved = Array.isArray(runtime[FOREIGN_AUGMENTS]) ? runtime[FOREIGN_AUGMENTS] : [];
        if (!saved.includes(statement)) {
          saved.push(statement);
          const slots = Array.isArray(runtime[FOREIGN_SLOTS]) ? runtime[FOREIGN_SLOTS] : [];
          slots.push(keptExtensions);
          runtime[FOREIGN_AUGMENTS] = saved;
          runtime[FOREIGN_SLOTS] = slots;
        }
      }
    }
    if (!current) {
      continue;
    }
    walkAndApply(current, contextModule, false);
    if (atRoot && invocation) {
      keptExtensions += 1;
    }
    out.push(current);
  }
  owner.statements = out;
}
function applyBuiltinExtensionInvocations(moduleData, options) {
  const previous = exportView;
  exportView = options?.exportView === true;
  try {
    walkAndApply(moduleData, moduleData, true);
  } finally {
    exportView = previous;
  }
}

// ts/src/xpath/evaluator.ts
function isNode(value) {
  return Boolean(value) && typeof value === "object" && "schema" in value && "parent" in value;
}
function isNodeSet(value) {
  return Array.isArray(value) && (value.length === 0 || isNode(value[0]));
}
function toYangBool(value) {
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0 && !Number.isNaN(value);
  }
  if (typeof value === "string") {
    return value !== "";
  }
  return value !== null && value !== void 0;
}
function nodeSetValues(value) {
  if (Array.isArray(value)) {
    return value.map((item) => isNode(item) ? item.data : item);
  }
  if (isNode(value)) {
    return [value.data];
  }
  if (value === void 0 || value === null) {
    return [];
  }
  return [value];
}
function firstValue(value) {
  const values = nodeSetValues(value);
  return values[0];
}
function asXPathString(value) {
  const first = firstValue(value);
  return first == null ? "" : String(first);
}
function requireArity(name, args, expected) {
  if (args.length !== expected) {
    throw new XPathEvaluationError(`${name}() expects ${expected} arguments, got ${args.length}`);
  }
}
function asXPathNumber(value) {
  const first = firstValue(value);
  const numberValue = Number(first);
  return Number.isNaN(numberValue) ? Number.NaN : numberValue;
}
function xpathRound(value) {
  if (!Number.isFinite(value)) {
    return value;
  }
  if (value === 0) {
    return value;
  }
  if (value >= -0.5 && value < 0) {
    return -0;
  }
  return Math.floor(value + 0.5);
}
function substringOffset(boundary, length) {
  if (!(boundary > 1)) {
    return 0;
  }
  const index = boundary - 1;
  if (!(index < length)) {
    return length;
  }
  return Math.trunc(index);
}
function substringOf(source, start, end) {
  if (Number.isNaN(start) || Number.isNaN(end) || start === Number.POSITIVE_INFINITY || end === Number.NEGATIVE_INFINITY) {
    return "";
  }
  const length = source.length;
  const lo = substringOffset(start, length);
  const hi = end === Number.POSITIVE_INFINITY ? length : substringOffset(end, length);
  if (lo >= hi) {
    return "";
  }
  return source.slice(lo, hi);
}
function coercePair(left, right) {
  if (typeof left === "boolean" || typeof right === "boolean") {
    return [toYangBool(left), toYangBool(right)];
  }
  if (typeof left === "number" && typeof right === "number") {
    return [left, right];
  }
  const leftNum = Number(left);
  const rightNum = Number(right);
  if (!Number.isNaN(leftNum) && !Number.isNaN(rightNum)) {
    return [leftNum, rightNum];
  }
  return [String(left ?? "").trim(), String(right ?? "").trim()];
}
function compareEq(left, right) {
  const leftValues = nodeSetValues(left);
  const rightValues = Array.isArray(right) && !isNodeSet(right) ? right : nodeSetValues(right);
  if (leftValues.length === 0 || rightValues.length === 0) {
    return leftValues.length === 0 && rightValues.length === 0;
  }
  for (const leftValue of leftValues) {
    for (const rightValue of rightValues) {
      if (leftValue == null && rightValue == null) {
        return true;
      }
      if (leftValue == null || rightValue == null) {
        continue;
      }
      const [cl, cr] = coercePair(leftValue, rightValue);
      if (cl === cr) {
        return true;
      }
    }
  }
  return false;
}
function compareOrdered(left, right, op) {
  const before = (a, b) => op === "<" ? a < b : a > b;
  for (const leftValue of nodeSetValues(left)) {
    for (const rightValue of nodeSetValues(right)) {
      const [cl, cr] = coercePair(leftValue, rightValue);
      if (typeof cl === "number" && typeof cr === "number") {
        if (before(cl, cr)) {
          return true;
        }
        continue;
      }
      if (before(`${cl}`, `${cr}`)) {
        return true;
      }
    }
  }
  return false;
}
function expandEntries(node2, step) {
  const schema = node2.schema;
  if (!Array.isArray(node2.data) || schema?.keyword !== "list" && schema?.keyword !== "leaf-list") {
    return null;
  }
  const expanded = [];
  for (const item of node2.data) {
    expanded.push(...step({ data: item, schema, parent: node2 }));
  }
  return expanded;
}
function getSchemaChildren(schema) {
  if (!schema || !Array.isArray(schema.statements)) {
    return [];
  }
  return schema.statements;
}
function findSchemaChild(schema, name) {
  for (const child2 of getSchemaChildren(schema)) {
    if (child2?.name === name) {
      return child2;
    }
  }
  return null;
}
var WILDCARD_DATA_KEYWORDS = /* @__PURE__ */ new Set(["container", "list", "leaf", "leaf-list", "anydata", "anyxml"]);
function dataChildren(schema, out = []) {
  for (const child2 of getSchemaChildren(schema)) {
    if (child2.keyword === "choice" || child2.keyword === "case") {
      dataChildren(child2, out);
    } else if (WILDCARD_DATA_KEYWORDS.has(child2.keyword ?? "")) {
      out.push(child2);
    }
  }
  return out;
}
function stepWildcard(node2, context, module) {
  const data = node2.data;
  const schema = node2.schema;
  const entries = expandEntries(node2, (entry) => stepWildcard(entry, context, module));
  if (entries) {
    return entries;
  }
  if (!data || typeof data !== "object") {
    return [];
  }
  const record = data;
  const rootModule = context.root.schema?.name ?? "";
  const result = [];
  for (const child2 of dataChildren(schema)) {
    const local2 = child2.name ?? "";
    const definedIn = child2.defining_module || rootModule;
    if (module !== void 0 && definedIn !== module) {
      continue;
    }
    const key2 = !rootModule || definedIn === rootModule ? local2 : `${definedIn}:${local2}`;
    let value;
    if (Object.prototype.hasOwnProperty.call(record, key2)) {
      value = record[key2];
      if (value === null) {
        value = true;
      }
    } else {
      value = defaultValue(child2);
    }
    if (value === void 0) {
      continue;
    }
    if (child2.keyword === "list" || child2.keyword === "leaf-list") {
      const items = Array.isArray(value) ? value : [value];
      for (const item of items) {
        result.push({ data: item, schema: child2, parent: node2 });
      }
    } else {
      result.push({ data: value, schema: child2, parent: node2 });
    }
  }
  return result;
}
function defaultValue(schema) {
  if (!schema || schema.keyword !== "leaf") {
    return void 0;
  }
  const raw = schema.default;
  const typeName = schema.type?.name;
  if (typeName === "boolean" && typeof raw === "string") {
    const lower = raw.toLowerCase();
    if (lower === "true") return true;
    if (lower === "false") return false;
  }
  return raw;
}
function definingModule(child2, rootModule) {
  return child2.defining_module || rootModule;
}
function memberName(child2, rootModule) {
  const local2 = child2.name ?? "";
  const owner = definingModule(child2, rootModule);
  return !rootModule || owner === rootModule ? local2 : `${owner}:${local2}`;
}
function stepNamed(node2, segment, rootModule) {
  const prefix = stepPrefix(segment.step);
  if (prefix === void 0) {
    return stepNode(node2, segment.step, rootModule);
  }
  const data = node2.data;
  const schema = node2.schema;
  if (Array.isArray(data) && (schema?.keyword === "list" || schema?.keyword === "leaf-list")) {
    return data.flatMap((item) => stepNamed({ data: item, schema, parent: node2 }, segment, rootModule));
  }
  const module = segment.module ?? prefix;
  const local2 = segment.step.slice(prefix.length + 1);
  const child2 = dataChildren(schema).find((c) => c.name === local2 && definingModule(c, rootModule) === module);
  if (!child2) {
    return [];
  }
  return stepChild(node2, memberName(child2, rootModule), child2);
}
function stepNode(node2, step, rootModule) {
  const entries = expandEntries(node2, (entry) => stepNode(entry, step, rootModule));
  if (entries) {
    return entries;
  }
  const childSchema = findSchemaChild(node2.schema, step);
  return stepChild(node2, childSchema ? memberName(childSchema, rootModule) : step, childSchema);
}
function stepChild(node2, step, childSchema) {
  const data = node2.data;
  let value;
  if (data && typeof data === "object" && !Array.isArray(data)) {
    const asRecord2 = data;
    if (step in asRecord2) {
      value = asRecord2[step];
      if (value === null) {
        value = true;
      }
    } else {
      value = defaultValue(childSchema);
    }
  }
  if (value === void 0) {
    return [];
  }
  if (childSchema?.keyword === "list" || childSchema?.keyword === "leaf-list") {
    if (Array.isArray(value)) {
      return value.map((item) => ({ data: item, schema: childSchema, parent: node2 }));
    }
    return [{ data: value, schema: childSchema, parent: node2 }];
  }
  return [{ data: value, schema: childSchema, parent: node2 }];
}
var XPathEvaluator = class {
  eval(ast, context, node2) {
    switch (ast.kind) {
      case "literal":
        return ast.value;
      case "path":
        return this.evalPath(ast, context, node2);
      case "binary":
        return this.evalBinary(ast, context, node2);
      case "function":
        return this.evalFunction(ast.name, ast.args, context, node2);
      default:
        return null;
    }
  }
  evalPath(path, context, node2) {
    let nodes = [path.isAbsolute ? context.root : node2];
    for (const segment of path.segments) {
      if (segment.step === ".") {
      } else if (segment.step === "..") {
        nodes = nodes.map((entry) => entry.parent).filter((entry) => Boolean(entry));
      } else if (isWildcardStep(segment.step)) {
        if (segment.step !== "*" && segment.module === void 0) {
          throw new XPathEvaluationError(`Prefix of '${segment.step}' is not bound to a module`);
        }
        const next = [];
        for (const entry of nodes) {
          next.push(...stepWildcard(entry, context, segment.module));
        }
        nodes = next;
      } else {
        const next = [];
        const rootModule = context.root.schema?.name ?? "";
        for (const entry of nodes) {
          next.push(...stepNamed(entry, segment, rootModule));
        }
        nodes = next;
      }
      if (segment.predicate) {
        const filtered = [];
        for (let index = 0; index < nodes.length; index += 1) {
          const candidate = nodes[index];
          const value = this.eval(segment.predicate, context, candidate);
          let keep = false;
          if (typeof value === "number" && Number.isFinite(value)) {
            keep = Math.trunc(value) === index + 1;
          } else {
            keep = toYangBool(value);
          }
          if (keep) {
            filtered.push(candidate);
          }
        }
        nodes = filtered;
      }
    }
    return nodes;
  }
  evalBinary(ast, context, node2) {
    const op = ast.operator;
    if (op === "or") {
      const left2 = this.eval(ast.left, context, node2);
      if (toYangBool(left2)) {
        return true;
      }
      return toYangBool(this.eval(ast.right, context, node2));
    }
    if (op === "and") {
      const left2 = this.eval(ast.left, context, node2);
      if (!toYangBool(left2)) {
        return false;
      }
      return toYangBool(this.eval(ast.right, context, node2));
    }
    if (op === "/") {
      const left2 = this.eval(ast.left, context, node2);
      const leftNodes = isNodeSet(left2) ? left2 : isNode(left2) ? [left2] : [];
      const results = [];
      for (const leftNode of leftNodes) {
        const right2 = this.eval(ast.right, context, leftNode);
        if (isNodeSet(right2)) {
          results.push(...right2);
        } else if (isNode(right2)) {
          results.push(right2);
        }
      }
      return results;
    }
    const left = this.eval(ast.left, context, node2);
    const right = this.eval(ast.right, context, node2);
    if (op === "=") {
      return compareEq(left, right);
    }
    if (op === "!=") {
      return !compareEq(left, right);
    }
    if (op === "<") {
      return compareOrdered(left, right, "<");
    }
    if (op === ">") {
      return compareOrdered(left, right, ">");
    }
    if (op === "<=") {
      return compareEq(left, right) || compareOrdered(left, right, "<");
    }
    if (op === ">=") {
      return compareEq(left, right) || compareOrdered(left, right, ">");
    }
    if (op === "+") {
      const sum = Number(firstValue(left)) + Number(firstValue(right));
      return Number.isNaN(sum) ? Number.NaN : sum;
    }
    if (op === "-") {
      const diff = Number(firstValue(left)) - Number(firstValue(right));
      return Number.isNaN(diff) ? Number.NaN : diff;
    }
    if (op === "*") {
      const product = Number(firstValue(left)) * Number(firstValue(right));
      return Number.isNaN(product) ? Number.NaN : product;
    }
    if (op === "div") {
      const quotient = Number(firstValue(left)) / Number(firstValue(right));
      return Number.isNaN(quotient) ? Number.NaN : quotient;
    }
    if (op === "mod") {
      const remainder = Number(firstValue(left)) % Number(firstValue(right));
      return Number.isNaN(remainder) ? Number.NaN : remainder;
    }
    return null;
  }
  stringPair(fn, args, context, node2) {
    requireArity(fn, args, 2);
    return [asXPathString(this.eval(args[0], context, node2)), asXPathString(this.eval(args[1], context, node2))];
  }
  evalFunction(name, args, context, node2) {
    const fn = name.toLowerCase();
    if (fn === "current") {
      return context.current;
    }
    if (fn === "not") {
      if (args.length !== 1) {
        return null;
      }
      return !toYangBool(this.eval(args[0], context, node2));
    }
    if (fn === "true") {
      return true;
    }
    if (fn === "false") {
      return false;
    }
    if (fn === "count") {
      if (args.length !== 1) {
        return 0;
      }
      const value = this.eval(args[0], context, node2);
      return isNodeSet(value) ? value.length : value == null ? 0 : 1;
    }
    if (fn === "string") {
      if (args.length !== 1) {
        return "";
      }
      const value = firstValue(this.eval(args[0], context, node2));
      return value == null ? "" : String(value);
    }
    if (fn === "number") {
      if (args.length !== 1) {
        return Number.NaN;
      }
      const value = firstValue(this.eval(args[0], context, node2));
      const numberValue = Number(value);
      return Number.isNaN(numberValue) ? Number.NaN : numberValue;
    }
    if (fn === "boolean") {
      if (args.length !== 1) {
        return false;
      }
      return toYangBool(this.eval(args[0], context, node2));
    }
    if (fn === "string-length") {
      if (args.length !== 1) {
        return 0;
      }
      const value = firstValue(this.eval(args[0], context, node2));
      return value == null ? 0 : String(value).length;
    }
    if (fn === "concat") {
      return args.map((arg) => String(firstValue(this.eval(arg, context, node2)) ?? "")).join("");
    }
    if (fn === "contains") {
      const [source, needle] = this.stringPair(fn, args, context, node2);
      return source.includes(needle);
    }
    if (fn === "starts-with") {
      const [source, needle] = this.stringPair(fn, args, context, node2);
      return source.startsWith(needle);
    }
    if (fn === "substring") {
      if (args.length !== 2 && args.length !== 3) {
        throw new XPathEvaluationError(`${fn}() expects 2 or 3 arguments, got ${args.length}`);
      }
      const source = asXPathString(this.eval(args[0], context, node2));
      const start = xpathRound(asXPathNumber(this.eval(args[1], context, node2)));
      const end = args.length === 3 ? start + xpathRound(asXPathNumber(this.eval(args[2], context, node2))) : Number.POSITIVE_INFINITY;
      return substringOf(source, start, end);
    }
    if (fn === "substring-before") {
      const [source, needle] = this.stringPair(fn, args, context, node2);
      const index = source.indexOf(needle);
      if (index < 0) {
        return "";
      }
      return source.slice(0, index);
    }
    if (fn === "substring-after") {
      const [source, needle] = this.stringPair(fn, args, context, node2);
      const index = source.indexOf(needle);
      if (index < 0) {
        return "";
      }
      return source.slice(index + needle.length);
    }
    if (fn === "translate") {
      if (args.length !== 3) {
        return "";
      }
      const source = String(firstValue(this.eval(args[0], context, node2)) ?? "");
      const fromChars = String(firstValue(this.eval(args[1], context, node2)) ?? "");
      const toChars = String(firstValue(this.eval(args[2], context, node2)) ?? "");
      if (fromChars.length === 0) {
        return source;
      }
      const map = /* @__PURE__ */ new Map();
      for (let i = 0; i < fromChars.length; i += 1) {
        map.set(fromChars[i], i < toChars.length ? toChars[i] : null);
      }
      let out = "";
      for (const ch of source) {
        if (!map.has(ch)) {
          out += ch;
          continue;
        }
        const replacement = map.get(ch);
        if (replacement != null) {
          out += replacement;
        }
      }
      return out;
    }
    if (fn === "deref") {
      if (args.length !== 1) {
        return [];
      }
      const start = context.current ?? node2;
      const raw = this.eval(args[0], context, start);
      const sourceNodes = isNodeSet(raw) ? raw : isNode(raw) ? [raw] : [];
      const results = [];
      for (const sourceNode of sourceNodes) {
        const typeShape = sourceNode.schema?.type;
        if (!typeShape || typeShape.name !== "leafref") {
          continue;
        }
        const leafrefPath2 = typeShape.path;
        if (!leafrefPath2 || leafrefPath2.kind !== "path") {
          continue;
        }
        const targets = this.evalPath(leafrefPath2, context, sourceNode);
        for (const target of targets) {
          if (target.data === sourceNode.data) {
            results.push(target);
          }
        }
      }
      return results;
    }
    if (fn === "derived-from" || fn === "derived-from-or-self") {
      if (args.length !== 2) {
        return false;
      }
      const rootSchema = context.root?.schema;
      if (!(rootSchema instanceof YangModule)) {
        return false;
      }
      const importer = rootSchema;
      const start = node2;
      let v1 = this.eval(args[0], context, start);
      if (isNodeSet(v1)) {
        if (v1.length === 0) {
          return false;
        }
        v1 = v1[0].data;
      } else if (isNode(v1)) {
        v1 = v1.data;
      } else {
        v1 = firstValue(v1);
      }
      if (typeof v1 !== "string") {
        return false;
      }
      const v2Raw = this.eval(args[1], context, start);
      const v2 = firstValue(v2Raw);
      if (typeof v2 !== "string") {
        return false;
      }
      if (fn === "derived-from") {
        return isDerivedFromStrictQNames(importer, v1, v2);
      }
      return isDerivedFromOrSelfQNames(importer, v1, v2);
    }
    throw unknownFunctionError(name);
  }
};

// ts/src/encoding/normalization.ts
var object = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
var truth = (v) => v !== false && v !== null;
function ext(stmt, name) {
  return stmt.resolved_module_name === "xyang-transform" && stmt.resolved_extension_name === name;
}
var Normalization = class {
  expandDotted;
  compiled = /* @__PURE__ */ new WeakMap();
  annotated = /* @__PURE__ */ new WeakSet();
  rootContext;
  skipProjection = false;
  compile(s) {
    if (s === void 0) throw new ExpressionError("normalization expression is required");
    const stringMap = /^\s*map\s*\(\s*split\s*\(\s*("(?:[^"\\]|\\.)*")\s*\)\s*,\s*([A-Za-z_][A-Za-z_0-9-]*)\s*:\s*\{\s*([A-Za-z_][A-Za-z_0-9-]*)\s*:\s*\$value\s*\}\s*\)\s*$/.exec(s);
    if (stringMap) {
      const delimiter = JSON.parse(stringMap[1]);
      if (typeof delimiter !== "string") throw new ExpressionError("split requires string input and argument");
      return (value) => {
        if (typeof value !== "string") throw new ExpressionError("split requires string input and argument");
        const parts = delimiter === "" ? Array.from(value) : value.split(delimiter);
        return { [stringMap[2]]: parts.map((part) => ({ [stringMap[3]]: part })) };
      };
    }
    const match = /^\s*map\s*\(\s*keys\s*\(\s*(\/[^()]*)\s*\)\s*,\s*([A-Za-z_][A-Za-z_0-9-]*)\s*:\s*\{\s*([A-Za-z_][A-Za-z_0-9-]*)\s*:\s*\$key\s*,\s*\.\.\.\$value\s*\}\s*\)\s*$/.exec(s);
    if (!match) {
      const expr = compileExpression(s);
      return (value) => evaluateExpression(expr, value);
    }
    const path = parseXPath(match[1].trim());
    return (value) => {
      if (this.skipProjection) return value;
      if (!object(value)) throw new ExpressionError("key projection requires an object");
      const [, , target, keyField] = match;
      if (!this.rootContext) throw new ExpressionError("key projection requires an instance root");
      const root = this.rootContext();
      const selected = new XPathEvaluator().eval(path, { current: root, root }, root);
      if (!Array.isArray(selected) || selected.some((n) => !n || typeof n !== "object" || typeof n.data !== "string")) throw new ExpressionError("keys XPath must select string nodes");
      const matches = new Set(selected.map((n) => n.data));
      if (!Object.keys(value).some((key2) => matches.has(key2))) return value;
      if (Object.hasOwn(value, target)) throw new ExpressionError(`projection target '${target}' already exists`);
      const result = /* @__PURE__ */ Object.create(null), rows = [];
      for (const [key2, item] of Object.entries(value)) {
        if (!matches.has(key2)) {
          result[key2] = item;
          continue;
        }
        if (item !== null && !object(item)) throw new ExpressionError(`value for '${key2}' must be an object or null`);
        if (object(item) && Object.hasOwn(item, keyField)) throw new ExpressionError(`projected key field '${keyField}' already exists`);
        rows.push({ [keyField]: key2, ...item ?? {} });
      }
      result[target] = rows;
      return result;
    };
  }
  constructor(module) {
    const opts = (module.statements ?? []).filter((s) => ext(s, "expand-dotted-keys"));
    if (opts.length > 1) throw new ExpressionError("duplicate module option 'expand_dotted_keys'");
    const option = opts[0];
    if (option && (option.argument !== "true" && option.argument !== "false" || option.statements?.length)) throw new ExpressionError("xt:expand-dotted-keys requires true or false and no body");
    this.expandDotted = option?.argument === "true";
  }
  rules(schema, isModule = false) {
    const old = this.compiled.get(schema);
    if (old) return old;
    const result = [];
    for (const stmt of schema.statements ?? []) {
      if (!isModule && ext(stmt, "expand-dotted-keys")) throw new ExpressionError("xt:expand-dotted-keys is allowed only at module level");
      if (!ext(stmt, "normalize")) continue;
      if (stmt.argument !== void 0) throw new ExpressionError("xt:normalize does not take an argument");
      this.annotated.add(schema);
      const clauses = stmt.statements ?? [];
      if (clauses.length === 1 && ext(clauses[0], "apply") && !clauses[0].statements?.length) {
        result.push([() => true, this.compile(clauses[0].argument)]);
      } else if (clauses.length === 2 && ext(clauses[0], "if") && !clauses[0].statements?.length && ext(clauses[1], "apply")) {
        if (clauses[1].statements?.length) throw new ExpressionError("xt:apply requires an expression and no body");
        result.push([this.compile(clauses[0].argument), this.compile(clauses[1].argument)]);
      } else if (clauses.length && clauses.every((s) => ext(s, "if"))) {
        for (const clause of clauses) {
          const parts = clause.statements ?? [];
          if (parts.length !== 1 || !ext(parts[0], "apply") || parts[0].statements?.length) throw new ExpressionError("nested xt:if requires exactly one xt:apply");
          result.push([this.compile(clause.argument), this.compile(parts[0].argument)]);
        }
      } else throw new ExpressionError("xt:normalize requires exactly xt:if followed by xt:apply");
    }
    this.compiled.set(schema, result);
    return result;
  }
  collection(schema, value) {
    this.rules(schema);
    return value === null && this.annotated.has(schema) ? [] : value;
  }
  visit(schema, value) {
    for (const [test, apply] of this.rules(schema)) if (truth(test(value))) value = apply(value);
    return value;
  }
};

// ts/src/ext/transform.ts
var TOKEN = /\s*(?:("(?:[^"\\]|\\.)*")|([A-Za-z_][A-Za-z_0-9-]*)|([0-9]+)|(==|!=|[.\[\]{}():,|]))/y;
var ExpressionError = class extends Error {
  constructor(message) {
    super(message);
    this.name = "ExpressionError";
  }
};
var Parser = class {
  tokens = [];
  i = 0;
  constructor(text) {
    let pos = 0;
    while (pos < text.length) {
      if (!text.slice(pos).trim()) break;
      TOKEN.lastIndex = pos;
      const match = TOKEN.exec(text);
      if (!match || match.index !== pos) {
        throw new ExpressionError(`unsupported expression syntax at offset ${pos}`);
      }
      const [, string, word, number, symbol] = match;
      if (string !== void 0) {
        try {
          this.tokens.push({ kind: "literal", value: JSON.parse(string) });
        } catch (exc) {
          throw new ExpressionError(`invalid string: ${exc instanceof Error ? exc.message : String(exc)}`);
        }
      } else if (word !== void 0) {
        this.tokens.push({ kind: "word", value: word });
      } else if (number !== void 0) {
        this.tokens.push({ kind: "number", value: Number(number) });
      } else {
        this.tokens.push({ kind: symbol, value: symbol });
      }
      pos = TOKEN.lastIndex;
    }
  }
  take(value) {
    const token = this.tokens[this.i];
    if (!token) return false;
    if (token.kind === value || token.value === value) {
      this.i += 1;
      return true;
    }
    return false;
  }
  require(value) {
    if (!this.take(value)) throw new ExpressionError(`expected ${JSON.stringify(value)}`);
  }
  parse() {
    const result = this.pipeline();
    if (this.i !== this.tokens.length) {
      throw new ExpressionError(`unexpected token ${JSON.stringify(this.tokens[this.i].value)}`);
    }
    return result;
  }
  pipeline() {
    let node2 = this.boolean();
    while (this.take("|")) node2 = ["pipe", node2, this.boolean()];
    return node2;
  }
  boolean() {
    let node2 = this.equality();
    while (this.i < this.tokens.length && (this.tokens[this.i].value === "and" || this.tokens[this.i].value === "or")) {
      const op = this.tokens[this.i].value;
      this.i += 1;
      node2 = [op, node2, this.equality()];
    }
    return node2;
  }
  equality() {
    const node2 = this.primary();
    if (this.take("==")) return ["eq", node2, this.primary()];
    if (this.take("!=")) return ["ne", node2, this.primary()];
    return node2;
  }
  primary() {
    if (this.take("[")) {
      this.require("]");
      return ["literal", []];
    }
    if (this.take("(")) {
      const node2 = this.pipeline();
      this.require(")");
      return node2;
    }
    if (this.take("{")) {
      const fields = [];
      if (!this.take("}")) {
        for (; ; ) {
          const token = this.tokens[this.i];
          if (!token || token.kind !== "word" && token.kind !== "literal") {
            throw new ExpressionError("expected object field name");
          }
          const key2 = String(token.value);
          this.i += 1;
          if (fields.some(([existing]) => existing === key2)) {
            throw new ExpressionError(`duplicate object field ${JSON.stringify(key2)}`);
          }
          this.require(":");
          fields.push([key2, this.pipeline()]);
          if (this.take("}")) break;
          this.require(",");
        }
      }
      return ["object", fields];
    }
    if (this.take(".")) {
      let node2 = ["input"];
      while (this.take("[")) {
        const token = this.tokens[this.i];
        if (!token || token.kind !== "number" && token.kind !== "literal") {
          throw new ExpressionError("expected array index or object key");
        }
        const key2 = token.value;
        this.i += 1;
        this.require("]");
        node2 = ["index", node2, key2];
      }
      return node2;
    }
    if (this.i >= this.tokens.length) throw new ExpressionError("expected expression");
    const { kind, value } = this.tokens[this.i];
    this.i += 1;
    if (kind === "literal" || kind === "number") return ["literal", value];
    if (kind !== "word") throw new ExpressionError(`unexpected token ${JSON.stringify(value)}`);
    if (value === "true" || value === "false" || value === "null") {
      return ["literal", value === "true" ? true : value === "false" ? false : null];
    }
    if (value === "type" || value === "length" || value === "to_entries") return [value];
    if (value === "contains" || value === "split" || value === "has") {
      this.require("(");
      const arg = this.pipeline();
      this.require(")");
      return [value, arg];
    }
    throw new ExpressionError(`unsupported function or identifier ${JSON.stringify(value)}`);
  }
};
var compiled = /* @__PURE__ */ new Map();
function compileExpression(expression) {
  const cached = compiled.get(expression);
  if (cached) return cached;
  try {
    const expr = new Parser(expression).parse();
    compiled.set(expression, expr);
    return expr;
  } catch (exc) {
    if (exc instanceof ExpressionError) {
      throw new ExpressionError(`invalid normalization expression ${JSON.stringify(expression)}: ${exc.message}`);
    }
    throw exc;
  }
}
function truth2(value) {
  return value !== null && value !== false;
}
function sameType(a, b) {
  if (a === null || b === null) return a === null && b === null;
  if (Array.isArray(a) || Array.isArray(b)) return Array.isArray(a) && Array.isArray(b);
  if (typeof a === "object" || typeof b === "object") {
    return typeof a === "object" && typeof b === "object" && !Array.isArray(a) && !Array.isArray(b);
  }
  return typeof a === typeof b;
}
function evaluateExpression(expr, value) {
  const op = expr[0];
  if (op === "input") return value;
  if (op === "literal") return expr[1];
  if (op === "pipe") return evaluateExpression(expr[2], evaluateExpression(expr[1], value));
  if (op === "type") {
    if (value === null) return "null";
    if (typeof value === "boolean") return "boolean";
    if (typeof value === "string") return "string";
    if (typeof value === "number") return "number";
    if (Array.isArray(value)) return "array";
    if (value && typeof value === "object") return "object";
    throw new ExpressionError("value is not JSON data");
  }
  if (op === "object") {
    const out = {};
    for (const [key2, child2] of expr[1]) out[key2] = evaluateExpression(child2, value);
    return out;
  }
  if (op === "length") {
    if (typeof value === "string") return Array.from(value).length;
    if (Array.isArray(value)) return value.length;
    if (value && typeof value === "object") return Object.keys(value).length;
    throw new ExpressionError("length requires a string, array, or object");
  }
  if (op === "to_entries") {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return Object.entries(value).map(([key2, item]) => ({ key: key2, value: item }));
    }
    if (Array.isArray(value)) {
      return value.map((item, index) => ({ key: index, value: item }));
    }
    throw new ExpressionError("to_entries requires an array or object");
  }
  if (op === "index") {
    const obj2 = evaluateExpression(expr[1], value);
    const key2 = expr[2];
    if (Array.isArray(obj2) && typeof key2 === "number") return key2 >= 0 && key2 < obj2.length ? obj2[key2] : null;
    if (obj2 && typeof obj2 === "object" && !Array.isArray(obj2) && typeof key2 === "string") {
      return obj2[key2] ?? null;
    }
    throw new ExpressionError("index requires an array index or object key");
  }
  if (op === "eq" || op === "ne") {
    const a = evaluateExpression(expr[1], value);
    const b = evaluateExpression(expr[2], value);
    const equal = sameType(a, b) && (typeof a === "object" && a !== null ? JSON.stringify(a) === JSON.stringify(b) : a === b);
    return op === "eq" ? equal : !equal;
  }
  if (op === "and" || op === "or") {
    const left = truth2(evaluateExpression(expr[1], value));
    return op === "and" ? left && truth2(evaluateExpression(expr[2], value)) : left || truth2(evaluateExpression(expr[2], value));
  }
  if (op === "has") {
    const arg = evaluateExpression(expr[1], value);
    if (value && typeof value === "object" && !Array.isArray(value) && typeof arg === "string") {
      return Object.prototype.hasOwnProperty.call(value, arg);
    }
    if (Array.isArray(value) && typeof arg === "number" && Number.isInteger(arg)) {
      return arg >= 0 && arg < value.length;
    }
    throw new ExpressionError("has requires an object key or array index");
  }
  if (op === "contains" || op === "split") {
    const arg = evaluateExpression(expr[1], value);
    if (typeof value !== "string" || typeof arg !== "string") {
      throw new ExpressionError(`${op} requires string input and argument`);
    }
    if (op === "contains") return value.includes(arg);
    return arg === "" ? [...value] : value.split(arg);
  }
  throw new ExpressionError(`unsupported operation ${JSON.stringify(op)}`);
}

// ts/src/transform/parent-when.ts
function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}
function mergeParentWhen(owner, child2, extra) {
  const ownerWhen = owner.when;
  if (!ownerWhen || typeof ownerWhen.expression !== "string" || ownerWhen.expression.trim() === "") {
    return;
  }
  const existing = child2.when;
  if (!existing?.expression) {
    child2.when = { ...deepClone(ownerWhen), evaluate_with_parent_context: true };
    return;
  }
  child2.when = {
    ...existing,
    expression: `(${String(existing.expression)}) and (${ownerWhen.expression})`,
    ...extra ? extra(existing, ownerWhen) : {},
    description: String(existing.description ?? ""),
    evaluate_with_parent_context: true
  };
}

// ts/src/transform/augment-expand.ts
var SCHEMA_NODE_KEYWORDS = /* @__PURE__ */ new Set([
  "container",
  "list",
  "leaf",
  "leaf-list",
  "choice",
  "case",
  "anydata",
  "anyxml",
  "notification",
  "rpc",
  "action",
  "input",
  "output"
]);
function deepCloneStatement2(stmt) {
  return new YangStatement(JSON.parse(JSON.stringify(stmt)));
}
function asStatements2(value) {
  return Array.isArray(value) ? value : [];
}
function sourceFileOf(stmt) {
  return stmt?.included_from;
}
function pathSegmentsFromAugment(aug, path) {
  const stored = aug.augment_path_segments;
  if (Array.isArray(stored) && stored.length > 0) {
    return stored;
  }
  try {
    return parseAbsoluteSchemaPath(path);
  } catch (err) {
    throw new YangSyntaxError(err instanceof Error ? err.message : String(err));
  }
}
function augmentSegmentCount(aug) {
  const path = String(aug.augment_path ?? aug.argument ?? "");
  return pathSegmentsFromAugment(aug, path).length;
}
function isSchemaNode(stmt) {
  const kw = typeof stmt.keyword === "string" ? stmt.keyword : "";
  return Boolean(stmt.name) && SCHEMA_NODE_KEYWORDS.has(kw);
}
function materializeOperationIo(parent2, name) {
  const keyword = parent2.keyword;
  if (keyword !== "rpc" && keyword !== "action" || name !== "input" && name !== "output") {
    return void 0;
  }
  const node2 = new YangStatement({ keyword: name, name, statements: [] });
  const children2 = asStatements2(parent2.statements);
  const outputIdx = children2.findIndex((child2) => child2.keyword === "output");
  if (name === "input" && outputIdx >= 0) {
    children2.splice(outputIdx, 0, node2);
  } else {
    children2.push(node2);
  }
  parent2.statements = children2;
  return node2;
}
function findNamedSchemaChild(parent2, name) {
  for (const child2 of asStatements2(parent2.statements)) {
    if (child2.name === name && isSchemaNode(child2)) {
      return child2;
    }
  }
  return materializeOperationIo(parent2, name);
}
function findToplevelSchemaChild(module, name) {
  for (const child2 of asStatements2(module.statements)) {
    if (child2.name === name && isSchemaNode(child2)) {
      return child2;
    }
  }
  return void 0;
}
function resolveAugmentTarget(ctxModule, path, aug) {
  return resolveAbsoluteSchemaPath({
    ctxModule,
    path,
    segments: aug ? pathSegmentsFromAugment(aug, path) : void 0,
    kind: "augment",
    findToplevel: findToplevelSchemaChild,
    file: sourceFileOf(aug)
  });
}
function walkAbsoluteSchemaPath(options) {
  const { ctxModule, path, kind, findToplevel, file } = options;
  let segments = options.segments;
  if (!segments || segments.length === 0) {
    try {
      segments = parseAbsoluteSchemaPath(path);
    } catch (err) {
      throw new YangSyntaxError(err instanceof Error ? err.message : String(err));
    }
  }
  const first = segments[0];
  const pref0 = first.prefix;
  const name0 = first.name;
  const mod0 = resolvePrefixedModule(ctxModule, pref0, file);
  if (!mod0) {
    throw new YangSyntaxError(
      `${kind}: unknown prefix '${pref0}' in path '${path}' (module '${String(ctxModule.name ?? "")}')`
    );
  }
  let cur = findToplevel(mod0, name0);
  if (!cur) {
    throw new YangSyntaxError(
      `${kind}: no top-level schema node '${name0}' in module '${String(mod0.name ?? "")}' (path '${path}')`
    );
  }
  let parent2 = mod0;
  for (const seg of segments.slice(1)) {
    const pref = seg.prefix;
    const nm = seg.name;
    if (!resolvePrefixedModule(ctxModule, pref, file)) {
      throw new YangSyntaxError(`${kind}: unknown prefix '${pref}' in path '${path}'`);
    }
    const nxt = findNamedSchemaChild(cur, nm);
    if (!nxt) {
      throw new YangSyntaxError(
        `${kind}: no child '${nm}' under node in path '${path}' (after '${String(cur.name ?? "")}')`
      );
    }
    parent2 = cur;
    cur = nxt;
  }
  return { parent: parent2, node: cur };
}
function resolveAbsoluteSchemaPath(options) {
  const cur = walkAbsoluteSchemaPath(options).node;
  if (!Array.isArray(cur.statements) && cur.statements !== void 0) {
    throw new YangSyntaxError(
      `${options.kind}: target node '${String(cur.name ?? "?")}' cannot contain schema substatements (path '${options.path}')`
    );
  }
  if (cur.statements === void 0) {
    cur.statements = [];
  }
  return cur;
}
function removeSchemaChild(parent2, node2) {
  const stmts = asStatements2(parent2.statements);
  const idx = stmts.indexOf(node2);
  if (idx < 0) {
    throw new YangSemanticError(
      `deviation: target node '${String(node2.name ?? "?")}' is not a child of its parent`
    );
  }
  stmts.splice(idx, 1);
  parent2.statements = stmts;
}
function cowStatement(stmt) {
  const copy = new YangStatement(stmt);
  copy.statements = stmt.statements.slice();
  return copy;
}
function cowModuleData(data) {
  return new YangModule(
    {
      name: data.name,
      yang_version: data.yang_version,
      namespace: data.namespace,
      prefix: data.prefix,
      organization: data.organization,
      contact: data.contact,
      description: data.description,
      typedefs: data.typedefs,
      identities: data.identities,
      import_prefixes: { ...data.import_prefixes },
      extensions: data.extensions,
      extension_runtime: data.extension_runtime,
      features: data.features,
      feature_if_features: data.feature_if_features,
      groupings: data.groupings,
      statements: data.statements.slice()
    },
    data.source
  );
}
function schemaChildIndex(parent2, name) {
  const idx = asStatements2(parent2.statements).findIndex(
    (stmt) => stmt.name === name && isSchemaNode(stmt)
  );
  if (idx >= 0) {
    return idx;
  }
  const node2 = materializeOperationIo(parent2, name);
  return node2 ? parent2.statements.indexOf(node2) : -1;
}
function copiedPathToTarget(moduleData, segments) {
  const pathText2 = `/${segments.map((seg) => `${seg.prefix}:${seg.name}`).join("/")}`;
  const missing = (name, under) => new YangSemanticError(`deviation: no child '${name}' under '${under}' (path '${pathText2}')`);
  let parent2 = moduleData;
  parent2.statements = asStatements2(parent2.statements).slice();
  let index = schemaChildIndex(parent2, segments[0].name);
  if (index < 0) {
    throw missing(segments[0].name, String(moduleData.name ?? "?"));
  }
  for (const seg of segments.slice(1)) {
    const current = cowStatement(parent2.statements[index]);
    parent2.statements[index] = current;
    parent2 = current;
    index = schemaChildIndex(current, seg.name);
    if (index < 0) {
      throw missing(seg.name, String(current.name ?? "?"));
    }
  }
  return { parent: parent2, index };
}
function privateTargetModule(root, owner, copies) {
  if (owner === root) {
    return root;
  }
  for (const cloned2 of copies.values()) {
    if (cloned2 === owner) {
      return owner;
    }
  }
  const existing = copies.get(owner);
  if (existing) {
    return existing;
  }
  const cloned = cowModuleData(owner);
  copies.set(owner, cloned);
  const imports = root.import_prefixes ?? {};
  root.import_prefixes = imports;
  for (const [prefix, mod] of Object.entries(imports)) {
    if (mod === owner) {
      imports[prefix] = cloned;
    }
  }
  return cloned;
}
var DeviateError = class extends YangSemanticError {
};
function single(node2, deviate, prop, present, alwaysPresent = false) {
  if (deviate.kind === "add" && present) {
    throw new DeviateError(
      `cannot 'deviate add' ${prop}: target ${String(node2.keyword)} '${String(node2.name)}' already has it (use 'deviate replace')`
    );
  }
  if (deviate.kind === "replace" && !present && !alwaysPresent) {
    throw new DeviateError(
      `cannot 'deviate replace' ${prop}: target ${String(node2.keyword)} '${String(node2.name)}' has no ${prop} (use 'deviate add')`
    );
  }
}
function requireKind(node2, prop, keywords) {
  if (!keywords.includes(String(node2.keyword))) {
    throw new DeviateError(`${prop} does not apply to target ${String(node2.keyword)} '${String(node2.name)}'`);
  }
}
var CONFIG_NODES = ["container", "leaf", "leaf-list", "list", "choice", "case", "anydata", "anyxml"];
var MUST_NODES = ["container", "leaf", "leaf-list", "list", "anydata", "anyxml", "input", "output", "notification"];
function applyDeviateDefaults(node2, deviate) {
  const values = deviate.defaults;
  if (node2.keyword === "leaf-list") {
    const current = Array.isArray(node2.defaults) ? [...node2.defaults] : [];
    if (deviate.kind === "add") {
      node2.defaults = [...current, ...values];
    } else if (deviate.kind === "replace") {
      if (current.length === 0) {
        throw new DeviateError(`cannot 'deviate replace' default: target leaf-list '${String(node2.name)}' has no default`);
      }
      node2.defaults = [...values];
    } else {
      for (const value of values) {
        const idx = current.indexOf(value);
        if (idx < 0) {
          throw new DeviateError(
            `cannot 'deviate delete' default '${value}': target leaf-list '${String(node2.name)}' has no such default`
          );
        }
        current.splice(idx, 1);
      }
      node2.defaults = current;
    }
    return;
  }
  requireKind(node2, "default", ["leaf", "choice"]);
  if (values.length !== 1) {
    throw new DeviateError(`target ${String(node2.keyword)} '${String(node2.name)}' takes one default, got ${values.length}`);
  }
  const present = node2.default !== void 0 && node2.default !== null;
  if (deviate.kind === "delete") {
    if (!present || String(node2.default) !== values[0]) {
      throw new DeviateError(
        `cannot 'deviate delete' default '${values[0]}': target ${String(node2.keyword)} '${String(node2.name)}' has default ${present ? `'${String(node2.default)}'` : "None"}`
      );
    }
    delete node2.default;
    return;
  }
  single(node2, deviate, "default", present);
  node2.default = values[0];
}
function applyDeviateMusts(node2, deviate) {
  requireKind(node2, "must", MUST_NODES);
  const children2 = [...node2.statements];
  if (deviate.kind === "add") {
    node2.statements = [...children2, ...deviate.must.map((m) => new YangStatement(m))];
    return;
  }
  for (const must of deviate.must) {
    const idx = children2.findIndex((c) => c.keyword === "must" && c.argument === must.argument);
    if (idx < 0) {
      throw new DeviateError(
        `cannot 'deviate delete' must '${String(must.argument)}': target ${String(node2.keyword)} '${String(node2.name)}' has no such must`
      );
    }
    children2.splice(idx, 1);
  }
  node2.statements = children2;
}
function applyDeviateUnique(node2, deviate) {
  requireKind(node2, "unique", ["list"]);
  const current = Array.isArray(node2.unique) ? node2.unique.map((u) => [...u]) : [];
  if (deviate.kind === "add") {
    node2.unique = [...current, ...deviate.unique.map((u) => [...u])];
    return;
  }
  for (const paths of deviate.unique) {
    const idx = current.findIndex((u) => u.length === paths.length && u.every((p, i) => p === paths[i]));
    if (idx < 0) {
      throw new DeviateError(
        `cannot 'deviate delete' unique '${paths.join(" ")}': target list '${String(node2.name)}' has no such unique`
      );
    }
    current.splice(idx, 1);
  }
  node2.unique = current;
}
function applyDeviate(node2, deviate) {
  if (deviate.config !== void 0) {
    requireKind(node2, "config", CONFIG_NODES);
    single(node2, deviate, "config", typeof node2.config === "boolean", true);
    node2.config = deviate.config;
  }
  if (deviate.mandatory !== void 0) {
    requireKind(node2, "mandatory", ["leaf", "choice", "anydata", "anyxml"]);
    single(node2, deviate, "mandatory", node2.mandatory === true, true);
    node2.mandatory = deviate.mandatory;
  }
  if (deviate.min_elements !== void 0) {
    requireKind(node2, "min-elements", ["list", "leaf-list"]);
    single(node2, deviate, "min-elements", typeof node2.min_elements === "number", true);
    node2.min_elements = deviate.min_elements;
  }
  if (deviate.max_elements_set) {
    requireKind(node2, "max-elements", ["list", "leaf-list"]);
    single(node2, deviate, "max-elements", typeof node2.max_elements === "number", true);
    if (deviate.max_elements === void 0) {
      delete node2.max_elements;
    } else {
      node2.max_elements = deviate.max_elements;
    }
  }
  if (deviate.type !== void 0) {
    requireKind(node2, "type", ["leaf", "leaf-list"]);
    node2.type = deviate.type;
  }
  if (deviate.units !== void 0) {
    requireKind(node2, "units", ["leaf", "leaf-list"]);
    const units = typeof node2.units === "string" ? node2.units : "";
    if (deviate.kind === "delete") {
      if (units !== deviate.units) {
        throw new DeviateError(
          `cannot 'deviate delete' units '${deviate.units}': target ${String(node2.keyword)} '${String(node2.name)}' has units '${units}'`
        );
      }
      delete node2.units;
    } else {
      single(node2, deviate, "units", units !== "");
      node2.units = deviate.units;
    }
  }
  if (deviate.defaults.length > 0) {
    applyDeviateDefaults(node2, deviate);
  }
  if (deviate.must.length > 0) {
    applyDeviateMusts(node2, deviate);
  }
  if (deviate.unique.length > 0) {
    applyDeviateUnique(node2, deviate);
  }
}
function applyDeviation(ctxModule, dev, copies) {
  const path = String(dev.deviation_path ?? dev.argument ?? "");
  const stored = dev.deviation_path_segments;
  const segments = Array.isArray(stored) && stored.length > 0 ? stored : parseAbsoluteSchemaPath(path);
  let located;
  try {
    located = walkAbsoluteSchemaPath({
      ctxModule,
      path,
      segments,
      kind: "deviation",
      findToplevel: findToplevelSchemaChild,
      file: sourceFileOf(dev)
    });
  } catch (err) {
    if (err instanceof YangSyntaxError) {
      throw new YangSemanticError(err.message);
    }
    throw err;
  }
  const owner = resolvePrefixedModule(ctxModule, segments[0].prefix, sourceFileOf(dev));
  if (!owner) {
    throw new YangSemanticError(`deviation: unknown prefix '${segments[0].prefix}' in path '${path}'`);
  }
  let node2 = located.node;
  if (owner === ctxModule) {
    if (dev.not_supported === true) {
      removeSchemaChild(located.parent, node2);
      return;
    }
  } else {
    const { parent: parent2, index } = copiedPathToTarget(privateTargetModule(ctxModule, owner, copies), segments);
    if (dev.not_supported === true) {
      parent2.statements.splice(index, 1);
      return;
    }
    node2 = cowStatement(parent2.statements[index]);
    parent2.statements[index] = node2;
  }
  const deviates = dev.deviates ?? [];
  for (const deviate of deviates) {
    try {
      applyDeviate(node2, deviate);
    } catch (err) {
      if (err instanceof DeviateError) {
        throw new YangSemanticError(`deviation '${path}': ${err.message}`);
      }
      throw err;
    }
  }
}
function applyDeviations(module) {
  const data = module;
  const statements = asStatements2(data.statements);
  const deviations = statements.filter((s) => s.keyword === "deviation");
  const copies = /* @__PURE__ */ new Map();
  for (const dev of deviations) {
    applyDeviation(data, dev, copies);
  }
  if (deviations.length > 0) {
    data.statements = statements.filter((s) => s.keyword !== "deviation");
  }
  return module;
}
function stampDefiningModule(stmt, moduleName2) {
  stmt.defining_module = moduleName2;
  for (const child2 of asStatements2(stmt.statements)) {
    stampDefiningModule(child2, moduleName2);
  }
}
function mergeIfFeaturesFromAugment(aug, child2) {
  const ufs = aug.if_features;
  if (!Array.isArray(ufs) || ufs.length === 0) {
    return;
  }
  const existing = Array.isArray(child2.if_features) ? child2.if_features : [];
  child2.if_features = [...ufs, ...existing];
}
function mergeAugmentIntoTarget(aug, target, sourceModuleName) {
  const copies = asStatements2(aug.statements).map((x) => deepCloneStatement2(x));
  for (const c of copies) {
    stampDefiningModule(c, sourceModuleName);
    mergeIfFeaturesFromAugment(aug, c);
    mergeParentWhen(aug, c);
  }
  const targetChildren = asStatements2(target.statements);
  for (const c of copies) {
    targetChildren.push(c);
  }
  target.statements = targetChildren;
}
function applyAugments(module) {
  const statements = asStatements2(module.statements);
  const augments = statements.filter((s) => s.keyword === "augment");
  if (augments.length === 0) {
    return module;
  }
  augments.sort((a, b) => augmentSegmentCount(a) - augmentSegmentCount(b));
  const sourceName = String(module.name ?? "");
  for (const aug of augments) {
    const path = String(aug.augment_path ?? aug.argument ?? "");
    const target = resolveAugmentTarget(module, path, aug);
    mergeAugmentIntoTarget(aug, target, sourceName);
  }
  module.statements = statements.filter((s) => s.keyword !== "augment");
  return module;
}

// ts/src/transform/uses-expand.ts
function deepCloneStatement3(stmt) {
  return new YangStatement(JSON.parse(JSON.stringify(stmt)));
}
function cloneStatementShell(stmt) {
  const copy = {};
  for (const key2 of Object.keys(stmt)) {
    const value = stmt[key2];
    if (key2 === "statements" && Array.isArray(value) && value.length > 0) {
      copy[key2] = value;
      continue;
    }
    const text = JSON.stringify(value);
    if (text !== void 0) {
      copy[key2] = JSON.parse(text);
    }
  }
  const shell = new YangStatement(copy);
  const shared = copy.statements;
  if (Array.isArray(shared) && shared.length > 0) {
    shell.statements = shared;
  }
  return shell;
}
function modulePrefix(moduleData) {
  if (!moduleData) {
    return void 0;
  }
  const prefix = String(moduleData.prefix ?? "").replace(/^['"]|['"]$/g, "");
  return prefix.length > 0 ? prefix : void 0;
}
function asGroupingMap(value) {
  if (!value || typeof value !== "object") {
    return {};
  }
  return value;
}
function asImportMap(value) {
  if (!value || typeof value !== "object") {
    return {};
  }
  return value;
}
function usesGroupingRef(usesStmt) {
  if (typeof usesStmt.grouping_name !== "string" || !usesStmt.grouping_name) {
    return void 0;
  }
  const name = usesStmt.grouping_name;
  const prefix = typeof usesStmt.grouping_prefix === "string" && usesStmt.grouping_prefix ? usesStmt.grouping_prefix : void 0;
  return prefix ? { prefix, name } : { name };
}
function resolveGrouping(ref, scope, file) {
  const key2 = formatIdentifierRef(ref);
  if (!ref.name) {
    throw new YangSemanticError("Empty grouping name in uses");
  }
  if (ref.prefix) {
    if (scope.prefix && ref.prefix === scope.prefix) {
      const grouping3 = scope.groupings[ref.name];
      if (!grouping3) {
        throw new YangSemanticError(`Unknown grouping '${key2}'`);
      }
      return { key: key2, grouping: grouping3, nestedScope: scope };
    }
    const view = {
      prefix: scope.prefix,
      import_prefixes: scope.import_prefixes,
      file_imports: scope.file_imports
    };
    const imp = resolvePrefixedModule(view, ref.prefix, file);
    if (!imp) {
      throw new YangSemanticError(`Unknown import prefix '${ref.prefix}' in uses '${key2}'`);
    }
    const groupings = asGroupingMap(imp.groupings);
    const grouping2 = groupings[ref.name];
    if (!grouping2) {
      throw new YangSemanticError(`Unknown grouping '${key2}'`);
    }
    return {
      key: key2,
      grouping: grouping2,
      nestedScope: {
        groupings,
        import_prefixes: asImportMap(imp.import_prefixes),
        file_imports: imp.file_imports,
        prefix: modulePrefix(imp)
      }
    };
  }
  const grouping = scope.groupings[ref.name];
  if (!grouping) {
    throw new YangSemanticError(`Unknown grouping '${key2}'`);
  }
  return { key: key2, grouping, nestedScope: scope };
}
function mergeIfFeaturesFromParentUses(usesStmt, child2) {
  const ufs = usesStmt.if_features;
  if (!Array.isArray(ufs) || ufs.length === 0) {
    return;
  }
  const existing = Array.isArray(child2.if_features) ? child2.if_features : [];
  child2.if_features = [...ufs, ...existing];
}
function mergeXPathPrefixes(a, b) {
  if (!a || !b) return a ?? b;
  for (const [prefix, module] of Object.entries(b)) {
    if (a[prefix] !== void 0 && a[prefix] !== module) {
      throw new YangSemanticError(
        `uses: 'when' joins expressions that bind prefix '${prefix}' to '${a[prefix]}' and '${module}'`
      );
    }
  }
  return { ...a, ...b };
}
function mergeWhenFromParentUses(usesStmt, child2) {
  mergeParentWhen(usesStmt, child2, (existing, usesWhen) => {
    const prefixes = mergeXPathPrefixes(
      existing.xpath_prefixes,
      usesWhen.xpath_prefixes
    );
    return prefixes ? { xpath_prefixes: prefixes } : {};
  });
}
function findNodeByNameDepthFirst(nodes, name) {
  for (const n of nodes) {
    if (n.name === name) {
      return n;
    }
  }
  for (const n of nodes) {
    const hit = findNodeByNameDepthFirst(n.statements ?? [], name);
    if (hit) {
      return hit;
    }
  }
  return void 0;
}
function findRefineTarget(nodes, segments) {
  if (segments.length === 0) {
    return void 0;
  }
  const [head, ...rest] = segments;
  const found = findNodeByNameDepthFirst(nodes, head);
  if (!found) {
    return void 0;
  }
  if (rest.length === 0) {
    return found;
  }
  return findRefineTarget(found.statements ?? [], rest);
}
var SCHEMA_WALK = /* @__PURE__ */ new Set([
  "container",
  "list",
  "leaf",
  "leaf-list",
  "choice",
  "case",
  "anydata",
  "anyxml",
  "notification",
  "rpc",
  "action",
  "input",
  "output"
]);
function isWalkable(stmt) {
  return typeof stmt.keyword === "string" && SCHEMA_WALK.has(stmt.keyword);
}
function statementChildren(stmt) {
  const kids = stmt.statements ?? [];
  if (stmt.keyword === "choice") {
    const out = [];
    for (const caseStmt of kids) {
      if (caseStmt.keyword !== "case") {
        continue;
      }
      for (const child2 of caseStmt.statements ?? []) {
        if (isWalkable(child2)) {
          out.push(child2);
        }
      }
    }
    return out;
  }
  return kids.filter(isWalkable);
}
function casesOf(stmt) {
  if (stmt.keyword !== "choice") {
    return [];
  }
  return (stmt.statements ?? []).filter((child2) => child2.keyword === "case");
}
function findFromNode(stmt, segments, idx) {
  const want = segments[idx];
  const last = idx === segments.length - 1;
  if (stmt.name === want && isWalkable(stmt)) {
    if (last) {
      return [stmt];
    }
    if (stmt.keyword === "choice" && idx + 1 < segments.length) {
      const caseName = segments[idx + 1];
      const matches3 = [];
      for (const caseStmt of casesOf(stmt)) {
        if (caseStmt.name !== caseName) {
          continue;
        }
        if (idx + 1 === segments.length - 1) {
          return [caseStmt];
        }
        for (const child2 of statementChildren(caseStmt)) {
          matches3.push(...findFromNode(child2, segments, idx + 2));
        }
      }
      return matches3;
    }
    const matches2 = [];
    for (const child2 of statementChildren(stmt)) {
      matches2.push(...findFromNode(child2, segments, idx + 1));
    }
    return matches2;
  }
  if (stmt.keyword === "choice") {
    const matches2 = [];
    let named = false;
    for (const caseStmt of casesOf(stmt)) {
      if (caseStmt.name !== want) {
        continue;
      }
      named = true;
      if (last) {
        return [caseStmt];
      }
      for (const child2 of statementChildren(caseStmt)) {
        matches2.push(...findFromNode(child2, segments, idx + 1));
      }
    }
    if (named) {
      return matches2;
    }
  }
  const matches = [];
  for (const child2 of statementChildren(stmt)) {
    matches.push(...findFromNode(child2, segments, idx));
  }
  return matches;
}
function findNodesByAugmentPath(nodes, segments) {
  const out = [];
  for (const root of nodes) {
    if (!isWalkable(root)) {
      continue;
    }
    out.push(...findFromNode(root, segments, 0));
  }
  return out;
}
function augmentPathSegments(path) {
  const raw = path.trim().replace(/^['"]|['"]$/g, "");
  if (!raw || raw.startsWith("/") || raw.includes("[") || raw.includes(" ")) {
    throw new YangSyntaxError(`invalid augment path '${raw}'`);
  }
  const parts = raw.split("/");
  if (parts.some((part) => part.trim() === "")) {
    throw new YangSyntaxError(`invalid augment path '${raw}'`);
  }
  return parts.map((part) => {
    const trimmed = part.trim();
    const colon = trimmed.indexOf(":");
    return colon >= 0 ? trimmed.slice(colon + 1) : trimmed;
  });
}
function applyAugmentsFromUses(usesStmt, body) {
  const augmentations = usesStmt.augmentations;
  if (!Array.isArray(augmentations) || augmentations.length === 0) {
    return;
  }
  const groupingName = typeof usesStmt.argument === "string" && usesStmt.argument || typeof usesStmt.grouping_name === "string" && usesStmt.grouping_name || "uses";
  for (const aug of augmentations) {
    const path = String(aug.path ?? aug.augment_path ?? aug.argument ?? "");
    let segments;
    try {
      segments = augmentPathSegments(path);
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      throw new YangSyntaxError(`uses '${groupingName}' augment: invalid path '${path}': ${detail}`);
    }
    const targets = findNodesByAugmentPath(body, segments);
    if (targets.length === 0) {
      throw new YangSyntaxError(`uses '${groupingName}' augment: no target for path '${path}'`);
    }
    if (targets.length !== 1) {
      throw new YangSyntaxError(
        `uses '${groupingName}' augment: path '${path}' matched ${targets.length} nodes, expected one`
      );
    }
    const target = targets[0];
    if (!Array.isArray(target.statements)) {
      throw new YangSyntaxError(
        `uses '${groupingName}' augment: target '${target.name ?? "?"}' cannot contain schema substatements (path '${path}')`
      );
    }
    const copies = (aug.statements ?? []).map((stmt) => deepCloneStatement3(stmt));
    for (const copy of copies) {
      mergeIfFeaturesFromParentUses(aug, copy);
      mergeWhenFromParentUses(aug, copy);
    }
    target.statements = [...target.statements, ...copies];
  }
}
function applyRefinesFromUses(usesStmt, expanded) {
  const refines = usesStmt.refines;
  if (!Array.isArray(refines) || refines.length === 0) {
    return;
  }
  for (const rf of refines) {
    const pathRaw = rf.refine_target_path ?? rf.argument ?? "";
    const segments = pathRaw.split("/").map((s) => s.trim()).filter(Boolean);
    if (segments.length === 0) {
      continue;
    }
    const target = findRefineTarget(expanded, segments);
    if (!target) {
      throw new YangRefineTargetNotFoundError(pathRaw);
    }
    if (typeof rf.min_elements === "number") {
      target.min_elements = rf.min_elements;
    }
    if (typeof rf.max_elements === "number") {
      target.max_elements = rf.max_elements;
    }
    if (typeof rf.refined_mandatory === "boolean") {
      target.mandatory = rf.refined_mandatory;
    }
    if (typeof rf.refined_config === "boolean") {
      target.config = rf.refined_config;
    }
    const refinedDefaults = rf.refined_defaults;
    if (Array.isArray(refinedDefaults) && refinedDefaults.length > 0) {
      if (target.keyword === YangTokenType.LEAF) {
        target.default = refinedDefaults[0];
      } else if (target.keyword === YangTokenType.LEAF_LIST) {
        target.defaults = [...refinedDefaults];
      }
    }
    const rif = rf.if_features;
    if (Array.isArray(rif) && rif.length > 0) {
      const cur = Array.isArray(target.if_features) ? target.if_features : [];
      target.if_features = [...rif, ...cur];
    }
    const refinedDesc = typeof rf.description === "string" ? rf.description.trim() : "";
    if (refinedDesc) {
      target.description = refinedDesc;
    }
    const extra = rf.statements ?? [];
    if (extra.length > 0) {
      target.statements = [...target.statements ?? [], ...extra.map((stmt) => deepCloneStatement3(stmt))];
    }
  }
}
function expandGroupingBody(ref, scope, stack, file) {
  const resolved = resolveGrouping(ref, scope, file);
  if (stack.includes(resolved.key)) {
    throw new YangCircularUsesError(stack, resolved.key);
  }
  const nextStack = [...stack, resolved.key];
  const rawChildren = resolved.grouping.statements ?? [];
  const flattened = [];
  for (const child2 of rawChildren) {
    if (child2.keyword === "uses") {
      const childRef = usesGroupingRef(child2);
      if (!childRef) {
        continue;
      }
      const body = expandGroupingBody(childRef, resolved.nestedScope, nextStack, child2.included_from);
      applyAugmentsFromUses(child2, body);
      applyRefinesFromUses(child2, body);
      for (const stmt of body) {
        mergeIfFeaturesFromParentUses(child2, stmt);
        mergeWhenFromParentUses(child2, stmt);
        flattened.push(deepCloneStatement3(stmt));
      }
    } else {
      flattened.push(deepCloneStatement3(child2));
    }
  }
  const withoutTypedefs = flattened.filter((stmt) => stmt.keyword !== "typedef");
  return withoutTypedefs.map((stmt) => expandUsesUnderStatement(stmt, resolved.nestedScope, nextStack));
}
function scopeWithLocalGroupings(stmt, scope) {
  const local2 = stmt.local_groupings;
  if (!local2 || Object.keys(local2).length === 0) {
    return scope;
  }
  return { ...scope, groupings: { ...scope.groupings, ...local2 } };
}
function expandUsesUnderStatement(stmt, scope, stack) {
  const next = scopeWithLocalGroupings(stmt, scope);
  if (stmt.statements?.length) {
    stmt.statements = expandStatementList(stmt.statements, next, stack);
  }
  return stmt;
}
function expandStatementList(statements, scope, stack) {
  const out = [];
  for (const stmt of statements) {
    if (stmt.keyword === "uses") {
      const ref = usesGroupingRef(stmt);
      if (!ref) {
        continue;
      }
      const expanded = expandGroupingBody(ref, scope, stack, stmt.included_from);
      applyAugmentsFromUses(stmt, expanded);
      applyRefinesFromUses(stmt, expanded);
      for (const e of expanded) {
        mergeIfFeaturesFromParentUses(stmt, e);
        mergeWhenFromParentUses(stmt, e);
        out.push(expandUsesUnderStatement(e, scope, stack));
      }
    } else {
      out.push(expandUsesUnderStatement(cloneStatementShell(stmt), scope, stack));
    }
  }
  return out;
}
function expandUses(module) {
  const sharedImports = module.import_prefixes;
  const cloned = deepClone({
    name: module.name,
    yang_version: module.yang_version,
    namespace: module.namespace,
    prefix: module.prefix,
    organization: module.organization,
    contact: module.contact,
    description: module.description,
    typedefs: module.typedefs,
    identities: module.identities,
    extension_runtime: module.extension_runtime,
    groupings: module.groupings,
    statements: module.statements
  });
  cloned.import_prefixes = sharedImports;
  cloned.file_imports = module.file_imports;
  cloned.extensions = { ...module.extensions };
  cloned.features = new Set(module.features);
  cloned.feature_if_features = { ...module.feature_if_features };
  const expandScope = {
    groupings: asGroupingMap(cloned.groupings),
    import_prefixes: sharedImports,
    file_imports: module.file_imports,
    prefix: modulePrefix(module)
  };
  const top = cloned.statements ?? [];
  cloned.statements = expandStatementList(top, expandScope, []);
  for (const g of Object.values(expandScope.groupings)) {
    if (!g.statements?.length) continue;
    g.statements = expandStatementList(g.statements, expandScope, []);
  }
  return new YangModule(cloned, module.source);
}

// ts/src/validator/semantic-validation.ts
function iterStatements(statements) {
  const out = [];
  for (const stmt of statements ?? []) {
    out.push(stmt);
    out.push(...iterStatements(stmt.statements));
  }
  return out;
}
function validateListKeyConstraints(module) {
  for (const stmt of iterStatements(module.statements)) {
    if (stmt.keyword !== "list" || typeof stmt.key !== "string" || stmt.key.trim() === "") {
      continue;
    }
    const keyLeaves = new Map(
      (stmt.statements ?? []).filter((child2) => child2.keyword === "leaf" && typeof child2.name === "string").map((child2) => [child2.name, child2])
    );
    for (const keyName of stmt.key.split(/\s+/).filter(Boolean)) {
      const child2 = keyLeaves.get(keyName);
      if (child2 === void 0) {
        throw new YangSemanticError(
          `List '${stmt.name ?? ""}': key leaf '${keyName}' does not exist (RFC 7950: each list key name must refer to a child leaf).`
        );
      }
      let illegal;
      if (child2.when !== void 0) {
        illegal = "when";
      } else if (Array.isArray(child2.if_features) && child2.if_features.length > 0) {
        illegal = "if-feature";
      }
      if (illegal === void 0) {
        continue;
      }
      throw new YangSemanticError(
        `List '${stmt.name ?? ""}': key leaf '${child2.name}' must not have '${illegal}' (RFC 7950: 'when' and 'if-feature' are illegal on list keys).`
      );
    }
  }
}
function validateSemantics(module) {
  validateListKeyConstraints(module);
  const checkType = (type, stack = /* @__PURE__ */ new Set()) => {
    if (!type) return;
    if (type.prefix || !Object.prototype.hasOwnProperty.call(REGISTRY, String(type.name))) {
      const td = resolveTypedef(module, type);
      if (!td) throw new YangSemanticError(`Unknown typedef '${type.name}' in lexical scope`);
      if (stack.has(td)) throw new YangSemanticError(`Circular typedef '${type.name}'`);
      checkType(td.type, /* @__PURE__ */ new Set([...stack, td]));
    }
    for (const member of type.types ?? []) checkType(member, stack);
  };
  for (const td of Object.values(module.typedefs)) checkType(td.type);
  for (const stmt of iterStatements(module.statements)) checkType(stmt.type);
}

// ts/src/parser/yang-parser.ts
function serializeIdentities(raw) {
  const out = {};
  if (!raw) {
    return out;
  }
  for (const [name, stmt] of Object.entries(raw)) {
    const bases = Array.isArray(stmt.bases) ? stmt.bases.map((b) => coerceIdentifierRef(b)).filter((b) => Boolean(b)) : [];
    const features = Array.isArray(stmt.if_features) ? stmt.if_features.filter((x) => typeof x === "string" && x.length > 0) : [];
    out[name] = {
      bases,
      ...typeof stmt.description === "string" && stmt.description.length > 0 ? { description: stmt.description } : {},
      ...features.length > 0 ? { if_features: features } : {}
    };
  }
  return out;
}
function buildModuleData(root, moduleState, serialize) {
  if (root.keyword !== "module") {
    throw new YangSemanticError("Only 'module' roots are currently supported by TS parser");
  }
  const statements = root.statements ?? [];
  const typedefs = {};
  for (const [key2, raw] of Object.entries(moduleState.typedefs ?? {})) {
    const stmt = serialize(raw);
    typedefs[key2] = { ...stmt, name: stmt.name, scope: stmt.scope };
  }
  const features = moduleState.features;
  const featureIfFeatures = moduleState.feature_if_features;
  const moduleDescriptionStmt = statements.find((stmt) => stmt.keyword === "description");
  const moduleDescription = typeof moduleDescriptionStmt?.argument === "string" ? moduleDescriptionStmt.argument : "";
  return {
    name: root.argument,
    yang_version: statements.find((stmt) => stmt.keyword === "yang-version")?.argument ?? "1.1",
    namespace: statements.find((stmt) => stmt.keyword === "namespace")?.argument ?? "",
    prefix: statements.find((stmt) => stmt.keyword === "prefix")?.argument ?? "",
    organization: String(moduleState.organization ?? ""),
    contact: String(moduleState.contact ?? ""),
    description: moduleDescription,
    typedefs,
    identities: serializeIdentities(moduleState.identities),
    import_prefixes: moduleState.import_prefixes ?? {},
    file_imports: moduleState.file_imports ?? {},
    extensions: moduleState.extensions ?? {},
    extension_runtime: moduleState.extension_runtime ?? {},
    features: features instanceof Set ? new Set(features) : /* @__PURE__ */ new Set(),
    feature_if_features: featureIfFeatures && typeof featureIfFeatures === "object" ? { ...featureIfFeatures } : {},
    statements
  };
}
var YangParser = class {
  expandUses;
  includePath;
  moduleCache = /* @__PURE__ */ new Map();
  /** Every module this parser loaded, by name; shared as each module's `module_registry`. */
  modulesByName = {};
  tokenizer = new YangTokenizer();
  includeStack = [];
  parsers = new StatementParsers({
    importResolver: (moduleName2, _localPrefix, revisionDate, context, tokens) => this.resolveImport(moduleName2, revisionDate, context, tokens),
    includeResolver: (submoduleName, revisionDate, context, tokens) => this.resolveInclude(submoduleName, revisionDate, context, tokens)
  });
  constructor(options = {}) {
    this.expandUses = options.expandUses ?? true;
    this.includePath = (options.includePath ?? []).map((p) => resolve(p));
  }
  /** Resolve `import` / `include` like Python `YangParser._resolve_module_file`. */
  resolveImportedModulePath(moduleBasename, revisionDate, sourceDir, kind = "module") {
    const trimmedRev = revisionDate?.trim();
    const candidates = [];
    if (trimmedRev) {
      candidates.push(`${moduleBasename}@${trimmedRev}.yang`);
    }
    candidates.push(`${moduleBasename}.yang`);
    const dirs = sourceDir ? [sourceDir, ...this.includePath] : [...this.includePath];
    if (typeof process !== "undefined" && process.versions?.node && import.meta.url) {
      dirs.push(resolve(dirname(fileURLToPath(import.meta.url)), "shared"));
    }
    for (const start of [sourceDir, "."]) {
      if (!start) continue;
      let ancestor = resolve(start);
      while (true) {
        const shared = resolve(ancestor, "shared");
        if (existsSync(shared) && !dirs.includes(shared)) dirs.push(shared);
        const parent2 = dirname(ancestor);
        if (parent2 === ancestor) break;
        ancestor = parent2;
      }
    }
    let found;
    for (const dir of dirs) {
      for (const c of candidates) {
        const p = resolve(dir, c);
        if (existsSync(p)) {
          found = p;
          break;
        }
      }
      if (found) {
        break;
      }
    }
    if (!found) {
      for (const dir of dirs) {
        let matches = [];
        try {
          matches = readdirSync(dir).filter((f) => f.startsWith(`${moduleBasename}@`) && f.endsWith(".yang"));
        } catch {
          matches = [];
        }
        if (matches.length > 0) {
          matches.sort();
          found = resolve(dir, matches[matches.length - 1]);
          break;
        }
      }
    }
    if (!found) {
      const tried = `[${candidates.map((c) => `'${c}'`).join(", ")}]`;
      throw new YangSemanticError(
        `Could not find ${kind} '${moduleBasename}' (tried filenames ${tried}) under [${dirs.join(", ")}]`
      );
    }
    const expected = trimmedRev ? `${moduleBasename}@${trimmedRev}.yang` : void 0;
    const foundName = found.slice(Math.max(found.lastIndexOf("/"), found.lastIndexOf("\\")) + 1);
    if (expected && foundName !== expected) {
      const statement = kind === "module" ? "import" : "include";
      console.warn(
        `${statement} '${moduleBasename}' revision-date ${trimmedRev} not found; using ${foundName}`
      );
    }
    return found;
  }
  sourceDirFromContext(context) {
    const sourcePath = context.module.__source_path;
    return sourcePath ? dirname(sourcePath) : void 0;
  }
  resolveImport(moduleName2, revisionDate, context, _tokens) {
    const sourceDir = this.sourceDirFromContext(context);
    if (!sourceDir && this.includePath.length === 0) {
      throw new YangSemanticError(
        "import requires a filesystem location: use parseYangFile(), or parseYangString(... from a file-backed source)"
      );
    }
    const filePath = this.resolveImportedModulePath(moduleName2, revisionDate, sourceDir, "module");
    return this.parseFile(filePath);
  }
  /**
   * Load an included submodule into the parent's parser context (Python
   * ``merge_included_submodule``). Definitions land on the parent; ``belongs-to``,
   * duplicate names, and circular includes use Python's messages.
   */
  resolveInclude(submoduleName, revisionDate, context, _tokens) {
    const module = context.module;
    const sourceDir = this.sourceDirFromContext(context);
    if (!sourceDir && this.includePath.length === 0) {
      throw new YangSemanticError(
        "include requires a filesystem location for the submodule: use parseYangFile(), or parseYangString(... from a file-backed source)"
      );
    }
    const path = this.resolveImportedModulePath(submoduleName, revisionDate, sourceDir, "submodule");
    if (this.includeStack.includes(path)) {
      throw new YangSyntaxError(`Circular submodule include: ${path}`, { filename: path });
    }
    this.includeStack.push(path);
    const fileImports = module.file_imports ??= {};
    fileImports[submoduleName] = {};
    const saved = snapshotModuleHeader(module);
    const releaseGuards = guardIncludeDefinitions(module, submoduleName);
    const previousInclude = this.parsers.includingSubmoduleName;
    this.parsers.includingSubmoduleName = submoduleName;
    const savedSource = module.__source_path;
    module.__source_path = path;
    let subName = "";
    let belongs = "";
    try {
      const content = readFileSync(path, "utf-8");
      const stream = this.tokenizer.tokenize(content, path);
      if (!stream.has_more() || stream.peek() !== "submodule") {
        const got = stream.has_more() ? stream.peek() : "";
        throw new YangSemanticError(
          `submodule file defines name '${got}', include expects '${submoduleName}'`
        );
      }
      this.parsers.parseSubmodule(stream, context);
      subName = String(module.name ?? "");
      belongs = String(module.belongs_to_module ?? "");
    } finally {
      module.__source_path = savedSource;
      this.parsers.includingSubmoduleName = previousInclude;
      releaseGuards();
      restoreModuleHeader(module, saved);
      this.includeStack.pop();
    }
    if (subName !== submoduleName) {
      throw new YangSemanticError(
        `submodule file defines name '${subName}', include expects '${submoduleName}'`
      );
    }
    const parentName = String(saved.name ?? "");
    const owner = String(saved.belongs_to_module ?? "") || parentName;
    if (belongs && belongs !== owner) {
      throw new YangSemanticError(
        `submodule belongs-to '${belongs}' does not match module '${owner}'`
      );
    }
  }
  parseTokenStream(stream, source, sourceDir) {
    const moduleState = {
      name: "",
      yang_version: "1.1",
      namespace: "",
      prefix: "",
      organization: "",
      contact: "",
      revisions: [],
      belongs_to_module: "",
      typedefs: {},
      identities: {},
      groupings: {},
      features: /* @__PURE__ */ new Set(),
      feature_if_features: {},
      import_prefixes: {},
      file_imports: {},
      extensions: {},
      extension_runtime: {},
      __source_path: source.kind === "file" ? source.value : sourceDir ? resolve(sourceDir, "memory.yang") : void 0,
      statements: []
    };
    const context = new ParserContext({ module: moduleState, current_parent: {} });
    const root = this.parsers.parseModule(stream, context);
    const data = buildModuleData(root, moduleState, (stmt) => this.parsers.serializeAstStatement(stmt));
    const rawGroupings = moduleState.groupings ?? {};
    const serializedGroupings = {};
    for (const [key2, val] of Object.entries(rawGroupings)) {
      if (!val || typeof val !== "object") {
        continue;
      }
      const g = val;
      const gname = g.name ?? key2;
      serializedGroupings[key2] = new YangStatement({
        keyword: "grouping",
        name: gname,
        argument: gname,
        statements: (g.statements ?? []).map((ch) => this.parsers.serializeAstStatement(ch))
      });
    }
    if (Object.keys(serializedGroupings).length > 0) {
      data.groupings = serializedGroupings;
    }
    const rawIdentities = moduleState.identities ?? {};
    const serializedIdentities = data.identities ?? {};
    for (const [name, raw] of Object.entries(rawIdentities)) {
      const invocations = (raw.statements ?? []).map((child2) => this.parsers.serializeAstStatement(child2)).filter((stmt) => typeof stmt.resolved_extension_name === "string" && stmt.resolved_extension_name.length > 0);
      if (invocations.length > 0 && serializedIdentities[name]) {
        serializedIdentities[name].statements = invocations;
      }
    }
    let mod = new YangModule(data, source);
    Object.defineProperty(mod, "module_registry", { value: this.modulesByName, enumerable: false });
    propagateTypedefUnits(data, mod);
    if (this.expandUses) {
      mod = expandUses(mod);
      mod = applyAugments(mod);
      mod = applyDeviations(mod);
      if (!mod.module_registry) Object.defineProperty(mod, "module_registry", { value: this.modulesByName, enumerable: false });
      applyBuiltinExtensionInvocations(mod);
      validateSemantics(mod);
    }
    if (mod.name) {
      this.modulesByName[mod.name] = mod;
    }
    Object.defineProperty(mod, "module_registry", { value: this.modulesByName, enumerable: false });
    return mod;
  }
  /**
   * @param sourceDir Directory searched before `includePath` for `import` / `include`.
   *   `parseYangString` passes `dirname(sourcePath)`.
   */
  parseString(content, sourceName = "<memory>", sourceDir) {
    const stream = this.tokenizer.tokenize(content, sourceName);
    const source = { kind: "string", value: content, name: sourceName };
    return this.parseTokenStream(stream, source, sourceDir);
  }
  parseFile(path) {
    const absolute = resolve(path);
    const cached = this.moduleCache.get(absolute);
    if (cached) {
      return cached;
    }
    const content = readFileSync(absolute, "utf-8");
    const stream = this.tokenizer.tokenize(content, absolute);
    const source = { kind: "file", value: absolute, name: absolute };
    const tracked = this.includeStack.length === 0;
    if (tracked) {
      this.includeStack.push(absolute);
    }
    try {
      const module = this.parseTokenStream(stream, source);
      this.moduleCache.set(absolute, module);
      return module;
    } finally {
      if (tracked) {
        this.includeStack.pop();
      }
    }
  }
};
function snapshotModuleHeader(module) {
  const revisions = Array.isArray(module.revisions) ? module.revisions : void 0;
  return {
    name: module.name,
    yang_version: module.yang_version,
    namespace: module.namespace,
    prefix: module.prefix,
    organization: module.organization,
    contact: module.contact,
    belongs_to_module: module.belongs_to_module,
    revisionLen: revisions?.length ?? 0
  };
}
function restoreModuleHeader(module, saved) {
  module.name = saved.name;
  module.yang_version = saved.yang_version;
  module.namespace = saved.namespace;
  module.prefix = saved.prefix;
  module.organization = saved.organization;
  module.contact = saved.contact;
  module.belongs_to_module = saved.belongs_to_module;
  if (Array.isArray(module.revisions)) {
    module.revisions.length = saved.revisionLen;
  }
}
function propagateTypedefUnits(data, module) {
  const unitsOf = (type, seen) => {
    if (!type || typeof type.name !== "string" || !type.name) {
      return "";
    }
    const key2 = `${type.prefix ?? ""}:${type.name}`;
    if (seen.has(key2)) {
      return "";
    }
    seen.add(key2);
    const td = resolveTypedef(module, type);
    if (!td) {
      return "";
    }
    if (typeof td.units === "string" && td.units) {
      return td.units;
    }
    return unitsOf(td.type, seen);
  };
  const walk = (statements) => {
    for (const stmt of statements ?? []) {
      const keyword = stmt.keyword;
      if ((keyword === "leaf" || keyword === "leaf-list") && !stmt.units && stmt.type) {
        const found = unitsOf(stmt.type, /* @__PURE__ */ new Set());
        if (found) {
          stmt.units = found;
        }
      }
      if (Array.isArray(stmt.statements)) {
        walk(stmt.statements);
      }
      const local2 = stmt.local_groupings;
      if (local2) {
        for (const grouping of Object.values(local2)) {
          walk(grouping.statements);
        }
      }
    }
  };
  walk(data.statements);
  const groupings = data.groupings;
  if (groupings) {
    for (const grouping of Object.values(groupings)) {
      walk(grouping.statements);
    }
  }
}
function duplicateFromInclude(kind, name, subName) {
  return new YangSemanticError(`Duplicate ${kind} '${name}' from include of '${subName}'`);
}
function includeSources(module) {
  const existing = module.__included_def_sources;
  if (existing) {
    return existing;
  }
  const created = {
    typedefs: {},
    identities: {},
    groupings: {},
    feature_if_features: {},
    features: {}
  };
  module.__included_def_sources = created;
  return created;
}
function guardIncludeDefinitions(module, subName) {
  const sources = includeSources(module);
  const typedefs = module.typedefs ?? {};
  const identities = module.identities ?? {};
  const groupings = module.groupings ?? {};
  const featureIfFeatures = module.feature_if_features ?? {};
  module.typedefs = guardRecord(
    typedefs,
    (name) => duplicateFromInclude("typedef", name, subName),
    subName,
    sources.typedefs
  );
  module.identities = guardRecord(
    identities,
    (name) => duplicateFromInclude("identity", name, subName),
    subName,
    sources.identities
  );
  module.groupings = guardRecord(
    groupings,
    (name) => duplicateFromInclude("grouping", name, subName),
    subName,
    sources.groupings
  );
  module.feature_if_features = guardRecord(
    featureIfFeatures,
    (name) => duplicateFromInclude("feature if-feature for", name, subName),
    subName,
    sources.feature_if_features
  );
  const features = module.features instanceof Set ? module.features : /* @__PURE__ */ new Set();
  module.features = features;
  const originalAdd = features.add;
  features.add = ((value) => {
    if (features.has(value)) {
      if (sources.features[value] === subName) {
        return features;
      }
      throw duplicateFromInclude("feature", value, subName);
    }
    if (sources.features[value] === void 0) {
      sources.features[value] = subName;
    }
    return originalAdd.call(features, value);
  });
  return () => {
    module.typedefs = typedefs;
    module.identities = identities;
    module.groupings = groupings;
    module.feature_if_features = featureIfFeatures;
    features.add = originalAdd;
  };
}
function guardRecord(record, duplicate, subName, sources) {
  return new Proxy(record, {
    set(target, prop, value) {
      if (typeof prop === "string" && Object.hasOwn(target, prop)) {
        if (sources[prop] === subName) {
          return true;
        }
        throw duplicate(prop);
      }
      if (typeof prop === "string" && sources[prop] === void 0) {
        sources[prop] = subName;
      }
      target[prop] = value;
      return true;
    }
  });
}

// ts/src/parser/index.ts
function parseYangString(content, options = {}) {
  const parser = new YangParser({
    includePath: options.includePath,
    expandUses: options.expandUses
  });
  const sourceDir = options.sourcePath ? dirname(options.sourcePath) : void 0;
  return parser.parseString(content, options.filename ?? "<memory>", sourceDir);
}

// ts/src/encoding/annotation-families.ts
var ANNOTATION_FAMILIES = {
  "jsonld": {
    "prefix": "@",
    "pattern": "^@[A-Za-z]+$"
  },
  "json_schema": {
    "prefix": "$",
    "pattern": "^\\$[A-Za-z]+$"
  }
};

// ts/src/encoding/annotations.ts
function isAnnotation(key2, options = {}) {
  return Object.keys(ANNOTATION_FAMILIES).some((family) => {
    const enabled = family === "jsonld" ? options.allowJsonld !== false : options.allowJsonSchema !== false;
    return enabled && new RegExp(ANNOTATION_FAMILIES[family].pattern).exec(key2)?.[0] === key2;
  });
}
function annotateSchema(schema, options) {
  const patterns = Object.fromEntries(Object.entries(ANNOTATION_FAMILIES).filter(([family]) => family === "jsonld" ? options.allowJsonld !== false : options.allowJsonSchema !== false).map(([, value]) => [value.pattern, true]));
  if (Object.keys(patterns).length === 0) return;
  if (schema.type === "object" || schema.properties) {
    if (schema.maxProperties === 0) {
      delete schema.maxProperties;
      schema.properties = {};
      schema.additionalProperties = false;
    }
    schema.patternProperties = { ...patterns };
  }
  const visit = (value) => {
    if (value && typeof value === "object" && !Array.isArray(value)) annotateSchema(value, options);
  };
  for (const key2 of ["properties", "$defs"]) {
    for (const child2 of Object.values(schema[key2] ?? {})) visit(child2);
  }
  for (const key2 of ["items", "not", "additionalProperties"]) visit(schema[key2]);
  for (const key2 of ["oneOf", "anyOf", "allOf"]) for (const child2 of schema[key2] ?? []) visit(child2);
}

// ts/src/encoding/rfc7951.ts
var STRUCTURE_INDEX = "ietf-yang-structure-ext:structure-index";
function resolveStructureInstance(data, module) {
  const keys = Object.keys(data);
  if (keys.length !== 1) {
    return void 0;
  }
  const key2 = keys[0];
  const inner = data[key2];
  if (!inner || typeof inner !== "object" || Array.isArray(inner)) {
    return void 0;
  }
  let name = key2;
  if (key2.includes(":")) {
    const colon = key2.indexOf(":");
    const owner = key2.slice(0, colon);
    name = key2.slice(colon + 1);
    if (!owner || !name || owner !== (module.name ?? "")) {
      return void 0;
    }
  }
  const index = module.extension_runtime?.[STRUCTURE_INDEX];
  if (!index || typeof index !== "object") {
    return void 0;
  }
  const schema = index[name];
  if (!(schema instanceof YangStatement)) {
    return void 0;
  }
  return { schema, inner, key: key2 };
}
function resolveQualifiedTopLevel(jsonKey, modules) {
  if (!jsonKey.includes(":")) {
    return { statementName: null, moduleName: null };
  }
  const [moduleQualifier, statementName] = jsonKey.split(":", 2);
  if (!moduleQualifier || !statementName) {
    return { statementName: null, moduleName: null };
  }
  const mod = modules[moduleQualifier];
  if (!mod) {
    return { statementName: null, moduleName: null };
  }
  if (!mod.findStatement(statementName)) {
    return { statementName: null, moduleName: null };
  }
  return { statementName, moduleName: moduleQualifier };
}

// ts/src/encoding/instance.ts
var INT642 = QUOTED_INTEGER_NAMES;
var DECIMAL = DECIMAL_TYPE_NAMES;
var STRINGISH = STRINGISH_NAMES;
var SMALL_INT = /* @__PURE__ */ new Set([...NUMBER_INTEGER_NAMES, "integer"]);
var BUILTINS = /* @__PURE__ */ new Set([...Object.keys(REGISTRY), ...DECIMAL, "integer"]);
var INTEGER_KEY = /* @__PURE__ */ new Set([...INT642, ...SMALL_INT]);
var ENCODED = /* @__PURE__ */ new Set([...INT642, ...DECIMAL, "empty"]);
var INT_TEXT = /^-?\d+$/;
var DEC_TEXT = /^-?\d+(\.\d+)?$/;
var DATA = /* @__PURE__ */ new Set(["container", "list", "leaf", "leaf-list", "anydata", "anyxml", "notification"]);
var SKIP = /* @__PURE__ */ new Set(["rpc", "action", "input", "output"]);
var NO = /* @__PURE__ */ Symbol("no-decode");
function escapeToken(token) {
  if (token.indexOf("~") < 0 && token.indexOf("/") < 0) return token;
  return token.replace(/~/g, "~0").replace(/\//g, "~1");
}
function join(prefix, token) {
  return `${prefix}/${escapeToken(token)}`;
}
var walkCache = null;
function schemaKey(schema) {
  return schema;
}
function keywordOf(stmt) {
  const raw = stmt.keyword ?? "";
  if (raw === "notification") return "container";
  if (raw.includes(":")) {
    const kind = stmt.data_node_kind;
    if (kind === "container" || kind === "list") return kind;
  }
  return raw;
}
function isStructureSchema(stmt) {
  return stmt.resolved_module_name === "ietf-yang-structure-ext" && stmt.resolved_extension_name === "structure";
}
function definingModule2(stmt, parent2) {
  const explicit = stmt.defining_module;
  if (typeof explicit === "string" && explicit.length > 0) return explicit;
  return parent2;
}
function memberKey(stmt, parent2) {
  const name = stmt.name ?? "";
  if (!name) return "";
  const owner = definingModule2(stmt, parent2);
  return !parent2 || owner === parent2 ? name : `${owner}:${name}`;
}
function dataNodes(schema) {
  const cache2 = walkCache;
  if (!cache2) return collectDataNodes(schema);
  const key2 = schemaKey(schema);
  let found = cache2.nodes.get(key2);
  if (!found) {
    found = collectDataNodes(schema);
    cache2.nodes.set(key2, found);
  }
  return found;
}
function collectDataNodes(schema) {
  const out = [];
  for (const stmt of schema.statements ?? []) {
    const keyword = keywordOf(stmt);
    if (SKIP.has(stmt.keyword ?? "")) continue;
    if (keyword === "choice" || keyword === "case") {
      out.push(...collectDataNodes(stmt));
      continue;
    }
    if (DATA.has(keyword)) out.push(stmt);
  }
  return out;
}
function leafType(stmt) {
  const type = stmt.type;
  return type && typeof type === "object" ? type : void 0;
}
function unwrap(module, type) {
  if (!type) return type;
  const cache2 = walkCache;
  if (!cache2) return unwrapType(module, type, /* @__PURE__ */ new Set());
  if (cache2.unwrapped.has(type)) return cache2.unwrapped.get(type);
  const eff = unwrapType(module, type, /* @__PURE__ */ new Set());
  cache2.unwrapped.set(type, eff);
  return eff;
}
function unwrapType(module, type, seen) {
  if (!type || typeof type.name !== "string") return type;
  const name = type.name;
  if (!type.prefix && BUILTINS.has(name) || seen.has(type)) return type;
  const typedef = resolveTypedef(module, type);
  if (typedef?.type && typeof typedef.type.name === "string") {
    seen.add(type);
    return unwrapType(module, typedef.type, seen);
  }
  return type;
}
function accepts(checker, value, type) {
  const name = typeof type.name === "string" ? type.name : "string";
  return checker.validate(value, name, type).length === 0;
}
function isIntText(value) {
  return typeof value === "string" && INT_TEXT.test(value.trim());
}
function isDecText(value) {
  return typeof value === "string" && DEC_TEXT.test(value.trim());
}
function hint(native, kind) {
  return native ? `${kind} is a JSON number in native mode; the default is RFC 7951` : `${kind} is a string in RFC 7951; pass --native-json for a JSON number`;
}
function decodeScalar(value, type, module, checker, native) {
  const eff = unwrap(module, type);
  if (!eff || typeof eff.name !== "string") return value;
  const name = eff.name;
  if (name === "union") {
    const members = Array.isArray(eff.types) ? eff.types : [];
    for (const member of members) {
      const decoded = decodeScalar(value, member, module, checker, native);
      if (decoded === NO) continue;
      if (accepts(checker, decoded, member)) return decoded;
    }
    return value;
  }
  if (name === "empty") {
    if (native && value === null) return null;
    if (!native && Array.isArray(value) && value.length === 1 && value[0] === null) return null;
    if (native && Array.isArray(value) && value.length === 1 && value[0] === null || !native && value === null) {
      return NO;
    }
    return value;
  }
  if (INT642.has(name)) {
    if (native) {
      if (typeof value !== "number" || !Number.isSafeInteger(value)) return NO;
      return BigInt(value);
    }
    if (isIntText(value)) return BigInt(value.trim());
    return NO;
  }
  if (DECIMAL.has(name)) {
    if (native) {
      if (typeof value !== "number" || !Number.isFinite(value)) return NO;
      return new ExactDecimal(String(value));
    }
    if (isDecText(value)) return new ExactDecimal(value.trim());
    return NO;
  }
  if (name === "leafref" || STRINGISH.has(name)) return value;
  if (name === "boolean") {
    if (typeof value === "boolean" || value === "true" || value === "false") return value;
    return NO;
  }
  return value;
}
function resolveCached(key2, schema, children2, parent2, native, atRoot) {
  const cache2 = walkCache;
  if (!cache2) return resolveName(key2, children2, parent2, native, atRoot);
  const owner = schemaKey(schema);
  let byKey = cache2.resolved.get(owner);
  if (!byKey) {
    byKey = /* @__PURE__ */ new Map();
    cache2.resolved.set(owner, byKey);
  }
  const memo = atRoot ? `\0${key2}` : key2;
  let hits = byKey.get(memo);
  if (!hits) {
    hits = resolveName(key2, children2, parent2, native, atRoot);
    byKey.set(memo, hits);
  }
  return hits;
}
function resolveName(key2, children2, parent2, native, atRoot) {
  if (native) {
    if (key2.includes(":")) return byQualifiedName(key2, children2, parent2);
    return children2.filter((child2) => child2.name === key2);
  }
  const canonical = children2.filter((child2) => memberKey(child2, parent2) === key2);
  if (canonical.length > 0 || !atRoot || !key2.includes(":")) return canonical;
  return byQualifiedName(key2, children2, parent2);
}
function byQualifiedName(key2, children2, parent2) {
  const colon = key2.indexOf(":");
  const moduleName2 = key2.slice(0, colon);
  const local2 = key2.slice(colon + 1);
  if (!moduleName2 || !local2) return [];
  return children2.filter((child2) => child2.name === local2 && definingModule2(child2, parent2) === moduleName2);
}
function node(stmt, value, ptr, kind, extra = {}) {
  return { stmt, value, pointer: ptr, children: [], kind, errors: [], include: true, ...extra };
}
function expandDotted(data, prefix) {
  const pointers = walkCache.pointers;
  const clone = (obj2, path) => {
    const copy = { ...obj2 };
    pointers.set(copy, new Map(pointers.get(obj2) ?? Object.keys(obj2).map((key2) => [key2, join(path, key2)])));
    return copy;
  };
  const result = clone(data, prefix);
  const source = pointers.get(result);
  for (const key2 of Object.keys(result).filter((k) => k.includes("."))) {
    const value = result[key2], pointer = source.get(key2);
    delete result[key2];
    source.delete(key2);
    const parts = key2.split(".");
    if (parts.some((p) => !p)) return { data: result, error: [pointer, `invalid dotted key '${key2}'`] };
    let cur = result;
    for (const part of parts.slice(0, -1)) {
      const map = pointers.get(cur);
      if (!Object.hasOwn(cur, part)) {
        cur[part] = /* @__PURE__ */ Object.create(null);
        pointers.set(cur[part], /* @__PURE__ */ new Map());
        map.set(part, pointer);
      } else if (!cur[part] || typeof cur[part] !== "object" || Array.isArray(cur[part])) return { data: result, error: [pointer, `dotted key '${key2}' conflicts with '${part}'`] };
      else cur[part] = clone(cur[part], map.get(part) ?? pointer);
      cur = cur[part];
    }
    const last = parts[parts.length - 1];
    if (Object.hasOwn(cur, last)) return { data: result, error: [pointer, `dotted key '${key2}' conflicts with an existing member`] };
    cur[last] = value;
    pointers.get(cur).set(last, pointer);
  }
  return { data: result };
}
function walkObject(data, schema, module, checker, parent2, prefix, native, atRoot) {
  if (atRoot) {
    const structure = resolveStructureInstance(data, module);
    if (structure && structure.schema.data_node_kind !== "container") {
      return [
        walkNode(structure.inner, structure.schema, module, checker, parent2, join(prefix, structure.key), native)
      ];
    }
  }
  if (walkCache?.normalization.expandDotted) {
    const expanded = expandDotted(data, prefix);
    if (expanded.error) return [node(null, null, expanded.error[0], "opaque", { errors: [["normalize", expanded.error[1]]], include: false })];
    data = expanded.data;
  }
  const children2 = dataNodes(schema);
  const nodes = [];
  const claimed = /* @__PURE__ */ new Set();
  for (const [key2, raw] of Object.entries(data)) {
    const here = walkCache?.pointers.get(data)?.get(key2) ?? join(prefix, key2);
    const hits = resolveCached(key2, schema, children2, parent2, native, atRoot);
    if (hits.length === 0) {
      nodes.push(node(null, raw, here, "unknown", { inputKey: key2 }));
      continue;
    }
    if (hits.length > 1) {
      nodes.push(
        node(null, null, here, "ambiguous", {
          errors: [["ambiguous-name", `member name '${key2}' matches more than one node`]],
          include: false
        })
      );
      continue;
    }
    const stmt = hits[0];
    if (claimed.has(stmt)) {
      if (walkCache?.normalization.expandDotted) nodes.push(node(null, null, here, "ambiguous", { errors: [["normalize", `member '${key2}' conflicts with another spelling of the same node`]], include: false }));
      continue;
    }
    claimed.add(stmt);
    nodes.push(walkNode(raw, stmt, module, checker, parent2, here, native));
  }
  return nodes;
}
function walkLeaf(raw, stmt, module, checker, ptr, native) {
  const type = leafType(stmt);
  if (!type) return node(stmt, raw, ptr, "leaf");
  const eff = unwrap(module, type);
  const decoded = decodeScalar(raw, type, module, checker, native);
  if (decoded instanceof ExactDecimal) {
    return node(stmt, decoded.text, ptr, "leaf", { projected: decoded });
  }
  if (decoded === NO) {
    const name = typeof eff?.name === "string" ? eff.name : "value";
    if (ENCODED.has(name)) {
      const message = name === "empty" ? native ? "empty is null in native mode; RFC 7951 encodes empty as [null]" : "empty is [null] in RFC 7951; pass --native-json for null" : hint(native, name);
      return node(stmt, null, ptr, "leaf", { errors: [["type", message]], include: false });
    }
    return node(stmt, raw, ptr, "leaf");
  }
  return node(stmt, decoded, ptr, "leaf");
}
function walkNode(raw, stmt, module, checker, parent2, ptr, native) {
  const keyword = keywordOf(stmt);
  if (keyword !== "list" && keyword !== "leaf-list" && walkCache) {
    try {
      raw = walkCache.normalization.visit(stmt, raw);
    } catch (e) {
      return node(stmt, null, ptr, "opaque", { errors: [["normalize", String(e instanceof Error ? e.message : e)]], include: false });
    }
  }
  if ((keyword === "list" || keyword === "leaf-list") && walkCache) raw = walkCache.normalization.collection(stmt, raw);
  if (keyword === "anydata" || keyword === "anyxml") return node(stmt, raw, ptr, "anydata");
  if (keyword === "container" || isStructureSchema(stmt)) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      return node(stmt, null, ptr, "container", { errors: [["type", "container must be an object"]], include: false });
    }
    return node(stmt, null, ptr, "container", {
      children: walkObject(raw, stmt, module, checker, parent2, ptr, native, false)
    });
  }
  if (keyword === "list") return walkList(raw, stmt, module, checker, parent2, ptr, native);
  if (keyword === "leaf-list") {
    if (!Array.isArray(raw)) {
      return node(stmt, null, ptr, "leaf-list", { errors: [["type", "leaf-list must be an array"]], include: false });
    }
    const children2 = raw.map((item, index) => {
      try {
        item = walkCache.normalization.visit(stmt, item);
      } catch (e) {
        return node(stmt, null, `${ptr}/${index}`, "leaf-list-item", { errors: [["normalize", String(e instanceof Error ? e.message : e)]], include: false });
      }
      const child2 = walkLeaf(item, stmt, module, checker, `${ptr}/${index}`, native);
      child2.kind = "leaf-list-item";
      return child2;
    });
    return node(stmt, null, ptr, "leaf-list", { children: children2 });
  }
  if (keyword === "leaf") return walkLeaf(raw, stmt, module, checker, ptr, native);
  return node(stmt, raw, ptr, "opaque");
}
function keyNames(stmt) {
  const raw = typeof stmt.key === "string" ? stmt.key.trim() : "";
  return raw ? raw.split(/\s+/).filter(Boolean) : [];
}
function convertKey(text, leaf, module, checker, native) {
  const type = leafType(leaf);
  if (!type) return text;
  const eff = unwrap(module, type);
  const name = typeof eff?.name === "string" ? eff.name : "";
  let candidate = text;
  if (INTEGER_KEY.has(name)) {
    if (!INT_TEXT.test(text)) return NO;
    candidate = INT642.has(name) ? BigInt(text) : Number(text);
    if (typeof candidate === "number" && !Number.isSafeInteger(candidate)) return NO;
  } else if (DECIMAL.has(name)) {
    if (!isDecText(text)) return NO;
    candidate = new ExactDecimal(text.trim());
  } else if (name === "boolean") {
    if (text !== "true" && text !== "false") return NO;
    candidate = text === "true";
  }
  const decoded = decodeScalar(candidate, type, module, checker, native);
  return decoded === NO ? candidate : decoded;
}
function walkList(raw, stmt, module, checker, parent2, ptr, native) {
  const keys = keyNames(stmt);
  let entries = [];
  let keyed = false;
  if (Array.isArray(raw)) {
    entries = raw.map((item, index) => [String(index), item]);
  } else if (native && raw && typeof raw === "object" && !Array.isArray(raw) && keys.length === 1 && (Object.values(raw).every((item) => item && typeof item === "object" && !Array.isArray(item)) || (walkCache?.normalization.rules(stmt).length ?? 0) > 0)) {
    entries = Object.entries(raw);
    keyed = true;
  } else if (native && raw && typeof raw === "object" && !Array.isArray(raw) && keys.length !== 1) {
    return node(stmt, null, ptr, "list", {
      errors: [["list-encoding", "a list with more than one key must be a JSON array (--native-json)"]],
      include: false
    });
  } else {
    return node(stmt, null, ptr, "list", {
      errors: [["type", native ? "list must be an array or a single-key object" : "list must be an array"]],
      include: false
    });
  }
  const keyLeaf = keys.length === 1 ? dataNodes(stmt).find((child2) => child2.name === keys[0]) : void 0;
  const children2 = entries.map(([token, original]) => {
    const entryPointer = join(ptr, token);
    let item = original;
    try {
      item = walkCache.normalization.visit(stmt, item);
    } catch (e) {
      return node(stmt, null, entryPointer, "entry", { errors: [["normalize", String(e instanceof Error ? e.message : e)]], include: false });
    }
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      return node(stmt, null, entryPointer, "entry", {
        errors: [["type", "list item must be an object"]],
        include: false
      });
    }
    const body = walkObject(item, stmt, module, checker, parent2, entryPointer, native, false);
    if (keyed && keyLeaf?.keyword === "leaf") {
      const converted = convertKey(token, keyLeaf, module, checker, native);
      const present = body.find((child2) => child2.kind === "leaf" && child2.stmt?.name === keyLeaf.name && child2.include);
      if (converted === NO) {
        body.push(
          node(keyLeaf, null, join(entryPointer, keyLeaf.name ?? keys[0]), "leaf", {
            errors: [["type", `dict key '${token}' cannot be converted to the key type`]],
            include: false
          })
        );
      } else if (!present) {
        body.unshift(node(keyLeaf, converted, join(entryPointer, keyLeaf.name ?? keys[0]), "leaf"));
      } else if (present.value !== converted && String(present.value) !== String(converted)) {
        present.errors.push(["key-mismatch", `key leaf does not match dict key '${token}'`]);
      }
    }
    return node(stmt, null, entryPointer, "entry", { children: body });
  });
  return node(stmt, null, ptr, "list", { children: children2 });
}
function* iterInstance(data, module, options = {}) {
  if (!data || typeof data !== "object" || Array.isArray(data)) return;
  const native = options.nativeJson === true;
  const schema = options.schema ?? module;
  const parent2 = options.parentModule ?? (schema === module ? module.name ?? "" : "");
  const checker = new TypeChecker(module);
  const outer = walkCache;
  walkCache = { nodes: /* @__PURE__ */ new WeakMap(), resolved: /* @__PURE__ */ new WeakMap(), unwrapped: /* @__PURE__ */ new WeakMap(), pointers: /* @__PURE__ */ new WeakMap(), normalization: new Normalization(module) };
  walkCache.normalization.skipProjection = options.skipProjection === true;
  let snapshot;
  walkCache.normalization.rootContext = () => {
    snapshot ??= projectInstance([...iterInstance(data, module, { ...options, skipProjection: true })], parent2).data;
    return { data: snapshot, schema, parent: null };
  };
  let nodes;
  try {
    const prepare = (current, isModule = false) => {
      walkCache.normalization.rules(current, isModule);
      for (const child2 of dataNodes(current)) prepare(child2);
    };
    prepare(schema, schema === module);
    let rootData;
    try {
      rootData = walkCache.normalization.visit(schema, data);
    } catch (e) {
      nodes = [node(null, null, "", "opaque", { errors: [["normalize", String(e instanceof Error ? e.message : e)]], include: false })];
      yield* nodes;
      return;
    }
    if (!rootData || typeof rootData !== "object" || Array.isArray(rootData)) {
      nodes = [node(null, null, "", "opaque", { errors: [["normalize", "root normalization must produce an object"]], include: false })];
    } else nodes = walkObject(rootData, schema, module, checker, parent2, "", native, options.atRoot ?? true);
  } finally {
    walkCache = outer;
  }
  yield* nodes;
}
function encodingErrors(nodes) {
  const found = [];
  const walk = (item) => {
    for (const [code, message] of item.errors) found.push({ path: item.pointer, code, message });
    for (const child2 of item.children) walk(child2);
  };
  for (const item of nodes) walk(item);
  return found;
}
function projectInstance(nodes, parent2 = "") {
  const pointerMap = /* @__PURE__ */ new Map();
  return { data: projectLevel(nodes, parent2, "", pointerMap), pointerMap };
}
function projectLevel(nodes, parent2, prefix, pointerMap) {
  const out = {};
  for (const item of nodes) {
    if (item.kind === "unknown" && item.inputKey) {
      out[item.inputKey] = item.value;
      pointerMap.set(join(prefix, item.inputKey), item.pointer);
      continue;
    }
    if (!item.include || !item.stmt) continue;
    const key2 = memberKey(item.stmt, parent2);
    const canon = join(prefix, key2);
    pointerMap.set(canon, item.pointer);
    if (item.kind === "container") {
      out[key2] = projectLevel(item.children, parent2, canon, pointerMap);
    } else if (item.kind === "list") {
      const rows = item.children.filter((child2) => child2.include);
      out[key2] = rows.map((entry, index) => {
        const entryCanon = `${canon}/${index}`;
        pointerMap.set(entryCanon, entry.pointer);
        return projectLevel(entry.children, parent2, entryCanon, pointerMap);
      });
    } else if (item.kind === "leaf-list") {
      const items = item.children.filter((child2) => child2.include);
      out[key2] = items.map((child2, index) => {
        pointerMap.set(`${canon}/${index}`, child2.pointer);
        return child2.projected !== void 0 ? child2.projected : child2.value;
      });
    } else if (item.kind === "leaf" || item.kind === "anydata") {
      out[key2] = item.projected !== void 0 ? item.projected : item.value;
    }
  }
  return out;
}
function remapPointer(path, pointerMap) {
  if (pointerMap.size === 0 || pointerMap.has(path)) return pointerMap.get(path) ?? path;
  const parts = path.split("/");
  for (let index = parts.length; index > 1; index -= 1) {
    const prefix = parts.slice(0, index).join("/");
    if (pointerMap.has(prefix)) {
      const rest = parts.slice(index).join("/");
      const base = pointerMap.get(prefix) ?? prefix;
      return rest ? `${base}/${rest}` : base;
    }
  }
  return path;
}

// ts/src/ext/anydata_validation.ts
function rejectUnknownKeys(kwargs, allowed) {
  const unexpected = Object.keys(kwargs).filter((k) => !allowed.has(k)).sort();
  if (unexpected.length > 0) {
    throw new TypeError(`unexpected keyword arguments: ${JSON.stringify(unexpected)}`);
  }
}
function parseAnydataExtensionConfig(config) {
  rejectUnknownKeys(config, /* @__PURE__ */ new Set(["modules", "mode"]));
  const mode = config.mode === void 0 ? "complete" /* COMPLETE */ : config.mode;
  const seenNames = /* @__PURE__ */ new Set();
  for (let i = 0; i < config.modules.length; i += 1) {
    const mod = config.modules[i];
    const moduleName2 = mod.name;
    if (!moduleName2) {
      throw new TypeError(`modules[${i}] must have a module name`);
    }
    if (seenNames.has(moduleName2)) {
      throw new TypeError(`duplicate module name '${moduleName2}' in modules`);
    }
    seenNames.add(moduleName2);
  }
  return {
    modules: [...config.modules],
    mode
  };
}

// ts/src/validator/operation.ts
var DIRECTIONS = ["input", "output"];
var IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_.-]*$/;
function checkOperationOptions(options) {
  const { rpc, action, direction = "input", context } = options;
  if (!DIRECTIONS.includes(direction)) {
    throw new Error(`direction must be 'input' or 'output', got ${JSON.stringify(direction)}`);
  }
  if (rpc !== void 0 && action !== void 0) {
    throw new Error("rpc and action are mutually exclusive");
  }
  if (rpc === void 0 && action === void 0) {
    if (direction !== "input") {
      throw new Error("direction applies only together with rpc or action");
    }
    if (context !== void 0) {
      throw new Error("context applies only together with rpc or action");
    }
  }
  if (rpc !== void 0 && (typeof rpc !== "string" || rpc.length === 0)) {
    throw new Error("rpc must be a non-empty rpc name");
  }
  if (action !== void 0) {
    if (typeof action !== "string" || action.length === 0) {
      throw new Error("action must be the data resource identifier of an action (RFC 8040 \xA73.5.3)");
    }
    if (context === void 0) {
      throw new Error(
        "action needs context: the instance it is invoked on must be in the server data (RFC 7950 \xA77.15)"
      );
    }
  }
  if (context !== void 0 && (context === null || typeof context !== "object" || Array.isArray(context))) {
    throw new Error("context must be a JSON object");
  }
}
function findRpc(module, name) {
  const rpcs = module.statements.filter((stmt) => stmt.keyword === "rpc" && stmt.name);
  const found = rpcs.find((stmt) => stmt.name === name);
  if (!found) {
    const known = rpcs.map((stmt) => stmt.name).sort();
    throw new Error(`module '${module.name}' has no rpc '${name}' (rpcs: ${known.length ? known.join(", ") : "none"})`);
  }
  return { operation: found, moduleName: module.name ?? "", label: `rpc '${name}'`, parents: [] };
}
function definingModule3(stmt, host) {
  return stmt.defining_module || host;
}
function parseApiPath(text) {
  if (!text.startsWith("/") || text === "/") {
    throw new Error(`action '${text}' must be a data resource identifier such as /module:list=key/action`);
  }
  const segments = text.slice(1).split("/").map((raw) => {
    const eq = raw.indexOf("=");
    const ident = eq < 0 ? raw : raw.slice(0, eq);
    const colon = ident.lastIndexOf(":");
    const module = colon < 0 ? void 0 : ident.slice(0, colon);
    const name = colon < 0 ? ident : ident.slice(colon + 1);
    if (module !== void 0 && !IDENTIFIER.test(module) || !IDENTIFIER.test(name)) {
      throw new Error(`action '${text}': '${raw}' is not an api-identifier (RFC 8040 \xA73.5.3)`);
    }
    const keys = eq < 0 ? void 0 : raw.slice(eq + 1).split(",").map((value) => decodeURIComponent(value));
    return { module, name, keys };
  });
  if (segments[0].module === void 0) {
    throw new Error(`action '${text}': the first segment must be module-qualified (RFC 8040 \xA73.5.3)`);
  }
  return segments;
}
function findDataChild(parent2, name, moduleName2, host) {
  for (const stmt of parent2.statements) {
    if (stmt.keyword === "rpc" || stmt.keyword === "action") continue;
    if (stmt.keyword === "choice" || stmt.keyword === "case") {
      const branches = stmt.keyword === "choice" ? stmt.statements.filter((s) => s.keyword === "case") : [stmt];
      for (const branch of branches) {
        const found = findDataChild(branch, name, moduleName2, host);
        if (found.stmt) {
          return { stmt: found.stmt, wrappers: [stmt, ...branch === stmt ? [] : [branch], ...found.wrappers] };
        }
      }
      if (stmt.keyword === "choice") {
        const direct = stmt.statements.find((s) => s.keyword !== "case" && s.name === name && definingModule3(s, host) === moduleName2);
        if (direct) return { stmt: direct, wrappers: [stmt] };
      }
      continue;
    }
    if (stmt.name === name && definingModule3(stmt, host) === moduleName2) {
      return { stmt, wrappers: [] };
    }
  }
  return { wrappers: [] };
}
function resolveAction(module, path) {
  const host = module.name ?? "";
  const segments = parseApiPath(path);
  if (segments[0].module !== host) {
    throw new Error(`action '${path}': the first segment must be in module '${host}'`);
  }
  if (segments.length < 2) {
    throw new Error(`action '${path}' names no container or list instance to invoke the action on`);
  }
  const parents = [];
  let schema = module;
  let namespace = host;
  for (const segment of segments.slice(0, -1)) {
    namespace = segment.module ?? namespace;
    const { stmt, wrappers } = findDataChild(schema, segment.name, namespace, host);
    const where = "/" + parents.map((p) => p.stmt.name).join("/");
    if (!stmt) {
      throw new Error(`action '${path}': no container or list '${namespace}:${segment.name}' under ${where}`);
    }
    if (stmt.keyword === "list") {
      const keyNames2 = (stmt.key ?? "").split(/\s+/).filter(Boolean);
      if (!segment.keys || segment.keys.length !== keyNames2.length) {
        throw new Error(
          `action '${path}': list '${segment.name}' needs its ${keyNames2.length} key value(s) (${keyNames2.join(", ")}) as ${segment.name}=value (RFC 8040 \xA73.5.3)`
        );
      }
    } else if (stmt.keyword === "container") {
      if (segment.keys) {
        throw new Error(`action '${path}': container '${segment.name}' takes no key values`);
      }
    } else {
      throw new Error(`action '${path}': '${segment.name}' is not a container or list`);
    }
    parents.push({ stmt, ...segment.keys ? { keys: segment.keys } : {}, wrappers });
    schema = stmt;
  }
  const last = segments[segments.length - 1];
  namespace = last.module ?? namespace;
  if (last.keys) {
    throw new Error(`action '${path}': the action segment takes no key values`);
  }
  const action = schema.statements.find(
    (s) => s.keyword === "action" && s.name === last.name && definingModule3(s, host) === namespace
  );
  if (!action) {
    const known = schema.statements.filter((s) => s.keyword === "action" && s.name).map((s) => s.name).sort();
    throw new Error(
      `action '${path}': '${schema.name}' has no action '${namespace}:${last.name}' (actions: ${known.join(", ") || "none"})`
    );
  }
  return { operation: action, moduleName: namespace, label: `action '${path}'`, parents };
}
function findBody(operation, direction) {
  return operation.statements.find((stmt) => stmt.keyword === direction);
}
function operationNode(operation, body) {
  const node2 = new YangStatement({ keyword: "container", name: operation.name });
  if (body) {
    node2.statements = body.statements;
  }
  if (operation.defining_module) {
    node2.defining_module = operation.defining_module;
  }
  return node2;
}
function shallowCopy(value) {
  const copy = Object.assign(Object.create(Object.getPrototypeOf(value)), value);
  const registry = value.module_registry;
  if (registry !== void 0) {
    Object.defineProperty(copy, "module_registry", { value: registry, enumerable: false });
  }
  return copy;
}
function accessibleModule(module, target, operation) {
  const accessible = shallowCopy(module);
  if (target.parents.length === 0) {
    accessible.statements = [...module.statements.filter((stmt) => stmt.keyword !== "rpc"), operation];
    return { module: accessible, parentCopies: [] };
  }
  const chain = target.parents.flatMap((step) => [...step.wrappers, step.stmt]);
  const copies = /* @__PURE__ */ new Map();
  let node2 = accessible;
  for (const original of chain) {
    const child2 = shallowCopy(original);
    copies.set(original, child2);
    node2.statements = node2.statements.map((s) => s === original ? child2 : s);
    node2 = child2;
  }
  node2.statements = node2.statements.map((s) => s === target.operation ? operation : s);
  return { module: accessible, parentCopies: target.parents.map((step) => copies.get(step.stmt)) };
}
function lexical(value) {
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}
function wrapperMember(moduleName2, direction) {
  return `${moduleName2}:${direction}`;
}

// ts/src/validator/document-validator.ts
function missingParent(target, detail) {
  return {
    document: "context",
    code: "action-parent",
    path: "",
    message: `${target.label} is invoked on an instance that is not in the context: ${detail}`,
    severity: "error",
    pathLabel: "context"
  };
}
function pointerFromLabel(path) {
  return path.split(".").filter(Boolean).map((segment) => "/" + segment.replace(/\[(\d+)\]/g, "/$1")).join("");
}
function joinPointer(base, token) {
  return `${base}/${token.replace(/~/g, "~0").replace(/\//g, "~1")}`;
}
function issue(pathLabel, code, message, expression, path) {
  const item = {
    code,
    path: path ?? pointerFromLabel(pathLabel),
    message,
    severity: "error",
    pathLabel
  };
  if (expression) {
    item.expression = expression;
  }
  return item;
}
function formatIssue(item) {
  return item.pathLabel ? `${item.pathLabel}: ${item.message}` : item.message;
}
function toPublicIssue(item) {
  const pub = {
    ...item.document ? { document: item.document } : {},
    code: item.code,
    path: item.path,
    message: item.message,
    severity: item.severity
  };
  if (item.expression) {
    pub.expression = item.expression;
  }
  return pub;
}
var DocumentValidator = class {
  xpath = new XPathEvaluator();
  xpathCache = /* @__PURE__ */ new Map();
  rootCtx;
  enabledFeaturesOverride;
  contextStack = [];
  typeValidationDebug;
  constructor(module, options = {}) {
    this.enabledFeaturesOverride = options.enabledFeaturesByModule ?? null;
    this.typeValidationDebug = options.typeValidationDebug === true;
    const constraintChecks = options.constraintChecks ?? true;
    const leafTypeMode = options.leafTypeMode ?? (constraintChecks ? "full" : "none");
    const ifFeatureCtx = module;
    this.rootCtx = {
      module,
      typeChecker: new TypeChecker(module, {
        typeValidationDebug: this.typeValidationDebug,
        enabledByModule: buildEnabledFeaturesMap(ifFeatureCtx, this.enabledFeaturesOverride)
      }),
      constraintChecks,
      leafTypeMode,
      typeValidationDebug: this.typeValidationDebug,
      anydataValidation: void 0,
      ifFeatureCtx,
      enabledByModule: buildEnabledFeaturesMap(ifFeatureCtx, this.enabledFeaturesOverride)
    };
  }
  /** When true, this validator emits `console.debug` lines for leaf type checks. */
  setTypeValidationDebug(on) {
    this.typeValidationDebug = on;
    this.rootCtx.typeValidationDebug = on;
    this.rootCtx.typeChecker = new TypeChecker(this.rootCtx.module, {
      typeValidationDebug: this.typeValidationDebug,
      enabledByModule: this.rootCtx.enabledByModule
    });
  }
  get ctx() {
    const c = this.contextStack[this.contextStack.length - 1];
    if (!c) {
      throw new Error("DocumentValidator: internal error \u2014 no active validation context");
    }
    return c;
  }
  enableExtension(extension, config) {
    if (extension !== "anydata_validation" /* ANYDATA_VALIDATION */) {
      throw new Error(`unknown validator extension: ${String(extension)}`);
    }
    this.rootCtx.anydataValidation = parseAnydataExtensionConfig(config);
  }
  validate(data, options = {}) {
    const collected = this.collect({ ...this.rootCtx, ...options }, data);
    return [collected.errors.length === 0, collected.errors.map(formatIssue), collected.warnings.map(formatIssue)];
  }
  validateDetailed(data, options = {}) {
    const collected = this.collect({ ...this.rootCtx, ...options }, data);
    return {
      valid: collected.errors.length === 0,
      errors: collected.errors.map(toPublicIssue),
      warnings: collected.warnings.map(toPublicIssue)
    };
  }
  /**
   * Validate the parameters of one rpc `input` or `output` (RFC 7950 §7.14). This validator's
   * module is the accessible module of RFC 7950 §6.4.1 (see `accessibleModule`). `params` is the
   * parameter object without the RFC 8040 wrapper, `rootData` the accessible tree's root object
   * (server data plus the operation node) and `operation` the operation node.
   */
  validateOperationDetailed(input, options = {}) {
    const errors = this.collectOperation(input, options);
    return { valid: errors.length === 0, errors: errors.map(toPublicIssue), warnings: [] };
  }
  /** Same as `validateOperationDetailed`, as `[isValid, errors, warnings]` display strings. */
  validateOperationText(input, options = {}) {
    const errors = this.collectOperation(input, options);
    return [errors.length === 0, errors.map(formatIssue), []];
  }
  /**
   * Validate the parameters of one rpc or action `input` or `output` (RFC 7950 §7.14, §7.15). This
   * validator's module is the accessible module of RFC 7950 §6.4.1 and `parentCopies` are its copies
   * of `target.parents` (see `accessibleModule`). `rootData` is the canonical server data, already
   * validated, which this call may extend (it is the caller's private copy).
   */
  collectOperation(input, options) {
    const { target, operation, parentCopies, params, rootData, wrapper } = input;
    const ctx = { ...this.rootCtx, ...options };
    const active2 = (stmt) => stmtIfFeaturesSatisfied(Array.isArray(stmt.if_features) ? stmt.if_features : [], ctx.ifFeatureCtx, ctx.enabledByModule, stmt.included_from);
    for (const step of target.parents) {
      for (const stmt of [...step.wrappers, step.stmt]) {
        if (!active2(stmt)) {
          throw new Error(`${target.label} is not available: '${stmt.name}' has a false 'if-feature' condition`);
        }
      }
    }
    if (!active2(target.operation)) {
      throw new Error(`${target.label} is not available: its 'if-feature' condition is false`);
    }
    this.contextStack.push(ctx);
    try {
      const errors = [];
      const rootNode = { data: rootData, schema: ctx.module, parent: null };
      let holder = rootData;
      let holderNode = rootNode;
      for (let index = 0; index < target.parents.length; index += 1) {
        const step = target.parents[index];
        const copied = parentCopies[index];
        const value = holder[this.instanceKeys(step.stmt)[0]];
        if (step.stmt.keyword === "list") {
          const keyNames2 = (step.stmt.key ?? "").split(/\s+/).filter(Boolean);
          const keyMembers = keyNames2.map((name) => {
            const leaf = step.stmt.statements.find((child2) => child2.name === name);
            return leaf ? this.instanceKeys(leaf)[0] : name;
          });
          const row = (Array.isArray(value) ? value : []).find(
            (entry) => Boolean(entry) && typeof entry === "object" && keyMembers.every((member, k) => member in entry && lexical(entry[member]) === step.keys[k])
          );
          if (!row) {
            return [missingParent(target, `no '${step.stmt.name}' entry with key ${step.keys.join(", ")}`)];
          }
          holder = row;
        } else {
          let container = value;
          if (container === void 0) {
            if (step.stmt.presence) {
              return [missingParent(target, `presence container '${step.stmt.name}' is absent`)];
            }
            container = {};
            holder[this.instanceKeys(step.stmt)[0]] = container;
          }
          holder = container;
        }
        holderNode = { data: holder, schema: copied, parent: holderNode };
      }
      holder[this.instanceKeys(operation)[0]] = params;
      const opNode = { data: params, schema: operation, parent: holderNode };
      if (ctx.constraintChecks) {
        this.checkMust(operation, opNode, rootNode, "", errors);
      }
      for (const child2 of operation.statements) {
        if (this.effectiveKeyword(child2) === YangTokenType.CHOICE) {
          this.validateChoice(child2, params, "", errors, opNode, rootNode);
          continue;
        }
        if (!child2.name) {
          continue;
        }
        this.validateStatement(child2, this.instanceValue(params, child2), this.childPath("", child2), errors, opNode, rootNode);
      }
      if (ctx.constraintChecks) {
        this.rejectUnknownContainerKeys(operation, params, "", errors);
      }
      for (const item of errors) {
        if (this.pointerMap) {
          item.path = remapPointer(item.path, this.pointerMap);
        }
        if (wrapper !== null) {
          item.path = joinPointer("", wrapper) + item.path;
          item.pathLabel = item.pathLabel ? `${wrapper}.${item.pathLabel}` : wrapper;
        }
      }
      return errors;
    } finally {
      this.contextStack.pop();
    }
  }
  pointerMap = null;
  /** Map canonical walker pointers back to the input JSON as written. */
  setPointerMap(pointerMap) {
    this.pointerMap = pointerMap;
  }
  collect(ctx, data) {
    this.contextStack.push(ctx);
    try {
      const errors = [];
      const warnings = [];
      if (!data || typeof data !== "object" || Array.isArray(data)) {
        errors.push(issue("", "type", "Document must be an object"));
        return { errors, warnings };
      }
      const root = data;
      const rootNode = { data: root, schema: ctx.module, parent: null };
      const nested = resolveStructureInstance(root, ctx.module);
      if (nested && nested.schema.data_node_kind !== "container") {
        const saved = nested.schema.data_node_kind;
        nested.schema.data_node_kind = "container";
        try {
          this.validateStatement(
            nested.schema,
            nested.inner,
            this.childPath("", nested.schema),
            errors,
            rootNode,
            rootNode
          );
        } finally {
          nested.schema.data_node_kind = saved;
        }
        if (this.pointerMap) {
          for (const item of [...errors, ...warnings]) {
            item.path = remapPointer(item.path, this.pointerMap);
          }
        }
        return { errors, warnings };
      }
      for (const stmt of ctx.module.statements) {
        if (!stmt.name) {
          continue;
        }
        const keyword = this.effectiveKeyword(stmt);
        if (!hasTokenType(keyword, [
          YangTokenType.CONTAINER,
          YangTokenType.LIST,
          YangTokenType.LEAF,
          YangTokenType.LEAF_LIST,
          YangTokenType.ANYDATA,
          YangTokenType.ANYXML,
          YangTokenType.CHOICE
        ])) {
          continue;
        }
        this.validateStatement(stmt, this.instanceValue(root, stmt), this.childPath("", stmt), errors, rootNode, rootNode);
      }
      if (ctx.constraintChecks) {
        this.rejectUnknownListItemKeys(ctx.module, root, "", errors);
      }
      if (this.pointerMap) {
        for (const item of [...errors, ...warnings]) {
          item.path = remapPointer(item.path, this.pointerMap);
        }
      }
      return { errors, warnings };
    } finally {
      this.contextStack.pop();
    }
  }
  validateStatement(stmt, value, path, errors, parentNode, rootNode) {
    const keyword = this.effectiveKeyword(stmt);
    const currentNode = { data: value, schema: stmt, parent: parentNode };
    if (keyword === YangTokenType.CHOICE) {
      this.validateChoice(stmt, parentNode.data, path, errors, parentNode, rootNode);
      return;
    }
    if (keyword === YangTokenType.CASE) {
      if (!parentNode.data || typeof parentNode.data !== "object" || Array.isArray(parentNode.data)) {
        return;
      }
      const obj2 = parentNode.data;
      for (const child2 of stmt.statements) {
        if (!child2.name) {
          continue;
        }
        this.validateStatement(child2, this.instanceValue(obj2, child2), this.childPath(path, child2), errors, parentNode, rootNode);
      }
      return;
    }
    const ifFeatures = stmt.if_features;
    const ifFeatureList = Array.isArray(ifFeatures) ? ifFeatures : [];
    if (!stmtIfFeaturesSatisfied(ifFeatureList, this.ctx.ifFeatureCtx, this.ctx.enabledByModule, stmt.included_from)) {
      if (value !== void 0) {
        errors.push(
          issue(
            path,
            "if-feature",
            `Node '${stmt.name ?? "node"}' is present but its 'if-feature' condition is false \u2014 this node must not exist`
          )
        );
      }
      return;
    }
    if (this.ctx.constraintChecks && !this.checkWhen(stmt, value, path, errors, currentNode, rootNode, parentNode)) {
      return;
    }
    if (keyword === YangTokenType.CONTAINER) {
      if (value === void 0 && stmt.presence) {
        return;
      }
      if (value !== void 0 && (!value || typeof value !== "object" || Array.isArray(value))) {
        errors.push(issue(path, "type", "container must be an object"));
        return;
      }
      const absent = value === void 0;
      const obj2 = value ?? {};
      if (absent) {
        currentNode.data = obj2;
      } else if (this.ctx.constraintChecks) {
        this.checkMust(stmt, currentNode, rootNode, path, errors);
      }
      for (const child2 of stmt.statements) {
        const childKw = this.effectiveKeyword(child2);
        if (childKw === YangTokenType.CHOICE) {
          this.validateChoice(child2, obj2, path, errors, currentNode, rootNode);
          continue;
        }
        if (!child2.name) {
          continue;
        }
        this.validateStatement(child2, this.instanceValue(obj2, child2), this.childPath(path, child2), errors, currentNode, rootNode);
      }
      if (this.ctx.constraintChecks) {
        this.rejectUnknownContainerKeys(stmt, obj2, path, errors);
      }
      return;
    }
    if (keyword === YangTokenType.LIST) {
      if (value === void 0) {
        this.checkElementCount(stmt, 0, path, errors);
        return;
      }
      if (!Array.isArray(value)) {
        errors.push(issue(path, "type", "list must be an array"));
        return;
      }
      this.checkElementCount(stmt, value.length, path, errors);
      const keyRaw = typeof stmt.key === "string" ? stmt.key.trim() : "";
      const keyNames2 = keyRaw.length > 0 ? keyRaw.split(/\s+/).map((k) => k.trim()).filter(Boolean) : [];
      if (this.ctx.constraintChecks && keyNames2.length > 0) {
        this.checkListKeyUniqueness(value, keyNames2, stmt.name ?? "list", path, errors);
      }
      if (this.ctx.constraintChecks) {
        this.checkListUnique(stmt, value, path, errors);
      }
      for (let i = 0; i < value.length; i += 1) {
        const item = value[i];
        if (!item || typeof item !== "object" || Array.isArray(item)) {
          errors.push(issue(`${path}[${i}]`, "type", "list item must be an object"));
          continue;
        }
        const itemNode = { data: item, schema: stmt, parent: parentNode };
        if (this.ctx.constraintChecks) {
          this.checkMust(stmt, itemNode, rootNode, `${path}[${i}]`, errors);
        }
        const row = item;
        for (const key2 of keyNames2) {
          if (!(key2 in row)) {
            errors.push(issue(`${path}[${i}]/${key2}`, "mandatory", `Missing list key '${key2}'`));
          }
        }
        for (const child2 of stmt.statements) {
          const childKw = this.effectiveKeyword(child2);
          if (childKw === YangTokenType.CHOICE) {
            this.validateChoice(child2, row, `${path}[${i}]`, errors, itemNode, rootNode);
            continue;
          }
          if (!child2.name) {
            continue;
          }
          this.validateStatement(child2, this.instanceValue(row, child2), this.childPath(`${path}[${i}]`, child2), errors, itemNode, rootNode);
        }
        if (this.ctx.constraintChecks) {
          this.rejectUnknownListItemKeys(stmt, row, `${path}[${i}]`, errors);
        }
      }
      return;
    }
    if (keyword === YangTokenType.LEAF) {
      const mandatory = Boolean(stmt.mandatory);
      if (value === void 0) {
        if (mandatory) {
          errors.push(issue(path, "mandatory", "mandatory leaf is missing"));
        }
        return;
      }
      if (this.ctx.leafTypeMode === "full" && this.ctx.constraintChecks) {
        const typeShape = stmt.type ?? {};
        const typeName = typeShape.name ?? "string";
        const effective = this.effectiveType(typeShape);
        if (effective.name === YangTokenType.LEAFREF) {
          this.checkLeafref(value, effective, path, errors, currentNode, rootNode);
        } else if (effective.name === YangTokenType.INSTANCE_IDENTIFIER) {
          this.checkInstanceIdentifier(value, effective, path, errors, currentNode, rootNode);
        } else {
          const typeIssues = this.ctx.typeChecker.validate(value, typeName, typeShape);
          if (this.ctx.typeValidationDebug) {
            traceTypeValidation(true, "DocumentValidator.leaf:full", {
              path,
              typeName,
              leafTypeMode: this.ctx.leafTypeMode,
              constraintChecks: this.ctx.constraintChecks,
              ok: typeIssues.length === 0,
              reason: typeIssues.length === 0 ? null : typeIssues.map(([, message]) => message).join("; "),
              value: summarizeValue(value)
            });
          }
          for (const [code, message] of typeIssues) {
            errors.push(issue(path, code, message));
          }
        }
      }
      if (this.ctx.constraintChecks) {
        this.checkMust(stmt, currentNode, rootNode, path, errors);
      }
      return;
    }
    if (keyword === YangTokenType.LEAF_LIST) {
      if (value === void 0) {
        this.checkElementCount(stmt, 0, path, errors);
        return;
      }
      if (!Array.isArray(value)) {
        errors.push(issue(path, "type", "leaf-list must be an array"));
        return;
      }
      this.checkElementCount(stmt, value.length, path, errors);
      if (this.ctx.leafTypeMode === "full" && this.ctx.constraintChecks) {
        const typeShape = stmt.type ?? {};
        const typeName = typeShape.name ?? "string";
        const effective = this.effectiveType(typeShape);
        for (let i = 0; i < value.length; i += 1) {
          const itemNode = { data: value[i], schema: stmt, parent: parentNode };
          if (effective.name === YangTokenType.LEAFREF) {
            this.checkLeafref(value[i], effective, `${path}[${i}]`, errors, itemNode, rootNode);
          } else if (effective.name === YangTokenType.INSTANCE_IDENTIFIER) {
            this.checkInstanceIdentifier(value[i], effective, `${path}[${i}]`, errors, itemNode, rootNode);
          } else {
            const typeIssues = this.ctx.typeChecker.validate(value[i], typeName, typeShape);
            if (this.ctx.typeValidationDebug) {
              traceTypeValidation(true, "DocumentValidator.leaf-list:full", {
                path: `${path}[${i}]`,
                typeName,
                leafTypeMode: this.ctx.leafTypeMode,
                constraintChecks: this.ctx.constraintChecks,
                ok: typeIssues.length === 0,
                reason: typeIssues.length === 0 ? null : typeIssues.map(([, message]) => message).join("; "),
                value: summarizeValue(value[i])
              });
            }
            for (const [code, message] of typeIssues) {
              errors.push(issue(`${path}[${i}]`, code, message));
            }
          }
          this.checkMust(stmt, itemNode, rootNode, `${path}[${i}]`, errors);
        }
      }
      return;
    }
    if (keyword === YangTokenType.ANYDATA || keyword === YangTokenType.ANYXML) {
      const mandatory = Boolean(stmt.mandatory);
      if (value === void 0) {
        if (mandatory) {
          errors.push(issue(path, "mandatory", `mandatory ${keyword} is missing`));
        }
        return;
      }
      if (this.ctx.constraintChecks) {
        this.checkMust(stmt, currentNode, rootNode, path, errors);
      }
      if (keyword === YangTokenType.ANYDATA) {
        this.runAnydataSubtreeValidation(value, path, errors);
      }
    }
  }
  /** min-elements / max-elements for a list or leaf-list. An absent one has count 0 (RFC 7950 §7.7.5). */
  checkElementCount(stmt, count, path, errors) {
    const name = stmt.name ?? "node";
    const min = stmt.min_elements;
    const max = stmt.max_elements;
    if (typeof min === "number" && count < min) {
      errors.push(issue(path, "min-elements", `'${name}' has ${count} element(s) but requires at least ${min}`));
    }
    if (typeof max === "number" && count > max) {
      errors.push(issue(path, "max-elements", `'${name}' has ${count} element(s) but allows at most ${max}`));
    }
  }
  rejectUnknownContainerKeys(stmt, obj2, path, errors) {
    this.rejectUnknownListItemKeys(stmt, obj2, path, errors);
  }
  rejectUnknownListItemKeys(stmt, row, path, errors) {
    const allowed = this.collectDirectChildKeys(stmt);
    for (const key2 of Object.keys(row)) {
      if (!allowed.has(key2) && !isAnnotation(key2, this.ctx)) {
        errors.push(issue(path ? `${path}.${key2}` : key2, "unknown-field", `Unknown field '${key2}'`, void 0, joinPointer(pointerFromLabel(path), key2)));
      }
    }
  }
  collectDirectChildKeys(parent2) {
    const keys = /* @__PURE__ */ new Set();
    const walk = (stmt) => {
      const kw = this.effectiveKeyword(stmt);
      if (kw === YangTokenType.CHOICE || kw === YangTokenType.CASE) {
        for (const child2 of stmt.statements ?? []) {
          walk(child2);
        }
        return;
      }
      if (stmt.name && hasTokenType(kw, [
        YangTokenType.CONTAINER,
        YangTokenType.LIST,
        YangTokenType.LEAF,
        YangTokenType.LEAF_LIST,
        YangTokenType.ANYDATA,
        YangTokenType.ANYXML
      ])) {
        for (const key2 of this.instanceKeys(stmt)) {
          keys.add(key2);
        }
      }
    };
    for (const child2 of parent2.statements ?? []) {
      walk(child2);
    }
    return keys;
  }
  validateChoice(choice, parentValue, path, errors, parentNode, rootNode) {
    if (!parentValue || typeof parentValue !== "object" || Array.isArray(parentValue)) {
      if (choice.mandatory === true) {
        errors.push(issue(path, "mandatory-choice", "mandatory choice has no active case"));
      }
      return;
    }
    const obj2 = parentValue;
    const choiceIfs = Array.isArray(choice.if_features) ? choice.if_features : [];
    const choiceActive = stmtIfFeaturesSatisfied(choiceIfs, this.ctx.ifFeatureCtx, this.ctx.enabledByModule, choice.included_from);
    if (!choiceActive && this.choiceHasBranchData(choice, obj2)) {
      errors.push(
        issue(
          path,
          "if-feature",
          `Choice '${choice.name ?? "choice"}' has data but its 'if-feature' condition is false \u2014 this branch must not exist`
        )
      );
      return;
    }
    if (!choiceActive) {
      return;
    }
    if (this.ctx.constraintChecks && !this.checkWhen(choice, this.choiceHasBranchData(choice, obj2) ? true : void 0, path, errors, parentNode, rootNode, parentNode)) {
      return;
    }
    const cases = choice.statements.filter((child2) => child2.keyword === YangTokenType.CASE);
    const activeCases = [];
    let hadBlockedCaseWithData = false;
    for (const c of cases) {
      if (!this.caseHasAnyData(c, obj2)) {
        continue;
      }
      const caseIfs = Array.isArray(c.if_features) ? c.if_features : [];
      if (!stmtIfFeaturesSatisfied(caseIfs, this.ctx.ifFeatureCtx, this.ctx.enabledByModule, c.included_from)) {
        errors.push(
          issue(
            path,
            "if-feature",
            `Case '${c.name ?? "case"}' of choice '${choice.name ?? "choice"}' has data but its 'if-feature' condition is false \u2014 this branch must not exist`
          )
        );
        return;
      }
      if (this.ctx.constraintChecks && !this.checkWhen(c, true, path, errors, parentNode, rootNode, parentNode)) {
        hadBlockedCaseWithData = true;
        continue;
      }
      activeCases.push(c);
    }
    if (activeCases.length > 1) {
      const names = activeCases.map((c) => c.name ?? "<unnamed>").join(", ");
      errors.push(
        issue(
          path,
          "choice-multiple-cases",
          `choice '${choice.name ?? "choice"}' allows only one case, but multiple are active: ${names}`
        )
      );
      return;
    }
    const active2 = activeCases[0];
    if (!active2) {
      if (hadBlockedCaseWithData) {
        return;
      }
      if (choice.mandatory === true) {
        errors.push(issue(path, "mandatory-choice", "mandatory choice has no active case"));
      }
      return;
    }
    for (const child2 of active2.statements) {
      if (!child2.name) {
        continue;
      }
      this.validateStatement(child2, this.instanceValue(obj2, child2), this.childPath(path, child2), errors, parentNode, rootNode);
    }
  }
  choiceHasBranchData(choice, obj2) {
    const cases = choice.statements.filter((child2) => child2.keyword === YangTokenType.CASE);
    return cases.some((c) => this.caseHasAnyData(c, obj2));
  }
  caseHasAnyData(caseStmt, obj2) {
    return caseStmt.statements.some((child2) => this.statementHasMatchingData(child2, obj2));
  }
  statementHasMatchingData(stmt, obj2) {
    const keyword = this.effectiveKeyword(stmt);
    if (hasTokenType(keyword, [
      YangTokenType.LEAF,
      YangTokenType.LEAF_LIST,
      YangTokenType.CONTAINER,
      YangTokenType.LIST,
      YangTokenType.ANYDATA,
      YangTokenType.ANYXML
    ])) {
      return this.instanceKeys(stmt).some((key2) => obj2[key2] !== void 0);
    }
    if (keyword === YangTokenType.CHOICE) {
      return this.choiceHasBranchData(stmt, obj2);
    }
    if (keyword === YangTokenType.CASE) {
      return this.caseHasAnyData(stmt, obj2);
    }
    return false;
  }
  /** RFC 7951 member name: local, or ``module:local`` when the node is defined in another module. */
  instanceKeys(stmt) {
    const local2 = stmt.name;
    if (!local2) {
      return [];
    }
    const parent2 = this.ctx.module.name ?? "";
    const defined = typeof stmt.defining_module === "string" && stmt.defining_module ? stmt.defining_module : parent2;
    if (!parent2 || defined === parent2) {
      return [local2];
    }
    return [`${defined}:${local2}`];
  }
  instanceValue(obj2, stmt) {
    for (const key2 of this.instanceKeys(stmt)) {
      if (Object.prototype.hasOwnProperty.call(obj2, key2)) {
        return obj2[key2];
      }
    }
    return void 0;
  }
  /** Display path of a child. `choice` and `case` are not data nodes, so they keep the parent path. */
  childPath(path, child2) {
    const kw = this.effectiveKeyword(child2);
    if (kw === YangTokenType.CHOICE || kw === YangTokenType.CASE) {
      return path;
    }
    const member = this.instanceKeys(child2)[0] ?? child2.name ?? "";
    return path ? `${path}.${member}` : member;
  }
  effectiveKeyword(stmt) {
    const raw = stmt.keyword ?? "";
    if (raw === YangTokenType.NOTIFICATION) {
      return YangTokenType.CONTAINER;
    }
    if (raw.includes(":")) {
      const kind = stmt.data_node_kind;
      if (kind === YangTokenType.CONTAINER || kind === YangTokenType.LIST) {
        return kind;
      }
    }
    return raw;
  }
  /**
   * RFC 7950: list instance keys must be unique within the list.
   * Reports the first duplicate only. @returns true if a duplicate was found.
   */
  checkListKeyUniqueness(val, keyNames2, listName, pathStr, errors) {
    if (keyNames2.length === 0) {
      return false;
    }
    const seenKeys = /* @__PURE__ */ new Map();
    for (let i = 0; i < val.length; i += 1) {
      const entry = val[i];
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
        continue;
      }
      const row = entry;
      if (keyNames2.some((k) => !(k in row))) continue;
      const keyTuple = keyNames2.map((k) => row[k]);
      const keyStr = JSON.stringify(keyTuple);
      if (seenKeys.has(keyStr)) {
        const firstIdx = seenKeys.get(keyStr);
        const keyDisplay = keyNames2.map((k) => `${k}='${String(row[k])}'`).join(", ");
        errors.push(
          issue(
            pathStr,
            "duplicate-key",
            `Duplicate key in list '${listName}': ${keyDisplay} (entries at index ${firstIdx} and ${i})`
          )
        );
        return true;
      }
      seenKeys.set(keyStr, i);
    }
    return false;
  }
  /**
   * RFC 7950 §7.8.3: one error per `unique` set whose values repeat across entries.
   * Entries missing any leaf of the set are ignored.
   */
  checkListUnique(stmt, val, pathStr, errors) {
    const sets = Array.isArray(stmt.unique) ? stmt.unique : [];
    const missing = /* @__PURE__ */ Symbol("missing");
    const lookup2 = (entry, descPath) => {
      let cur = entry;
      for (const seg of descPath.split("/")) {
        if (!cur || typeof cur !== "object" || Array.isArray(cur) || !Object.prototype.hasOwnProperty.call(cur, seg)) {
          return missing;
        }
        cur = cur[seg];
      }
      return cur;
    };
    for (const paths of sets) {
      const seen = /* @__PURE__ */ new Map();
      for (let i = 0; i < val.length; i += 1) {
        const values = paths.map((p) => lookup2(val[i], p));
        if (values.includes(missing)) {
          continue;
        }
        const token = JSON.stringify(values);
        const first = seen.get(token);
        if (first !== void 0) {
          const shown = paths.map((p, j) => `${p}='${String(values[j])}'`).join(", ");
          errors.push(
            issue(
              pathStr,
              "unique",
              `Unique constraint violated in list '${stmt.name ?? "list"}': ${shown} (entries at index ${first} and ${i})`
            )
          );
          break;
        }
        seen.set(token, i);
      }
    }
  }
  /**
   * RFC 7950 instance-identifier: string path; when require-instance is true, path must be absolute
   * and resolve to at least one node in the instance (same idea as Python DocumentValidator).
   */
  /**
   * The type a leaf's `type` derives from, following typedefs where each `type` was written, so a
   * leafref or instance-identifier behind a typedef (local or imported) is checked like a direct one.
   */
  effectiveType(typeShape) {
    let current = typeShape;
    for (let depth = 0; depth < 64; depth += 1) {
      const typedef = resolveTypedef(this.ctx.module, current);
      if (!typedef?.type) {
        return current;
      }
      current = typedef.type;
    }
    return current;
  }
  leafrefPathAst(typeShape) {
    const rawPath = typeShape.path;
    if (typeof rawPath === "string" && rawPath.trim().length > 0) {
      const recorded = typeShape.xpath_prefixes;
      const text = rawPath.trim();
      const key2 = `path\0${text}\0${recorded ? JSON.stringify(recorded) : this.ctx.module.name ?? ""}`;
      const cached = this.xpathCache.get(key2);
      if (cached) {
        return cached;
      }
      let ast;
      try {
        ast = parseXPathPath(text);
      } catch {
        return null;
      }
      if (xpathPrefixes(ast).size > 0) {
        bindXPathPrefixes(ast, recorded ? (prefix) => recorded[prefix] : modulePrefixResolver(this.ctx.module), text);
      }
      this.xpathCache.set(key2, ast);
      return ast;
    }
    if (rawPath && typeof rawPath === "object" && !Array.isArray(rawPath) && rawPath.kind === "path") {
      return rawPath;
    }
    return null;
  }
  checkLeafref(value, typeShape, path, errors, leafContextNode, rootNode) {
    const requireInstance = typeShape.require_instance !== false;
    const ast = this.leafrefPathAst(typeShape);
    if (!ast || ast.kind !== "path") {
      if (requireInstance) {
        errors.push(issue(path, "leafref", "leafref has no path"));
      }
      return;
    }
    try {
      const context = { current: leafContextNode, root: rootNode };
      const result = this.xpath.eval(ast, context, leafContextNode);
      const nodes = Array.isArray(result) ? result : [];
      const allowed = /* @__PURE__ */ new Set();
      for (const n of nodes) {
        if (!n || typeof n !== "object" || !("data" in n)) {
          continue;
        }
        const v = n.data;
        if (v !== void 0 && v !== null && (typeof v === "string" || typeof v === "number" || typeof v === "boolean")) {
          allowed.add(String(v));
        }
      }
      if (typeof value !== "string" && typeof value !== "number" && typeof value !== "boolean") {
        errors.push(issue(path, "leafref", "leafref value must be a string, number, or boolean"));
        return;
      }
      const s = String(value);
      if (requireInstance && !allowed.has(s)) {
        errors.push(
          issue(path, "leafref", `leafref: value '${s}' does not reference an existing instance (require-instance is true)`)
        );
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      errors.push(issue(path, "leafref", `leafref: error evaluating path (${msg})`));
    }
  }
  checkInstanceIdentifier(value, typeShape, path, errors, currentNode, rootNode) {
    if (typeof value !== "string") {
      errors.push(issue(path, "instance-identifier", `instance-identifier value must be a string, got ${typeof value}`));
      return;
    }
    const requireInstance = typeShape.require_instance !== false;
    if (!requireInstance) {
      return;
    }
    const s = value.trim();
    if (!s) {
      errors.push(issue(path, "instance-identifier", "instance-identifier path must not be empty when require-instance is true"));
      return;
    }
    let ast;
    try {
      ast = parseXPath(s);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      errors.push(issue(path, "instance-identifier", `instance-identifier: invalid path expression (${msg})`));
      return;
    }
    if (ast.kind !== "path") {
      errors.push(issue(path, "instance-identifier", "instance-identifier: value must be a path expression (e.g. /top/leaf)"));
      return;
    }
    if (!ast.isAbsolute) {
      errors.push(
        issue(path, "instance-identifier", "instance-identifier: only absolute paths are supported (path must start with '/')")
      );
      return;
    }
    const context = { current: currentNode, root: rootNode };
    try {
      const nodes = this.xpath.evalPath(ast, context, rootNode);
      if (nodes.length === 0) {
        errors.push(
          issue(
            path,
            "instance-identifier",
            `instance-identifier: no instance at path ${JSON.stringify(value)} (require-instance is true)`
          )
        );
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      errors.push(issue(path, "instance-identifier", `instance-identifier: invalid path expression (${msg})`));
    }
  }
  /**
   * Parse a `must` / `when` expression once per distinct prefix binding. A statement with no
   * recorded binding binds against the root module's own prefix and imports.
   */
  compileXPath(expression, recorded) {
    const key2 = recorded ? `${expression}\0${JSON.stringify(recorded)}` : expression;
    const cached = this.xpathCache.get(key2);
    if (cached) {
      return cached;
    }
    const ast = parseXPath(expression);
    if (xpathPrefixes(ast).size > 0) {
      const resolve2 = recorded ? (prefix) => recorded[prefix] : modulePrefixResolver(this.ctx.module);
      bindXPathPrefixes(ast, resolve2, expression);
    }
    this.xpathCache.set(key2, ast);
    return ast;
  }
  checkMust(stmt, currentNode, rootNode, path, errors) {
    const mustStatements = stmt.statements.filter((child2) => child2.keyword === "must" && typeof child2.argument === "string");
    for (const mustStmt of mustStatements) {
      const expression = mustStmt.argument;
      let ast;
      try {
        ast = this.compileXPath(expression, mustStmt.xpath_prefixes);
      } catch {
        ast = void 0;
      }
      if (!ast) {
        errors.push(
          issue(path, "xpath-error", `Error evaluating must expression on '${stmt.name ?? "node"}'`, expression)
        );
        continue;
      }
      try {
        const context = { current: currentNode, root: rootNode };
        const result = this.xpath.eval(ast, context, currentNode);
        const ok = this.xpathBoolean(result);
        if (!ok) {
          let errorMessage = typeof mustStmt.error_message === "string" && mustStmt.error_message.trim().length > 0 ? mustStmt.error_message : `must constraint not satisfied on '${stmt.name ?? "node"}'`;
          const appTag = typeof mustStmt.error_app_tag === "string" ? mustStmt.error_app_tag : "";
          if (appTag.length > 0) {
            errorMessage = `${errorMessage} (error-app-tag: ${appTag})`;
          }
          errors.push(issue(path, "must", errorMessage, expression));
        }
      } catch {
        errors.push(issue(path, "xpath-error", `Error evaluating must expression on '${stmt.name ?? "node"}'`, expression));
      }
    }
  }
  checkWhen(stmt, value, path, errors, currentNode, rootNode, parentNode) {
    const whenShape = stmt.when;
    const expression = typeof whenShape?.expression === "string" ? whenShape.expression : void 0;
    if (!expression || expression.trim().length === 0) {
      return true;
    }
    let ast;
    try {
      ast = this.compileXPath(expression, whenShape?.xpath_prefixes);
    } catch {
      ast = void 0;
    }
    if (!ast) {
      errors.push(issue(path, "xpath-error", `Error evaluating when expression on '${stmt.name ?? "node"}'`, expression));
      return false;
    }
    try {
      const evaluateWithParentContext = whenShape?.evaluate_with_parent_context === true;
      const evalNode = evaluateWithParentContext ? parentNode : currentNode;
      const context = { current: evalNode, root: rootNode };
      const result = this.xpath.eval(ast, context, evalNode);
      const active2 = this.xpathBoolean(result);
      if (!active2) {
        if (value !== void 0) {
          errors.push(issue(path, "when", "node is not allowed by when condition", expression));
        }
        return false;
      }
      return true;
    } catch {
      errors.push(issue(path, "xpath-error", `Error evaluating when expression on '${stmt.name ?? "node"}'`, expression));
      return false;
    }
  }
  xpathBoolean(value) {
    if (Array.isArray(value)) {
      return value.length > 0;
    }
    if (typeof value === "boolean") {
      return value;
    }
    if (typeof value === "number") {
      return value !== 0 && !Number.isNaN(value);
    }
    if (typeof value === "string") {
      return value.length > 0;
    }
    return value !== null && value !== void 0;
  }
  anydataModuleMap(modules) {
    const map = {};
    for (const mod of modules) {
      const n = mod.name;
      if (n) {
        map[n] = mod;
      }
    }
    return map;
  }
  /**
   * RFC 7951 qualified members under `anydata` (draft-ietf-netmod-yang-anydata-validation §4–§5).
   * Nested validation uses anydata-complete (full constraints) vs anydata-candidate (no constraint checks).
   */
  runAnydataSubtreeValidation(value, anydataPath, errors) {
    if (!this.ctx.anydataValidation || !value || typeof value !== "object" || Array.isArray(value)) {
      return;
    }
    const mode = this.ctx.anydataValidation.mode;
    const modules = this.ctx.anydataValidation.modules;
    const moduleMap = this.anydataModuleMap(modules);
    const obj2 = value;
    for (const [jsonKey, childVal] of Object.entries(obj2)) {
      const { statementName, moduleName: moduleName2 } = resolveQualifiedTopLevel(jsonKey, moduleMap);
      if (!statementName || !moduleName2) {
        errors.push(
          issue(
            `${anydataPath}.${jsonKey}`,
            "unknown-field",
            `Unknown anydata member '${jsonKey}': no matching module:identifier in the provided modules`
          )
        );
        continue;
      }
      const mod = moduleMap[moduleName2];
      const top = mod?.findStatement(statementName);
      if (!top) {
        errors.push(issue(`${anydataPath}.${jsonKey}`, "unknown-field", `Unknown anydata member '${jsonKey}'`));
        continue;
      }
      if (top.keyword === YangTokenType.LEAF) {
        errors.push(
          issue(
            `${anydataPath}.${jsonKey}`,
            "type",
            `anydata member '${jsonKey}' maps to a leaf; nested subtree validation expects a container or list`
          )
        );
        continue;
      }
      const fragment = { [statementName]: childVal };
      const payloadIfCtx = mod;
      const payloadCtx = {
        allowJsonld: this.ctx.allowJsonld,
        allowJsonSchema: this.ctx.allowJsonSchema,
        module: mod,
        typeChecker: new TypeChecker(mod, {
          typeValidationDebug: this.rootCtx.typeValidationDebug,
          enabledByModule: buildEnabledFeaturesMap(payloadIfCtx, this.enabledFeaturesOverride)
        }),
        constraintChecks: mode === "complete" /* COMPLETE */,
        leafTypeMode: mode === "complete" /* COMPLETE */ ? "full" : "none",
        typeValidationDebug: this.rootCtx.typeValidationDebug,
        anydataValidation: void 0,
        ifFeatureCtx: payloadIfCtx,
        enabledByModule: buildEnabledFeaturesMap(payloadIfCtx, this.enabledFeaturesOverride)
      };
      const inner = this.collect(payloadCtx, fragment);
      for (const innerIssue of inner.errors) {
        errors.push(issue(`${anydataPath}.${jsonKey}`, innerIssue.code, formatIssue(innerIssue)));
      }
    }
  }
};

// ts/src/validator/yang-validator.ts
var YangValidator = class {
  constructor(module, options = {}) {
    this.module = module;
    this.options = options;
    this.typeValidationDebug = options.typeValidationDebug === true;
    this.documentValidator = this.newDocumentValidator(module);
  }
  module;
  options;
  documentValidator;
  extensions = [];
  typeValidationDebug;
  newDocumentValidator(root) {
    const validator = new DocumentValidator(root, {
      enabledFeaturesByModule: this.options.enabledFeaturesByModule ?? null,
      typeValidationDebug: this.typeValidationDebug
    });
    for (const [extension, config] of this.extensions) {
      validator.enableExtension(extension, config);
    }
    return validator;
  }
  /**
   * Toggle `console.debug` tracing for leaf type checks performed by this validator only.
   */
  setTypeValidationDebug(on) {
    this.typeValidationDebug = on;
    this.documentValidator.setTypeValidationDebug(on);
    return this;
  }
  enableExtension(extension, config) {
    this.documentValidator.enableExtension(extension, config);
    this.extensions.push([extension, config]);
  }
  /**
   * Validate `data` against the module, or against one rpc's or action's input or output.
   *
   * With `options.rpc` (a name) or `options.action` (the RFC 8040 §3.5.3 data resource identifier
   * `/module:list=key/action`) set, `data` is that operation's `options.direction` (`"input"`
   * default, or `"output"`) instance: the RFC 8040 §3.6 `{"module:input": {...}}` wrapper in RFC
   * 7951 mode, the bare parameter object with `nativeJson`. `options.context` is server data
   * (required for an action). It is validated first; its errors carry `document: "context"` and the
   * operation is then not checked. Otherwise the operation's `must` and `leafref` reach it (RFC 7950
   * §6.4.1). An unknown rpc or action, or a bad option combination, throws.
   */
  validate(data, options = {}) {
    checkOperationOptions(options);
    if (options.rpc !== void 0 || options.action !== void 0) {
      const detailed = this.validateOperation(data, options);
      const text = (issue2) => {
        const where = issue2.document ? `${issue2.document} ${issue2.path}` : issue2.path;
        return where ? `${where}: ${issue2.message}` : issue2.message;
      };
      return { isValid: detailed.valid, errors: detailed.errors.map(text), warnings: detailed.warnings.map(text) };
    }
    const prepared = this.prepare(data, options.nativeJson === true);
    const [isValid, errors, warnings] = this.documentValidator.validate(prepared.data, options);
    const encoding = prepared.errors.map((issue2) => issue2.path ? `${issue2.path}: ${issue2.message}` : issue2.message);
    const all = [...encoding, ...errors];
    return { isValid: isValid && encoding.length === 0, errors: all, warnings };
  }
  /**
   * Structured issues. `validate()` string output is unchanged.
   * Each issue is `{ code, path, message, expression?, severity }` with `path` a JSON Pointer; an issue
   * about the server data context of an rpc or action also has `document: "context"`.
   */
  validateDetailed(data, options = {}) {
    checkOperationOptions(options);
    if (options.rpc !== void 0 || options.action !== void 0) {
      return this.validateOperation(data, options);
    }
    return this.validateDocument(data, options.nativeJson === true, options);
  }
  validateDocument(data, nativeJson, options) {
    const prepared = this.prepare(data, nativeJson);
    const result = this.documentValidator.validateDetailed(prepared.data, options);
    const encoding = prepared.errors.map((issue2) => ({
      code: issue2.code,
      path: issue2.path,
      message: issue2.message,
      severity: "error"
    }));
    const errors = [...encoding, ...result.errors];
    return { valid: errors.length === 0, errors, warnings: result.warnings };
  }
  validateOperation(data, options) {
    const direction = options.direction ?? "input";
    const nativeJson = options.nativeJson === true;
    const target = options.rpc !== void 0 ? findRpc(this.module, options.rpc) : resolveAction(this.module, options.action);
    const operation = operationNode(target.operation, findBody(target.operation, direction));
    let contextWarnings = [];
    if (options.context !== void 0) {
      const checked = this.validateDocument(options.context, nativeJson, options);
      const mark = (issue2) => ({ document: "context", ...issue2 });
      if (!checked.valid) {
        return { valid: false, errors: checked.errors.map(mark), warnings: checked.warnings.map(mark) };
      }
      contextWarnings = checked.warnings.map(mark);
    }
    let wrapper = null;
    let params = data;
    const fail = (issue2) => ({
      valid: false,
      errors: [{ ...issue2, severity: "error" }],
      warnings: contextWarnings
    });
    if (!nativeJson) {
      wrapper = wrapperMember(target.moduleName, direction);
      const keys = data && typeof data === "object" && !Array.isArray(data) ? Object.keys(data).filter((key2) => !isAnnotation(key2, options)) : null;
      if (!keys || keys.length !== 1 || keys[0] !== wrapper) {
        const found = keys ? keys.map((key2) => `'${key2}'`).join(", ") : Array.isArray(data) ? "array" : typeof data;
        const kind = options.rpc !== void 0 ? "rpc" : "action";
        return fail({
          code: "operation-wrapper",
          path: "",
          message: `${kind} ${direction} must be an object with the single member '${wrapper}' (RFC 8040 \xA73.6); found ${found || "no members"}. Pass nativeJson for the bare parameter object`
        });
      }
      params = data[wrapper];
      if (!params || typeof params !== "object" || Array.isArray(params)) {
        return fail({ code: "type", path: `/${escapePointer(wrapper)}`, message: `${direction} must be an object` });
      }
    } else if (!params || typeof params !== "object" || Array.isArray(params)) {
      return fail({ code: "type", path: "", message: "operation parameters must be an object" });
    }
    const host = this.module.name ?? "";
    const nodes = [...iterInstance(params, this.module, { nativeJson, schema: operation, parentModule: target.moduleName, atRoot: false })];
    const projected = projectInstance(nodes, host);
    const rootData = options.context !== void 0 ? projectInstance([...iterInstance(options.context, this.module, { nativeJson })], host).data : {};
    const accessible = accessibleModule(this.module, target, operation);
    const validator = this.newDocumentValidator(accessible.module);
    validator.setPointerMap(projected.pointerMap);
    const result = validator.validateOperationDetailed({
      target,
      operation,
      parentCopies: accessible.parentCopies,
      params: projected.data,
      rootData,
      wrapper
    }, options);
    const encoding = encodingErrors(nodes).map((item) => ({
      code: item.code,
      path: wrapper === null ? item.path : `/${escapePointer(wrapper)}${item.path}`,
      message: item.message,
      severity: "error"
    }));
    const errors = [...encoding, ...result.errors];
    return { valid: errors.length === 0, errors, warnings: [...contextWarnings, ...result.warnings] };
  }
  prepare(data, nativeJson) {
    const nodes = [...iterInstance(data, this.module, { nativeJson })];
    const projected = projectInstance(nodes, this.module.name ?? "");
    this.documentValidator.setPointerMap(projected.pointerMap);
    return { data: projected.data, errors: encodingErrors(nodes) };
  }
};
function escapePointer(token) {
  return token.replace(/~/g, "~0").replace(/\//g, "~1");
}

// ts/src/xpath/subtree-dependencies.ts
function expressionIsWithinSubtree(expression, context, subtree) {
  const within = (path) => subtree.every((part, i) => path[i] === part);
  const visit = (node2, base) => {
    if (node2.kind === "literal") return true;
    if (node2.kind === "binary") {
      if (node2.operator === "/" && node2.left.kind === "function" && node2.left.name === "current") return within(context) && visit(node2.right, context);
      return visit(node2.left, base) && visit(node2.right, base);
    }
    if (node2.kind === "function") {
      if (node2.name === "deref") return false;
      if (node2.name === "current") return within(context);
      return node2.args.every((arg) => visit(arg, base));
    }
    const path = node2.isAbsolute ? [] : [...base];
    for (const segment of node2.segments) {
      if (segment.step === "..") path.pop();
      else if (segment.step !== ".") {
        if (segment.step.includes("*")) return false;
        path.push(segment.step.split(":").pop());
      }
      if (segment.predicate && !visit(segment.predicate, path)) return false;
    }
    return within(path);
  };
  return visit(parseXPath(expression), context);
}

// ts/src/json/subtree.ts
var obj = (v) => v && typeof v === "object" && !Array.isArray(v) ? v : {};
var local = (name) => name.split(":").pop();
function statementAt(module, path) {
  let statements = module.statements;
  let current;
  const candidates = (items) => items.flatMap((item) => item.keyword === "choice" || item.keyword === "case" ? candidates(item.statements) : [item]);
  for (const segment of path) {
    current = candidates(statements).find((item) => item.name === segment);
    if (!current) return void 0;
    statements = current.statements;
  }
  return current;
}
function leafrefType(module, path) {
  const stmt = statementAt(module, path);
  if (!stmt || stmt.keyword !== "leaf" && stmt.keyword !== "leaf-list") return void 0;
  let type = obj(stmt.type);
  const seen = /* @__PURE__ */ new Set();
  while (type.name !== "leafref") {
    if (seen.has(type)) throw new YangExportError(`circular typedef at '/${path.join("/")}'`);
    seen.add(type);
    if (type.name === "union" && Array.isArray(type.types)) {
      const containsLeafref = (member, visited) => {
        if (member.name === "leafref") return true;
        if (visited.has(member)) throw new YangExportError(`circular typedef at '/${path.join("/")}'`);
        visited.add(member);
        if (member.name === "union" && Array.isArray(member.types)) return member.types.some((raw) => containsLeafref(obj(raw), new Set(visited)));
        const nested = resolveTypedef(module, member);
        return nested?.type ? containsLeafref(obj(nested.type), visited) : false;
      };
      if (type.types.some((raw) => containsLeafref(obj(raw), /* @__PURE__ */ new Set()))) {
        throw new YangExportError(`cannot safely project a union containing a leafref at '/${path.join("/")}'`);
      }
    }
    const typedef = resolveTypedef(module, type);
    if (!typedef?.type) return void 0;
    type = obj(typedef.type);
  }
  return type;
}
function leafrefPath(type) {
  if (typeof type.path === "string") return type.path;
  const ast = obj(type.path);
  if (ast.kind !== "path" || !Array.isArray(ast.segments)) throw new YangExportError("invalid leafref path");
  if (typeof ast.source === "string") return ast.source;
  const segments = ast.segments.map((raw) => {
    const segment = obj(raw);
    if (segment.predicate) throw new YangExportError("cannot safely project a leafref typedef path with predicates");
    return String(segment.step);
  });
  return `${ast.isAbsolute ? "/" : ""}${segments.join("/")}`;
}
function translatePatterns(value) {
  if (Array.isArray(value)) {
    for (const item of value) translatePatterns(item);
    return;
  }
  if (!value || typeof value !== "object") return;
  const node2 = value;
  const patterns = obj(node2["x-yang"])["string-patterns"];
  if (Array.isArray(patterns) && patterns.length) {
    const convert = (raw) => {
      const pattern = String(obj(raw).pattern);
      if (/(?:^|[^\\])(?:\\\\)*\\[dDsSwWiIcCpP]/.test(pattern)) throw new YangExportError("subtree schema cannot portably encode an XSD regex shorthand or Unicode category");
      return translateXsdRegex(pattern).source.replace(
        /\\u\{([0-9A-Fa-f]+)\}/g,
        (_, hex) => {
          const n = parseInt(hex, 16);
          return n <= 65535 ? `\\u${hex.padStart(4, "0")}` : String.fromCodePoint(n);
        }
      );
    };
    if (patterns.length === 1 && !obj(patterns[0])["invert-match"]) node2.pattern = convert(patterns[0]);
    else if (Array.isArray(node2.allOf)) patterns.forEach((raw, i) => {
      const part = obj(node2.allOf[i]);
      if (obj(raw)["invert-match"]) obj(part.not).pattern = convert(raw);
      else part.pattern = convert(raw);
    });
  }
  for (const child2 of Object.values(node2)) translatePatterns(child2);
}
function children(node2) {
  const out = [node2];
  if (node2.items && typeof node2.items === "object") out.push(...children(obj(node2.items)));
  for (const value of Object.values(obj(node2.properties))) {
    const schema = obj(value);
    if (obj(schema["x-yang"]).type === "choice") out.push(...children(schema));
  }
  for (const k of ["oneOf", "anyOf", "allOf"]) if (Array.isArray(node2[k])) {
    for (const branch of node2[k]) out.push(...children(obj(branch)));
  }
  return out;
}
function child(node2, name) {
  const matches = [];
  for (const parent2 of children(node2)) for (const [key2, value] of Object.entries(obj(parent2.properties))) {
    if ((key2 === name || !name.includes(":") && local(key2) === name) && !matches.some((existing) => JSON.stringify(existing) === JSON.stringify(value))) matches.push(obj(value));
  }
  if (matches.length !== 1) throw new YangExportError(`subtree path segment '${name}' ${matches.length ? "is ambiguous" : "was not found"}`);
  return matches[0];
}
function lookup(root, path) {
  return path.reduce((node2, name) => child(node2, name), root);
}
function targetPath(expression, context) {
  const ast = parseXPath(expression);
  if (ast.kind !== "path") throw new YangExportError(`cannot resolve leafref '${expression}'`);
  const path = ast.isAbsolute ? [] : [...context];
  for (const step of ast.segments) {
    if (step.step === "..") {
      if (!path.length) throw new YangExportError(`invalid leafref '${expression}'`);
      path.pop();
    } else if (step.step !== ".") {
      if (step.step.includes("*")) throw new YangExportError(`cannot resolve leafref '${expression}'`);
      path.push(local(step.step));
    }
  }
  return path;
}
function supportedPrefixes(expression, module, bindings) {
  const visit = (node2) => {
    if (node2.kind === "literal") return true;
    if (node2.kind === "binary") return visit(node2.left) && visit(node2.right);
    if (node2.kind === "function") return node2.args.every(visit);
    return node2.segments.every((s) => {
      const prefix = s.step.includes(":") ? s.step.split(":")[0] : void 0;
      return (!prefix || prefix === module.prefix || bindings[prefix] === module.name) && (!s.predicate || visit(s.predicate));
    });
  };
  return visit(parseXPath(expression));
}
function guardsActive(expressions, module, enabled) {
  const imported = reachableModuleData(module).filter((other) => other.name !== module.name);
  for (const expression of expressions) {
    for (const token of expression.match(/[A-Za-z_][A-Za-z0-9_.:-]*/g) ?? []) {
      if (!["and", "or", "not"].includes(token) && !token.includes(":") && imported.some((other) => other.features.has(token))) {
        throw new YangExportError(`cannot safely resolve unqualified if-feature '${token}' shared with an imported module`);
      }
    }
  }
  return stmtIfFeaturesSatisfied(expressions, module, enabled);
}
function restrictGatedValues(node2, module, enabled) {
  if (Array.isArray(node2)) {
    for (const item of node2) restrictGatedValues(item, module, enabled);
    return;
  }
  if (!node2 || typeof node2 !== "object") return;
  const current = node2;
  const meta = obj(current["x-yang"]);
  const entries = meta.enums;
  const values = current.enum;
  if (Array.isArray(entries) && Array.isArray(values)) {
    const drop = /* @__PURE__ */ new Set();
    const kept = [];
    for (const entry of entries) {
      const item = obj(entry);
      const name = item.name;
      const feats = Array.isArray(item["if-features"]) ? item["if-features"].filter((feat) => typeof feat === "string" && feat.length > 0) : [];
      if (typeof name === "string" && feats.length > 0 && !guardsActive(feats, module, enabled)) {
        drop.add(name);
        continue;
      }
      kept.push(entry);
    }
    if (drop.size > 0) {
      current.enum = values.filter((value) => typeof value !== "string" || !drop.has(value));
      if (kept.some((entry) => Array.isArray(obj(entry)["if-features"]) && obj(entry)["if-features"].length > 0)) meta.enums = kept;
      else delete meta.enums;
    }
  }
  const bitGuards = meta["bit-if-features"];
  const bits = meta.bits;
  if (bitGuards && typeof bitGuards === "object" && !Array.isArray(bitGuards) && bits && typeof bits === "object" && !Array.isArray(bits)) {
    const disabled = Object.entries(bitGuards).filter(
      ([, feats]) => Array.isArray(feats) && feats.some((feat) => typeof feat === "string" && feat.length > 0) && !guardsActive(feats.filter((feat) => typeof feat === "string"), module, enabled)
    ).map(([name]) => name);
    if (disabled.length > 0) {
      for (const name of disabled) {
        delete bits[name];
        delete bitGuards[name];
      }
      const names = Object.keys(bits);
      const escaped = names.map((name) => name.replace(/[()[\]{}?*+|^$\\.\-&~#\s]/g, "\\$&")).sort((a, b) => b.length - a.length);
      current.pattern = names.length === 0 ? "^$" : `^$|^(?:${escaped.join("|")})(?:\\s+(?:${escaped.join("|")}))*$`;
      if (Object.keys(bitGuards).length === 0) delete meta["bit-if-features"];
    }
  }
  for (const child2 of Object.values(current)) restrictGatedValues(child2, module, enabled);
}
function projectSubtree(full, module, selection, nativeJson = false, available = full) {
  const segments = parseAbsoluteSchemaPath(selection, module.prefix || void 0);
  for (const seg of segments) if (seg.prefix !== module.prefix && seg.prefix !== module.name) {
    throw new YangExportError(`unsupported module prefix '${seg.prefix}' in subtree path '${selection}'`);
  }
  const scope = segments.map((s) => s.name);
  const selected = structuredClone(lookup(available, scope));
  const diagnostics = [];
  const within = (expression, path, bindings) => supportedPrefixes(expression, module, bindings) && expressionIsWithinSubtree(expression, path, scope);
  const report = (path, constraint, expression, reason = "depends on data outside the selected subtree or cannot be proved local") => {
    const entry = { path: `/${path.join("/")}`, constraint, expression, reason };
    if (!diagnostics.some((item) => item.path === entry.path && item.constraint === constraint && item.expression === expression && item.reason === reason)) diagnostics.push(entry);
  };
  const visit = (node2, path, dataNode = true) => {
    const meta = obj(node2["x-yang"]);
    const stmt = statementAt(module, path);
    const inheritedLeafref = dataNode ? leafrefType(module, path) : void 0;
    if (inheritedLeafref && meta.type !== "leafref" && (stmt?.keyword === "leaf" || stmt?.keyword === "leaf-list" && meta.type !== "leaf-list")) {
      meta.type = "leafref";
      meta.path = leafrefPath(inheritedLeafref);
      meta["require-instance"] = inheritedLeafref.require_instance !== false;
      if (inheritedLeafref.xpath_prefixes) meta["xpath-prefixes"] = inheritedLeafref.xpath_prefixes;
      node2["x-yang"] = meta;
    }
    const bindings = obj(meta["xpath-prefixes"]);
    if (Array.isArray(meta.must)) meta.must = meta.must.filter((raw) => {
      const item = obj(raw), expression = String(item.must ?? "");
      if (within(expression, path, obj(item["xpath-prefixes"]))) return true;
      report(path, "must", expression);
      return false;
    });
    const when = obj(meta.when);
    if (typeof when.condition === "string" && !within(when.condition, when["evaluate-with-parent-context"] === true ? path.slice(0, -1) : path, obj(when["xpath-prefixes"]))) {
      report(path, "when", when.condition);
      delete meta.when;
    }
    if (meta.type === "leafref" && typeof meta.path === "string") {
      const expression = meta.path;
      if (!supportedPrefixes(expression, module, bindings)) throw new YangExportError(`cannot resolve leafref '${expression}' outside module`);
      let target = lookup(full, targetPath(expression, path));
      let targetContext = targetPath(expression, path);
      const seen = /* @__PURE__ */ new Set();
      while (true) {
        const targetMeta = obj(target["x-yang"]);
        const targetType = leafrefType(module, targetContext);
        const next = targetMeta.type === "leafref" ? String(targetMeta.path ?? "") : targetType ? leafrefPath(targetType) : void 0;
        if (next === void 0) break;
        const identity = targetContext.join("/");
        if (seen.has(identity)) throw new YangExportError(`circular leafref '${expression}'`);
        seen.add(identity);
        if (!supportedPrefixes(next, module, obj(targetMeta["xpath-prefixes"] ?? targetType?.xpath_prefixes))) throw new YangExportError(`cannot resolve leafref '${next}' outside module`);
        targetContext = targetPath(next, targetContext);
        target = lookup(full, targetContext);
      }
      for (const key2 of ["type", "$ref", "enum", "pattern", "minimum", "maximum", "minLength", "maxLength", "anyOf", "oneOf", "allOf", "format", "multipleOf"]) {
        delete node2[key2];
        if (key2 in target) node2[key2] = structuredClone(target[key2]);
      }
      let targetEnabled = true;
      try {
        lookup(available, targetPath(expression, path));
      } catch {
        targetEnabled = false;
      }
      if (!within(expression, path, bindings) || !targetEnabled) {
        meta.type = "leaf";
        delete meta.path;
        delete meta["require-instance"];
        delete meta["xpath-prefixes"];
        if (targetEnabled) report(path, "leafref", expression);
        else report(path, "leafref", expression, "target is disabled by feature selection");
      }
    }
    for (const [name, value] of Object.entries(obj(node2.properties))) visit(obj(value), [...path, local(name)]);
    if (node2.items && typeof node2.items === "object") visit(obj(node2.items), path, meta.type === "leaf-list");
    for (const key2 of ["oneOf", "anyOf", "allOf"]) if (Array.isArray(node2[key2])) for (const branch of node2[key2]) visit(obj(branch), path, false);
    if (nativeJson && meta.type === "list" && typeof meta.key === "string" && meta.key.trim().split(/\s+/).length === 1) {
      const item = obj(node2.items);
      const keyedItem = structuredClone(item);
      if (Array.isArray(keyedItem.required)) keyedItem.required = keyedItem.required.filter((k) => local(String(k)) !== local(String(meta.key)));
      const array = { type: "array", items: item };
      for (const k of ["minItems", "maxItems"]) if (k in node2) {
        array[k] = node2[k];
        delete node2[k];
      }
      delete node2.type;
      delete node2.items;
      const keyed = { type: "object", additionalProperties: keyedItem };
      if (typeof array.minItems === "number") keyed.minProperties = array.minItems;
      if (typeof array.maxItems === "number") keyed.maxProperties = array.maxItems;
      node2.anyOf = [array, keyed];
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
  return { schema: selected, diagnostics };
}

// ts/src/json/default-values.ts
var YANG_INT_TYPES = YANG_INTEGER_BUILTIN_NAMES;
function tryIntLiteral(value) {
  if (typeof value === "number" && Number.isInteger(value)) {
    return value;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (/^-?\d+$/.test(trimmed)) {
      return Number.parseInt(trimmed, 10);
    }
  }
  return null;
}
function coerceDefaultValue(value, typeName) {
  if (value === void 0 || value === null || typeName === void 0) {
    return value;
  }
  if (typeName === "boolean") {
    if (value === true || value === "true") {
      return true;
    }
    if (value === false || value === "false") {
      return false;
    }
  }
  if (YANG_INT_TYPES.has(typeName)) {
    if (typeof value === "number" && Number.isInteger(value)) {
      return value;
    }
    const parsed = tryIntLiteral(value);
    if (parsed !== null) {
      return parsed;
    }
  }
  if (typeName === "decimal64" || typeName === "number") {
    if (typeof value === "number") {
      return value;
    }
    const n = Number(value);
    if (!Number.isNaN(n)) {
      return n;
    }
  }
  return value;
}
function jsonSchemaDefaultValue(defaultValue2, options = {}) {
  if (defaultValue2 === void 0 || defaultValue2 === null) {
    return defaultValue2;
  }
  const { yangTypeName = null, jsonSchemaType = null } = options;
  const typeName = yangTypeName ?? jsonSchemaType;
  if (typeName === "boolean" || jsonSchemaType === "boolean") {
    if (defaultValue2 === true || typeof defaultValue2 === "string" && defaultValue2.toLowerCase() === "true") {
      return true;
    }
    if (defaultValue2 === false || typeof defaultValue2 === "string" && defaultValue2.toLowerCase() === "false") {
      return false;
    }
  }
  if (yangTypeName === "union") {
    const numeric = tryIntLiteral(defaultValue2);
    if (numeric !== null) {
      return numeric;
    }
    return defaultValue2;
  }
  let coerceType = yangTypeName ?? void 0;
  if (jsonSchemaType === "integer" && (coerceType === void 0 || coerceType === "integer")) {
    coerceType = "int32";
  }
  if (jsonSchemaType === "number" && coerceType === void 0) {
    coerceType = "decimal64";
  }
  const coerced = coerceDefaultValue(defaultValue2, coerceType ?? void 0);
  if (coerced !== defaultValue2) {
    return coerced;
  }
  if (jsonSchemaType === "integer") {
    const numeric = tryIntLiteral(defaultValue2);
    if (numeric !== null) {
      return numeric;
    }
  }
  return defaultValue2;
}

// ts/src/json/generator.ts
function withDescription(out, text) {
  if (typeof text === "string" && text.length > 0) {
    out.description = text;
  }
}
function asRecord(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}
function isSchemaDataNode(stmt) {
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
var extensionUses;
function isExtensionInvocation(stmt) {
  return typeof stmt.prefix === "string" && stmt.prefix.length > 0 && typeof stmt.resolved_extension_name === "string" && stmt.resolved_extension_name.length > 0;
}
function asStatement(value) {
  return value instanceof YangStatement ? value : new YangStatement(value ?? {});
}
function statementListOf(value) {
  return Array.isArray(value) ? value.map(asStatement) : [];
}
function extensionLabel(stmt) {
  return `${stmt.prefix}:${stmt.resolved_extension_name}`;
}
function rejectSemanticExtension(stmt) {
  const owner = stmt.resolved_module_name ?? "";
  const ext2 = stmt.resolved_extension_name ?? "";
  if (owner === "ietf-yang-structure-ext" && (ext2 === "structure" || ext2 === "augment-structure")) {
    return;
  }
  if (stmt.has_apply_callback === true) {
    throw new YangExportError(
      `cannot export extension invocation '${extensionLabel(stmt)}': extension ${owner}:${ext2} is applied when the module is parsed and is not re-applied when the native JSON form is loaded`
    );
  }
}
function lookupImportedModule(root, name) {
  for (const imported of Object.values(root.import_prefixes)) {
    if (imported.name === name) {
      return imported;
    }
  }
  return root.module_registry?.[name];
}
function recordImportedExtension(stmt, root) {
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
function extensionDefJson(ext2) {
  const raw = asRecord(ext2);
  const out = {};
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
function oneExtensionInvocation(stmt, module, typedefNames) {
  rejectSemanticExtension(stmt);
  recordImportedExtension(stmt, module);
  const out = { name: extensionLabel(stmt) };
  if (typeof stmt.argument === "string") {
    out[XYANG_KEYS.argument] = stmt.argument;
  }
  if (typeof stmt.description === "string" && stmt.description.length > 0) {
    out.description = stmt.description;
  }
  if (typeof stmt.reference === "string" && stmt.reference.length > 0) {
    out[XYANG_KEYS.reference] = stmt.reference;
  }
  const features = Array.isArray(stmt.if_features) ? stmt.if_features.filter((item) => typeof item === "string" && item.trim().length > 0) : [];
  if (features.length > 0) {
    out["if-features"] = features;
  }
  const whenShape = asRecord(stmt.when);
  const whenExpression = typeof whenShape.expression === "string" ? whenShape.expression : "";
  if (whenExpression.trim().length > 0) {
    const whenOut = {
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
  const body = [];
  for (const child2 of stmt.statements ?? []) {
    if (child2.keyword === YangTokenType.MUST) {
      continue;
    }
    if (isExtensionInvocation(child2)) {
      body.push({ [XYANG_KEYS.extension]: oneExtensionInvocation(child2, module, typedefNames) });
      continue;
    }
    if (isSchemaDataNode(child2) && child2.keyword !== YangTokenType.CASE) {
      body.push({
        node: propertyKey(child2, module),
        schema: statementToSchema(child2, module, typedefNames)
      });
      continue;
    }
    throw new YangExportError(
      `cannot export extension invocation '${extensionLabel(stmt)}': nested statement ${child2.keyword ?? ""} '${child2.name ?? ""}' is not representable in the native JSON form`
    );
  }
  if (body.length > 0) {
    out[XYANG_KEYS.body] = body;
  }
  return out;
}
function extensionInvocationsJson(statements, module, typedefNames) {
  return statements.filter(isExtensionInvocation).map((stmt) => oneExtensionInvocation(stmt, module, typedefNames));
}
function stampExtensions(xyang, statements, module, typedefNames) {
  const invocations = extensionInvocationsJson(statements, module, typedefNames);
  if (invocations.length > 0) {
    xyang[XYANG_KEYS.extensions] = invocations;
  }
}
function ownPrefixOf(module) {
  return String(module.prefix ?? "").replace(/^['"]|['"]$/g, "");
}
function extensionImportKey(root, module) {
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
function localExtensionDefs(module) {
  const out = {};
  for (const [name, ext2] of Object.entries(module.extensions ?? {})) {
    out[name] = extensionDefJson(ext2);
  }
  return out;
}
function mergeExtensionImports(root, imports, used) {
  const byOwner = /* @__PURE__ */ new Map();
  for (const item of used) {
    const key2 = item.owner.name ?? "";
    const bucket = byOwner.get(key2) ?? { owner: item.owner, names: [] };
    if (!bucket.names.includes(item.name)) {
      bucket.names.push(item.name);
    }
    byOwner.set(key2, bucket);
  }
  for (const { owner, names } of byOwner.values()) {
    const key2 = extensionImportKey(root, owner);
    const stub2 = asRecord(imports[key2]);
    if (!imports[key2]) {
      imports[key2] = {
        module: owner.name,
        namespace: owner.namespace ?? "",
        prefix: owner.prefix ?? ""
      };
    }
    const target = asRecord(imports[key2]);
    if (Object.keys(stub2).length === 0 && imports[key2] !== target) {
      Object.assign(target, stub2);
    }
    const extMap = {};
    for (const name of [...names].sort()) {
      const ext2 = (owner.extensions ?? {})[name];
      if (!ext2) {
        throw new YangExportError(
          `cannot export extension ${owner.name}:${name}: the extension definition is not in that module`
        );
      }
      extMap[name] = extensionDefJson(ext2);
    }
    target[XYANG_KEYS.extension] = extMap;
  }
  return Object.fromEntries(Object.entries(imports).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0));
}
var PLACED_KEYWORDS = /* @__PURE__ */ new Set([
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
function findExtensionInvocation(stmt) {
  if (isExtensionInvocation(stmt)) {
    return stmt;
  }
  for (const child2 of stmt.statements ?? []) {
    const found = findExtensionInvocation(child2);
    if (found) {
      return found;
    }
  }
  return void 0;
}
function assertExtensionsPlaced(module) {
  const walk = (owner, placed) => {
    for (const child2 of owner.statements ?? []) {
      if (isExtensionInvocation(child2)) {
        rejectSemanticExtension(child2);
        if (!placed) {
          throw new YangExportError(
            `cannot export extension invocation '${extensionLabel(child2)}': it is on ${owner.keyword ?? ""} '${owner.name ?? ""}', which the native JSON form does not carry`
          );
        }
        walk(child2, true);
        continue;
      }
      if (child2.keyword === "grouping" || child2.keyword === YangTokenType.EXTENSION) {
        continue;
      }
      if (child2.keyword === YangTokenType.USES) {
        const found = findExtensionInvocation(child2);
        if (found) {
          throw new YangExportError(
            `cannot export extension invocation '${extensionLabel(found)}': it is inside uses '${child2.argument ?? child2.name ?? ""}', which the native JSON form does not carry`
          );
        }
        continue;
      }
      walk(child2, PLACED_KEYWORDS.has(child2.keyword ?? ""));
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
          `cannot export extension invocation '${extensionLabel(found)}': it is inside uses '${stmt.argument ?? stmt.name ?? ""}', which the native JSON form does not carry`
        );
      }
      continue;
    }
    walk(stmt, PLACED_KEYWORDS.has(stmt.keyword ?? ""));
  }
  for (const raw of Object.values(module.identities)) {
    for (const stmt of statementListOf(raw.statements)) {
      if (!isExtensionInvocation(stmt)) {
        continue;
      }
      rejectSemanticExtension(stmt);
      walk(stmt, true);
    }
  }
}
function pathHasPredicate(path) {
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
    return s.predicate !== void 0 && s.predicate !== null;
  });
}
function pathText(path) {
  if (typeof path === "string") {
    return path;
  }
  const shape = asRecord(path);
  if (shape.kind !== "path") {
    return "";
  }
  if (typeof shape.source === "string") return shape.source;
  const segmentsRaw = Array.isArray(shape.segments) ? shape.segments : [];
  const segments = segmentsRaw.map((seg) => asRecord(seg).step).filter((step) => typeof step === "string" && step.length > 0);
  if (segments.length === 0) {
    return "";
  }
  const absolute = shape.isAbsolute === true;
  return `${absolute ? "/" : ""}${segments.join("/")}`;
}
function xpathPrefixesEntry(recorded) {
  if (!recorded || typeof recorded !== "object" || Object.keys(recorded).length === 0) {
    return {};
  }
  const sorted = Object.keys(recorded).sort().map((prefix) => [prefix, recorded[prefix]]);
  return { [XYANG_KEYS.xpathPrefixes]: Object.fromEntries(sorted) };
}
function propertyKey(stmt, module) {
  const owner = stmt.defining_module;
  return owner && owner !== module.name ? `${owner}:${stmt.name}` : stmt.name ?? "";
}
function mustToXYang(stmt) {
  const out = [];
  for (const child2 of stmt.statements) {
    if (child2.keyword !== YangTokenType.MUST || typeof child2.argument !== "string") {
      continue;
    }
    const entry = {
      must: child2.argument,
      "error-message": typeof child2.error_message === "string" ? child2.error_message : "",
      ...typeof child2.error_app_tag === "string" && child2.error_app_tag.length > 0 ? { "error-app-tag": child2.error_app_tag } : {},
      ...xpathPrefixesEntry(child2.xpath_prefixes)
    };
    withDescription(entry, child2.description);
    out.push(entry);
  }
  return out;
}
function explicitConfig(stmt) {
  const cfg = stmt.config;
  return typeof cfg === "boolean" ? cfg : void 0;
}
function withStatementMeta(stmt, meta, module, typedefNames) {
  const out = { ...meta };
  const config = explicitConfig(stmt);
  if (config !== void 0) {
    out[XYANG_KEYS.config] = config;
  }
  const ifFeatures = Array.isArray(stmt.if_features) ? stmt.if_features.filter((x) => typeof x === "string" && x.trim().length > 0) : [];
  if (ifFeatures.length > 0) {
    out["if-features"] = ifFeatures;
  }
  if (typeof stmt.units === "string" && stmt.units) out.units = stmt.units;
  const whenShape = asRecord(stmt.when);
  const whenExpression = typeof whenShape.expression === "string" ? whenShape.expression : "";
  if (whenExpression.trim().length > 0) {
    const whenOut = {
      condition: whenExpression,
      ...xpathPrefixesEntry(whenShape.xpath_prefixes)
    };
    const wd = typeof whenShape.description === "string" && whenShape.description.trim().length > 0 ? whenShape.description.trim() : "";
    if (wd.length > 0) {
      whenOut.description = wd;
    }
    if (whenShape.evaluate_with_parent_context === true) {
      whenOut["evaluate-with-parent-context"] = true;
    }
    out.when = whenOut;
  }
  const augmentStructure = stmt.augment_structure;
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
function resolveAbsoluteLeafTypePath(module, path) {
  if (pathHasPredicate(path)) {
    return void 0;
  }
  let segments;
  if (typeof path === "string") {
    if (!path.startsWith("/")) {
      return void 0;
    }
    segments = path.split("/").map((x) => x.trim()).filter(Boolean);
  } else {
    const shape = asRecord(path);
    if (shape.kind !== "path" || shape.isAbsolute !== true) {
      return void 0;
    }
    const segmentsRaw = Array.isArray(shape.segments) ? shape.segments : [];
    segments = segmentsRaw.map((seg) => asRecord(seg).step).filter((step) => typeof step === "string" && step.length > 0);
  }
  if (segments.length === 0) {
    return void 0;
  }
  let level = module.statements;
  let current;
  for (const seg of segments) {
    const name = parseIdentifierRefAtom(seg).name;
    current = level.find((stmt) => stmt.name === name);
    if (!current) {
      return void 0;
    }
    level = current.statements;
  }
  if (current?.keyword !== YangTokenType.LEAF) {
    return void 0;
  }
  return asRecord(current.type);
}
function foreignTypedefResolved(typeShape, module) {
  if (resolveTypedef(module, typeShape)?.scope !== void 0) return typeShape;
  let current = typeShape;
  for (let depth = 0; depth < 64; depth += 1) {
    const typeName = typeof current.name === "string" ? current.name : "";
    const prefix = typeof current.prefix === "string" && current.prefix ? current.prefix : void 0;
    const scope = typeof current.scope_module === "string" ? current.scope_module : void 0;
    const foreign = prefix !== void 0 || scope !== void 0 && scope !== module.name;
    if (!foreign || !prefix && Object.prototype.hasOwnProperty.call(REGISTRY, typeName)) {
      return current;
    }
    const label = prefix ? `${prefix}:${typeName}` : typeName;
    const typedef = resolveTypedef(module, current);
    if (!typedef?.type) {
      throw new YangExportError(`cannot export type '${label}': its typedef is not found where the type is written`);
    }
    if (current.range || current.length || Array.isArray(current.patterns) && current.patterns.length > 0) {
      throw new YangExportError(`cannot export restrictions on the imported typedef '${label}' in the native JSON form`);
    }
    current = typedef.type;
  }
  return current;
}
var scopedExportDefs = {};
var defsRef = (name) => `#/$defs/${encodeURIComponent(name.replace(/~/g, "~0").replace(/\//g, "~1"))}`;
function scopedCatalog(module) {
  const out = {};
  const seen = /* @__PURE__ */ new Set();
  const collect = (current) => {
    if (seen.has(current)) return;
    seen.add(current);
    for (const [key2, value] of Object.entries(current.typedefs)) {
      const td = value;
      if (td.scope !== void 0) {
        const exported = current === module ? key2 : `@${current.name}:${key2}`;
        if (exported in out) throw new YangExportError(`Conflicting scoped typedef key '${exported}'`);
        out[exported] = { td, owner: current, key: key2 };
      }
    }
    for (const imported of Object.values(current.import_prefixes)) collect(imported);
  };
  collect(module);
  return out;
}
function scopedTypeSchema(type, module) {
  const td = resolveTypedef(module, type);
  if (td?.scope === void 0) return void 0;
  if (type.range || type.length || Array.isArray(type.patterns) && type.patterns.length) throw new YangExportError(`cannot export restrictions on scoped typedef '${td.name}' in the native JSON form`);
  const writer = typeof type.scope_module === "string" ? type.scope_module : module.name;
  const source = writer === module.name ? module : module.module_registry?.[String(writer)];
  const storageKey = Object.entries(source?.typedefs ?? {}).find(([, value]) => value === td)?.[0];
  const found = Object.entries(scopedExportDefs).find(([, entry]) => entry.owner.name === writer && entry.key === storageKey);
  if (!found) throw new YangExportError(`Scoped typedef '${td.name}' is absent from the export catalog`);
  return { $ref: defsRef(found[0]), [YANG_SCHEMA_KEYS.xYang]: { "type-context": type.context ?? "" } };
}
function typedefRefOrInline(typeShape, typedefNames, module) {
  const scoped = scopedTypeSchema(typeShape, module);
  if (scoped) return scoped;
  const typeName = typeof typeShape.name === "string" ? typeShape.name : "";
  const prefix = typeof typeShape.prefix === "string" && typeShape.prefix ? typeShape.prefix : void 0;
  const scope = typeof typeShape.scope_module === "string" ? typeShape.scope_module : void 0;
  const local2 = !prefix && (scope === void 0 || scope === module.name);
  if (local2 && typedefNames.has(typeName)) {
    return { $ref: defsRef(typeName) };
  }
  if (!prefix && Object.prototype.hasOwnProperty.call(REGISTRY, typeName)) {
    if (typeName === "union") return { oneOf: (typeShape.types ?? []).map((member) => typedefRefOrInline(member, typedefNames, module)) };
    return leafTypeToSchema(typeShape, exportNativeJson);
  }
  const label = prefix ? `${prefix}:${typeName}` : typeName;
  const typedef = resolveTypedef(module, typeShape);
  if (!typedef?.type) {
    throw new YangExportError(`cannot export type '${label}': its typedef is not found where the type is written`);
  }
  if (typeShape.range || typeShape.length || Array.isArray(typeShape.patterns) && typeShape.patterns.length > 0) {
    throw new YangExportError(`cannot export restrictions on the imported typedef '${label}' in the native JSON form`);
  }
  return typedefRefOrInline(typedef.type, /* @__PURE__ */ new Set(), module);
}
function partitionChoiceSiblings(children2) {
  const choices = children2.filter((c) => c.keyword === YangTokenType.CHOICE);
  const others = children2.filter((c) => c.keyword !== YangTokenType.CHOICE);
  if (choices.length === 1) {
    return { others, soleChoice: choices[0] };
  }
  return { others: children2, soleChoice: void 0 };
}
function mergeOneOfBranchesWithBase(oneOf, baseProps, baseRequired) {
  const merged = [];
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
    const br = Array.isArray(branch.required) ? branch.required.filter((x) => typeof x === "string") : [];
    const mergedBranch = {
      type: JSON_TYPE_OBJECT,
      properties: { ...baseProps, ...bp },
      required: [.../* @__PURE__ */ new Set([...baseRequired, ...br])].sort(),
      additionalProperties: false
    };
    const bDesc = branch.description;
    if (typeof bDesc === "string" && bDesc.length > 0) {
      mergedBranch.description = bDesc;
    }
    const bXy = branch[YANG_SCHEMA_KEYS.xYang];
    if (bXy && typeof bXy === "object" && !Array.isArray(bXy) && Object.keys(bXy).length > 0) {
      mergedBranch[YANG_SCHEMA_KEYS.xYang] = { ...bXy };
    }
    merged.push(mergedBranch);
  }
  return merged;
}
function choiceMetaForXYang(choice, module, typedefNames) {
  const meta = {
    name: choice.name ?? "",
    mandatory: choice.mandatory === true
  };
  withDescription(meta, choice.description);
  const ifFeatures = Array.isArray(choice.if_features) ? choice.if_features.filter((x) => typeof x === "string" && x.trim().length > 0) : [];
  if (ifFeatures.length > 0) {
    meta["if-features"] = ifFeatures;
  }
  stampExtensions(meta, choice.statements ?? [], module, typedefNames);
  return meta;
}
function buildSoleChoiceObjectSchema(others, soleChoice, module, typedefNames, keyNames2 = []) {
  const properties = {};
  const required = [];
  for (const child2 of others) {
    if (!child2.name || !isSchemaDataNode(child2)) {
      continue;
    }
    properties[propertyKey(child2, module)] = statementToSchema(child2, module, typedefNames);
    if (hasTokenType(child2.keyword ?? "", [YangTokenType.LEAF, YangTokenType.ANYDATA, YangTokenType.ANYXML]) && (child2.mandatory === true || keyNames2.includes(child2.name ?? ""))) {
      required.push(propertyKey(child2, module));
    }
  }
  const choiceShape = buildChoiceOneOf(soleChoice, module, typedefNames);
  const oneOfArr = choiceShape?.oneOf ?? [];
  if (Object.keys(properties).length === 0 && required.length === 0) {
    return { type: JSON_TYPE_OBJECT, oneOf: oneOfArr };
  }
  return {
    type: JSON_TYPE_OBJECT,
    oneOf: mergeOneOfBranchesWithBase(oneOfArr, properties, required)
  };
}
function ioBlockToSchema(stmt, module, typedefNames, ioType) {
  const body = buildMultiChildObjectSchema(stmt.statements, module, typedefNames);
  const out = {
    ...body,
    [YANG_SCHEMA_KEYS.xYang]: withStatementMeta(stmt, { type: ioType }, module, typedefNames)
  };
  withDescription(out, stmt.description);
  return out;
}
function rpcToJson(stmt, module, typedefNames, kind = YangTokenType.RPC) {
  const out = {
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
function buildMultiChildObjectSchema(statements, module, typedefNames, keyNames2 = []) {
  const properties = {};
  const required = [];
  for (const child2 of statements) {
    if (child2.keyword === YangTokenType.CHOICE) {
      if (!child2.name) {
        continue;
      }
      properties[child2.name] = statementToSchema(child2, module, typedefNames);
      continue;
    }
    if (!child2.name || !isSchemaDataNode(child2)) {
      continue;
    }
    properties[propertyKey(child2, module)] = statementToSchema(child2, module, typedefNames);
    if (hasTokenType(child2.keyword ?? "", [YangTokenType.LEAF, YangTokenType.ANYDATA, YangTokenType.ANYXML]) && (child2.mandatory === true || keyNames2.includes(child2.name ?? ""))) {
      required.push(propertyKey(child2, module));
    }
  }
  const out = {
    type: JSON_TYPE_OBJECT,
    properties,
    additionalProperties: false
  };
  if (required.length > 0) {
    out.required = required;
  }
  return out;
}
function buildChoiceOneOf(choice, module, typedefNames) {
  const branches = [];
  const cases = choice.statements.filter((stmt) => stmt.keyword === YangTokenType.CASE);
  const mandatory = choice.mandatory === true;
  if (!mandatory) {
    branches.push({ type: JSON_TYPE_OBJECT, maxProperties: 0 });
  }
  for (const c of cases) {
    const properties = {};
    const required = [];
    for (const child2 of c.statements) {
      if (!child2.name || !isSchemaDataNode(child2)) {
        continue;
      }
      properties[propertyKey(child2, module)] = statementToSchema(child2, module, typedefNames);
      required.push(propertyKey(child2, module));
    }
    if (Object.keys(properties).length === 0) {
      continue;
    }
    const branch = {
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
    return void 0;
  }
  return {
    oneOf: branches
  };
}
function statementToSchema(stmt, module, typedefNames) {
  const out = statementToSchemaBody(stmt, module, typedefNames);
  if (stmt.keyword !== YangTokenType.CONTAINER && stmt.keyword !== YangTokenType.LIST) {
    return out;
  }
  const actions = {};
  for (const child2 of stmt.statements) {
    if (child2.keyword === YangTokenType.ACTION && child2.name) {
      actions[propertyKey(child2, module)] = rpcToJson(child2, module, typedefNames, YangTokenType.ACTION);
    }
  }
  if (Object.keys(actions).length > 0) {
    asRecord(out[YANG_SCHEMA_KEYS.xYang])[XYANG_KEYS.actions] = actions;
  }
  return out;
}
function statementToSchemaBody(stmt, module, typedefNames) {
  const keyword = stmt.keyword ?? "";
  if (keyword === YangTokenType.CHOICE) {
    const oneOfShape = buildChoiceOneOf(stmt, module, typedefNames);
    const xyChoice = {
      type: "choice",
      mandatory: stmt.mandatory === true
    };
    const choiceConfig = explicitConfig(stmt);
    if (choiceConfig !== void 0) {
      xyChoice[XYANG_KEYS.config] = choiceConfig;
    }
    const ifFeatures = Array.isArray(stmt.if_features) ? stmt.if_features.filter((x) => typeof x === "string" && x.trim().length > 0) : [];
    if (ifFeatures.length > 0) {
      xyChoice["if-features"] = ifFeatures;
    }
    stampExtensions(xyChoice, stmt.statements ?? [], module, typedefNames);
    const choiceAugment = stmt.augment_structure;
    if (typeof choiceAugment === "string" && choiceAugment.length > 0) {
      xyChoice["augment-structure"] = choiceAugment;
    }
    const out = {
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
    const xYang = withStatementMeta(stmt, { type: keyword }, module, typedefNames);
    if (soleChoice) {
      xYang.choice = choiceMetaForXYang(soleChoice, module, typedefNames);
    }
    const body = soleChoice ? buildSoleChoiceObjectSchema(others, soleChoice, module, typedefNames) : buildMultiChildObjectSchema(stmt.statements, module, typedefNames);
    const out = {
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
      key: typeof stmt.key === "string" ? stmt.key : void 0
    }, module, typedefNames);
    if (soleChoice) {
      listXY.choice = choiceMetaForXYang(soleChoice, module, typedefNames);
    }
    const unique = stmt.unique;
    if (Array.isArray(unique) && unique.length > 0) {
      listXY.unique = unique.map((paths) => [...paths]);
    }
    const keys = typeof stmt.key === "string" ? stmt.key.trim().split(/\s+/).filter(Boolean) : [];
    const itemSchema = soleChoice ? buildSoleChoiceObjectSchema(others, soleChoice, module, typedefNames, keys) : buildMultiChildObjectSchema(stmt.statements, module, typedefNames, keys);
    const out = {
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
    const typeName = typeShape.name ?? YangTokenType.STRING_KW;
    const out = {
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
    const llDefaults = stmt.defaults;
    if (Array.isArray(llDefaults) && llDefaults.length > 0) {
      out.default = llDefaults;
    }
    return out;
  }
  if (keyword === YangTokenType.LEAF) {
    const typeShape = foreignTypedefResolved(asRecord(stmt.type), module);
    const typeName = typeShape.name ?? YangTokenType.STRING_KW;
    let leafSchema = typedefRefOrInline(typeShape, typedefNames, module);
    if (typeName === YangTokenType.LEAFREF) {
      const targetType = resolveAbsoluteLeafTypePath(module, typeShape.path);
      leafSchema = targetType ? typedefRefOrInline(targetType, typedefNames, module) : leafTypeToSchema({ name: YangTokenType.STRING_KW });
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
      const bases = Array.isArray(typeShape.identityref_bases) ? typeShape.identityref_bases.map((b) => coerceIdentifierRef(b)).filter((b) => Boolean(b)).map((b) => formatIdentifierRef(b)) : [];
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
    const out = {
      ...leafSchemaRest,
      [YANG_SCHEMA_KEYS.xYang]: { ...xYang, ...schemaXy, ...typeName === YangTokenType.LEAFREF ? { type: YangTokenType.LEAFREF } : {} }
    };
    withDescription(out, stmt.description);
    if (stmt.default !== void 0) {
      const schemaType = typeof out.type === "string" ? out.type : null;
      out.default = jsonSchemaDefaultValue(stmt.default, {
        yangTypeName: typeName,
        jsonSchemaType: schemaType
      });
    }
    return out;
  }
  if (keyword === YangTokenType.ANYDATA || keyword === YangTokenType.ANYXML) {
    const out = {
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
function typedefToSchema(module, entries = module.typedefs) {
  const out = {};
  const typedefs = entries;
  const names = new Set(Object.keys(typedefs));
  for (const [name, entry] of Object.entries(typedefs)) {
    const typeShape = asRecord(entry.type);
    const schema = typedefRefOrInline(typeShape, names, module);
    const { description: _typedefTypeDescription, ...schemaRest } = schema;
    const def = {
      ...schemaRest
    };
    withDescription(def, entry.description);
    const schemaXy = asRecord(schema[YANG_SCHEMA_KEYS.xYang]);
    const typedefXy = {};
    if (typeShape.name === YangTokenType.LEAFREF) {
      Object.assign(typedefXy, {
        type: YangTokenType.LEAFREF,
        path: pathText(typeShape.path),
        "require-instance": typeShape.require_instance !== false,
        ...xpathPrefixesEntry(typeShape.xpath_prefixes)
      });
    }
    const rawPatList = Array.isArray(typeShape.patterns) ? typeShape.patterns : [];
    const lastPat = rawPatList.length > 0 ? rawPatList[rawPatList.length - 1] : null;
    if (lastPat && typeof lastPat.error_message === "string" && lastPat.error_message.length > 0) {
      typedefXy["pattern-error-message"] = lastPat.error_message;
    }
    if (lastPat && typeof lastPat.error_app_tag === "string" && lastPat.error_app_tag.length > 0) {
      typedefXy["pattern-error-app-tag"] = lastPat.error_app_tag;
    }
    if (Object.keys(schemaXy).length > 0 || Object.keys(typedefXy).length > 0) {
      def[YANG_SCHEMA_KEYS.xYang] = { ...schemaXy, ...typedefXy };
    }
    const invocations = extensionInvocationsJson(statementListOf(entry.statements), module, names);
    if (invocations.length > 0) {
      const xy = asRecord(def[YANG_SCHEMA_KEYS.xYang]);
      xy[XYANG_KEYS.extensions] = invocations;
      def[YANG_SCHEMA_KEYS.xYang] = xy;
    }
    const scoped = entry;
    if (scoped.scope !== void 0) {
      def[YANG_SCHEMA_KEYS.xYang] = { ...asRecord(def[YANG_SCHEMA_KEYS.xYang]), scope: scoped.scope, name: scoped.name, ...scoped.units ? { units: scoped.units } : {} };
      const defaultValue2 = entry.default;
      if (defaultValue2 !== void 0) def.default = jsonSchemaDefaultValue(defaultValue2, { yangTypeName: String(typeShape.name), jsonSchemaType: typeof def.type === "string" ? def.type : null });
    }
    out[name] = def;
  }
  return out;
}
function scopedTypedefsToSchema() {
  const out = {};
  for (const [key2, { td, owner }] of Object.entries(scopedExportDefs)) {
    Object.assign(out, typedefToSchema(owner, { [key2]: td }));
  }
  return out;
}
function identityToSchema(module, typedefNames) {
  const defs = {};
  for (const identityName of Object.keys(module.identities)) {
    const def = identityDef(module, identityName);
    const raw = module.identities[identityName];
    const invocations = extensionInvocationsJson(statementListOf(raw?.statements), module, typedefNames);
    if (invocations.length > 0) {
      asRecord(def[YANG_SCHEMA_KEYS.xYang])[XYANG_KEYS.extensions] = invocations;
    }
    defs[identityName] = def;
  }
  return defs;
}
function applyOwnAugments(effective) {
  for (const stmt of effective.statements) {
    if (stmt.keyword !== YangTokenType.AUGMENT) {
      continue;
    }
    const path = String(stmt.augment_path ?? stmt.argument ?? "");
    const first = (Array.isArray(stmt.augment_path_segments) && stmt.augment_path_segments.length > 0 ? stmt.augment_path_segments : parseAbsoluteSchemaPath(path))[0];
    const own = String(effective.prefix ?? "").replace(/^['"]|['"]$/g, "");
    if (first?.prefix !== own) {
      throw new YangExportError(
        `cannot export augment '${path}': its target belongs to another module, which the native JSON form of module '${effective.name}' does not carry`
      );
    }
  }
  applyAugments(effective);
}
function applyOwnDeviations(effective) {
  for (const stmt of effective.statements) {
    if (stmt.keyword !== "deviation") {
      continue;
    }
    const path = String(stmt.deviation_path ?? stmt.argument ?? "");
    const first = (Array.isArray(stmt.deviation_path_segments) && stmt.deviation_path_segments.length > 0 ? stmt.deviation_path_segments : parseAbsoluteSchemaPath(path))[0];
    const own = String(effective.prefix ?? "").replace(/^['"]|['"]$/g, "");
    if (first?.prefix !== own) {
      throw new YangExportError(
        `cannot export deviation '${path}': its target belongs to another module, which the native JSON form of module '${effective.name}' does not carry`
      );
    }
  }
  applyDeviations(effective);
}
var FOREIGN_AUGMENTS2 = "ietf-yang-structure-ext:foreign-augment-structure";
var FOREIGN_SLOTS2 = "ietf-yang-structure-ext:foreign-augment-structure-slots";
var STRUCTURE_INDEX2 = "ietf-yang-structure-ext:structure-index";
function isRfc8791(stmt, name) {
  return stmt.resolved_module_name === "ietf-yang-structure-ext" && stmt.resolved_extension_name === name;
}
function foreignAugmentsOf(module) {
  const raw = module.extension_runtime?.[FOREIGN_AUGMENTS2];
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.map((item) => item instanceof YangStatement ? item : new YangStatement(asRecord(item)));
}
function foreignSlotsOf(module) {
  const raw = module.extension_runtime?.[FOREIGN_SLOTS2];
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((item) => typeof item === "number");
}
function orderedExtensionInvocations(module, typedefNames) {
  const kept = extensionInvocationsJson(module.statements, module, typedefNames);
  const foreign = foreignAugmentsOf(module);
  const slots = foreignSlotsOf(module);
  if (foreign.length === 0) {
    return kept;
  }
  const groups = /* @__PURE__ */ new Map();
  foreign.forEach((inv, index) => {
    const slot = slots[index] ?? kept.length;
    const list = groups.get(slot) ?? [];
    list.push(oneExtensionInvocation(inv, module, typedefNames));
    groups.set(slot, list);
  });
  const ordered = [];
  kept.forEach((item, index) => {
    ordered.push(...groups.get(index) ?? []);
    groups.delete(index);
    ordered.push(item);
  });
  ordered.push(...groups.get(kept.length) ?? []);
  groups.delete(kept.length);
  for (const slot of [...groups.keys()].sort((a, b) => a - b)) {
    ordered.push(...groups.get(slot) ?? []);
  }
  return ordered;
}
function structureInvocations(module) {
  const found = [];
  const seen = /* @__PURE__ */ new Set();
  for (const stmt of module.statements) {
    if (isRfc8791(stmt, "structure")) {
      found.push(stmt);
      seen.add(stmt);
    }
  }
  const index = asRecord(module.extension_runtime?.[STRUCTURE_INDEX2]);
  for (const stmt of Object.values(index)) {
    if (stmt instanceof YangStatement && !seen.has(stmt) && isRfc8791(stmt, "structure")) {
      found.push(stmt);
    }
  }
  return found;
}
function structureView(module) {
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
function extensionStub(module) {
  return {
    module: module.name,
    namespace: module.namespace ?? "",
    prefix: module.prefix ?? "",
    [XYANG_KEYS.extension]: localExtensionDefs(module)
  };
}
function stripAugmentedBy(stmt, exporterName) {
  if (stmt.augment_structure_module === exporterName) {
    return void 0;
  }
  const cloned = new YangStatement(JSON.parse(JSON.stringify(stmt)));
  cloned.statements = cloned.statements.map((child2) => stripAugmentedBy(child2, exporterName)).filter((child2) => child2 !== void 0);
  return cloned;
}
function addImportedStructures(root, imports) {
  const seen = /* @__PURE__ */ new Set();
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
    const key2 = extensionImportKey(root, owner);
    if (!imports[key2]) {
      imports[key2] = {
        module: owner.name,
        namespace: owner.namespace ?? "",
        prefix: owner.prefix ?? ""
      };
    }
    const stub2 = asRecord(imports[key2]);
    const view = structureView(owner);
    for (const structure of structureInvocations(view)) {
      const marker = `${key2}:${String(structure.argument ?? "").trim()}`;
      if (seen.has(marker) || marker.endsWith(":") && !firstName) {
        continue;
      }
      seen.add(marker);
      const shadow = new YangStatement(JSON.parse(JSON.stringify(structure)));
      shadow.statements = structure.statements.map((child2) => stripAugmentedBy(child2, root.name ?? "")).filter((child2) => child2 !== void 0);
      const body = oneExtensionInvocation(shadow, root, /* @__PURE__ */ new Set());
      const list = Array.isArray(stub2[XYANG_KEYS.extensions]) ? stub2[XYANG_KEYS.extensions] : [];
      list.push(body);
      stub2[XYANG_KEYS.extensions] = list;
      const prefix = structure.prefix ?? "";
      const definingName = structure.resolved_module_name ?? "";
      const defining = prefix ? owner.import_prefixes?.[prefix] : void 0;
      if (defining && prefix) {
        const nested = asRecord(stub2[XYANG_KEYS.imports]);
        if (!nested[prefix]) {
          nested[prefix] = extensionStub(defining);
        }
        stub2[XYANG_KEYS.imports] = nested;
      } else if (definingName && prefix) {
        const nested = asRecord(stub2[XYANG_KEYS.imports]);
        if (!nested[prefix]) {
          nested[prefix] = {
            module: definingName,
            namespace: "",
            prefix
          };
        }
        stub2[XYANG_KEYS.imports] = nested;
      }
    }
  }
}
function featuresJson(module) {
  const names = [...module.features].sort();
  if (names.length === 0) {
    return {};
  }
  const out = {};
  for (const name of names) {
    const body = {};
    const guards = module.feature_if_features?.[name] ?? [];
    if (guards.length > 0) {
      body["if-features"] = [...guards];
    }
    out[name] = body;
  }
  return out;
}
var exportNativeJson = false;
function generateJsonSchema(module, options = {}) {
  const previousNative = exportNativeJson;
  const previous = extensionUses;
  const previousScoped = scopedExportDefs;
  scopedExportDefs = scopedCatalog(module);
  extensionUses = [];
  exportNativeJson = options.nativeJson === true;
  try {
    let effective;
    const schema = withIdentityExport(module, (used) => generateSchema(module, used, (value) => {
      effective = value;
    }));
    if (options.schemaId !== void 0) schema.$id = options.schemaId;
    annotateSchema(schema, options);
    if (!options.path) {
      if (options.features != null) throw new YangExportError("features requires a subtree path");
      return { schema, diagnostics: [] };
    }
    const overrides = {};
    if (options.features != null) {
      if (typeof options.features !== "object" || Array.isArray(options.features)) throw new TypeError("features must map module names to arrays of feature names");
      for (const [name, features] of Object.entries(options.features)) {
        if (!Array.isArray(features) || features.some((feature) => typeof feature !== "string")) throw new TypeError(`features[${name}] must be an array of feature names`);
        overrides[name] = new Set(features);
      }
    }
    const enabled = buildEnabledFeaturesMap(module, overrides);
    let filteredModule;
    extensionUses = [];
    const filtered = withIdentityExport(module, (used) => generateSchema(module, used, (value) => {
      filteredModule = value;
      const filter = (statements) => statements.filter((stmt) => {
        const imported = reachableModuleData(value).filter((other) => other.name !== value.name);
        for (const expression of stmt.if_features ?? []) {
          for (const token of expression.match(/[A-Za-z_][A-Za-z0-9_.:-]*/g) ?? []) {
            if (!["and", "or", "not"].includes(token) && !token.includes(":") && imported.some((other) => other.features.has(token))) {
              throw new YangExportError(`cannot safely resolve unqualified if-feature '${token}' shared with an imported module`);
            }
          }
        }
        const owner = stmt.defining_module && stmt.defining_module !== value.name ? value.module_registry?.[stmt.defining_module] ?? value : value;
        if (!stmtIfFeaturesSatisfied(stmt.if_features, owner, enabled, stmt.included_from)) return false;
        stmt.statements = filter(stmt.statements ?? []);
        return true;
      });
      value.statements = filter(value.statements);
    }));
    annotateSchema(filtered, options);
    if (options.schemaId !== void 0) filtered.$id = options.schemaId;
    restrictGatedValues(filtered, module, enabled);
    const projected = projectSubtree(schema, filteredModule ?? effective ?? module, options.path, options.nativeJson === true, filtered);
    restrictGatedValues(projected.schema, module, enabled);
    return projected;
  } finally {
    exportNativeJson = previousNative;
    extensionUses = previous;
    scopedExportDefs = previousScoped;
  }
}
function generateSchema(module, used, onEffective) {
  const effectiveModule = expandUses(module);
  if (effectiveModule !== module && module.module_registry && !effectiveModule.module_registry) {
    Object.defineProperty(effectiveModule, "module_registry", { value: module.module_registry, enumerable: false });
  }
  applyOwnAugments(effectiveModule);
  applyOwnDeviations(effectiveModule);
  applyBuiltinExtensionInvocations(effectiveModule, { exportView: true });
  onEffective?.(effectiveModule);
  const properties = {};
  const required = [];
  const typedefNames = new Set(Object.keys(effectiveModule.typedefs));
  for (const stmt of effectiveModule.statements) {
    if (!stmt.name) {
      continue;
    }
    if (!hasTokenType(stmt.keyword ?? "", [
      YangTokenType.CONTAINER,
      YangTokenType.LIST,
      YangTokenType.LEAF,
      YangTokenType.LEAF_LIST,
      YangTokenType.ANYDATA,
      YangTokenType.ANYXML
    ])) {
      continue;
    }
    properties[propertyKey(stmt, module)] = statementToSchema(stmt, effectiveModule, typedefNames);
    if (hasTokenType(stmt.keyword ?? "", [YangTokenType.LEAF, YangTokenType.ANYDATA, YangTokenType.ANYXML]) && stmt.mandatory === true) {
      required.push(propertyKey(stmt, module));
    }
  }
  const rootXYang = {
    module: effectiveModule.name,
    "yang-version": effectiveModule.yangVersion ?? "1.1",
    namespace: effectiveModule.namespace,
    prefix: effectiveModule.prefix,
    organization: effectiveModule.organization ?? "",
    contact: effectiveModule.contact ?? ""
  };
  const rpcs = {};
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
  const sortedImports = Object.fromEntries(Object.entries(imports).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0));
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
  const schema = {
    $schema: JSON_SCHEMA_DRAFT_2020_12,
    $id: effectiveModule.namespace ? effectiveModule.namespace : effectiveModule.name ? `urn:${effectiveModule.name}` : "urn:module",
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

// docs/lab-net-webmcp/tool.js
async function registerTopologyTool(modelContext, schema, submit) {
  await modelContext.registerTool({
    name: "submit_topology",
    description: "Validate and display a lab.net topology.",
    inputSchema: schema,
    async execute(topology) {
      try {
        const result = await submit(topology);
        return { content: [{ type: "text", text: JSON.stringify(result) }] };
      } catch (error) {
        return { content: [{ type: "text", text: String(error?.message ?? error) }], isError: true };
      }
    }
  });
}

// docs/lab-net-webmcp/app.js
var $ = (selector) => document.querySelector(selector);
var status = $("#status");
document.querySelectorAll("[data-copy-target]").forEach((button) => {
  button.addEventListener("click", async () => {
    const status = document.querySelector(button.dataset.copyStatus);
    try {
      await navigator.clipboard.writeText(document.querySelector(button.dataset.copyTarget).textContent);
      if (status) status.textContent = "Copied.";
    } catch {
      if (status) status.textContent = "Select and copy the address above.";
    }
  });
});
try {
  const response = await fetch("./lab-net.yang");
  if (!response.ok) throw new Error(`Could not load lab-net.yang: ${response.status}`);
  const module = parseYangString(await response.text());
  const { schema, diagnostics } = generateJsonSchema(module, { path: "/lab:topology", nativeJson: true });
  $("#schema-output").textContent = JSON.stringify(schema, null, 2);
  const validator = new YangValidator(module);
  const submit = (topology) => {
    const validation = validator.validateDetailed({ topology }, { nativeJson: true });
    if (!validation.valid) throw new Error(validation.errors.map((error) => `${error.path || "/"}: ${error.message}`).join("\n"));
    $("#topology-output").textContent = JSON.stringify(topology, null, 2);
    $("#empty").hidden = true;
    $("#topology-output").hidden = false;
    $("#submission-state").textContent = "VALIDATED";
    return { valid: true, warnings: validation.warnings };
  };
  if (document.modelContext) {
    await registerTopologyTool(document.modelContext, schema, submit);
    $("#connection-label").textContent = "WebMCP connected";
    status.textContent = `Tool registered \xB7 ${diagnostics.length} out-of-scope constraints omitted`;
  } else {
    $("#webmcp-help").hidden = false;
    $(".top-meta .live-dot").classList.add("off");
    $("#connection-label").textContent = "WebMCP unavailable";
    status.textContent = "This browser does not expose WebMCP.";
  }
} catch (error) {
  $(".top-meta .live-dot").classList.add("off");
  $("#connection-label").textContent = "Setup incomplete";
  status.textContent = `Could not set up the example: ${error.message}`;
}
