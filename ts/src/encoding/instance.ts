/**
 * Walk instance JSON as written and yield one node per schema instance node.
 * The input is never modified. RFC 7951 is the default; native JSON is opt-in.
 */
import { YangModule, YangStatement } from "../core/model";
import { Normalization } from "./normalization";
import { resolveStructureInstance } from "./rfc7951";
import { ExactDecimal } from "../types";
import {
  DECIMAL_TYPE_NAMES,
  NUMBER_INTEGER_NAMES,
  QUOTED_INTEGER_NAMES,
  REGISTRY,
  STRINGISH_NAMES
} from "../types/registry";
import { resolveTypedef, TypeChecker } from "../validator/type-checker";

const INT64 = QUOTED_INTEGER_NAMES;
const DECIMAL = DECIMAL_TYPE_NAMES;
const STRINGISH = STRINGISH_NAMES;
const SMALL_INT = new Set([...NUMBER_INTEGER_NAMES, "integer"]);
const BUILTINS = new Set([...Object.keys(REGISTRY), ...DECIMAL, "integer"]);
const INTEGER_KEY = new Set([...INT64, ...SMALL_INT]);
const ENCODED = new Set([...INT64, ...DECIMAL, "empty"]);
const INT_TEXT = /^-?\d+$/;
const DEC_TEXT = /^-?\d+(\.\d+)?$/;
const DATA = new Set(["container", "list", "leaf", "leaf-list", "anydata", "anyxml", "notification"]);
const SKIP = new Set(["rpc", "action", "input", "output"]);
const NO = Symbol("no-decode");

export type InstanceNode = {
  stmt: YangStatement | null;
  value: unknown;
  pointer: string;
  children: InstanceNode[];
  kind: string;
  errors: Array<[string, string]>;
  include: boolean;
  /** Value placed in the validator tree when it differs from `value` (decimal64). */
  projected?: unknown;
  inputKey?: string;
};

type TypeShape = Record<string, unknown>;

function escapeToken(token: string): string {
  if (token.indexOf("~") < 0 && token.indexOf("/") < 0) return token;
  return token.replace(/~/g, "~0").replace(/\//g, "~1");
}

/** JSON Pointer for `token` under `prefix` (an already-escaped pointer, "" for the root). */
function join(prefix: string, token: string): string {
  return `${prefix}/${escapeToken(token)}`;
}

type SchemaLike = { statements?: YangStatement[] };

/** Per-walk caches. Statements are stable objects, so the schema node itself is the key. */
type WalkCache = {
  nodes: WeakMap<object, YangStatement[]>;
  resolved: WeakMap<object, Map<string, YangStatement[]>>;
  unwrapped: WeakMap<object, TypeShape | undefined>;
  normalization: Normalization;
  pointers: WeakMap<object, Map<string, string>>;
};

let walkCache: WalkCache | null = null;

function schemaKey(schema: SchemaLike): object {
  return schema;
}

function keywordOf(stmt: YangStatement): string {
  const raw = stmt.keyword ?? "";
  if (raw === "notification") return "container";
  if (raw.includes(":")) {
    const kind = stmt.data_node_kind;
    if (kind === "container" || kind === "list") return kind;
  }
  return raw;
}

function isStructureSchema(stmt: YangStatement): boolean {
  return stmt.resolved_module_name === "ietf-yang-structure-ext" && stmt.resolved_extension_name === "structure";
}

function definingModule(stmt: YangStatement, parent: string): string {
  const explicit = stmt.defining_module;
  if (typeof explicit === "string" && explicit.length > 0) return explicit;
  return parent;
}

function memberKey(stmt: YangStatement, parent: string): string {
  const name = stmt.name ?? "";
  if (!name) return "";
  const owner = definingModule(stmt, parent);
  return !parent || owner === parent ? name : `${owner}:${name}`;
}

function dataNodes(schema: SchemaLike): YangStatement[] {
  const cache = walkCache;
  if (!cache) return collectDataNodes(schema);
  const key = schemaKey(schema);
  let found = cache.nodes.get(key);
  if (!found) {
    found = collectDataNodes(schema);
    cache.nodes.set(key, found);
  }
  return found;
}

function collectDataNodes(schema: SchemaLike): YangStatement[] {
  const out: YangStatement[] = [];
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

function leafType(stmt: YangStatement): TypeShape | undefined {
  const type = stmt.type;
  return type && typeof type === "object" ? (type as TypeShape) : undefined;
}

function unwrap(module: YangModule, type: TypeShape | undefined): TypeShape | undefined {
  if (!type) return type;
  const cache = walkCache;
  if (!cache) return unwrapType(module, type, new Set<TypeShape>());
  if (cache.unwrapped.has(type)) return cache.unwrapped.get(type);
  const eff = unwrapType(module, type, new Set<TypeShape>());
  cache.unwrapped.set(type, eff);
  return eff;
}

function unwrapType(module: YangModule, type: TypeShape | undefined, seen: Set<TypeShape>): TypeShape | undefined {
  if (!type || typeof type.name !== "string") return type;
  const name = type.name;
  if ((!type.prefix && BUILTINS.has(name)) || seen.has(type)) return type;
  const typedef = resolveTypedef(module, type);
  if (typedef?.type && typeof typedef.type.name === "string") {
    seen.add(type);
    return unwrapType(module, typedef.type, seen);
  }
  return type;
}

function accepts(checker: TypeChecker, value: unknown, type: TypeShape): boolean {
  const name = typeof type.name === "string" ? type.name : "string";
  return checker.validate(value, name, type).length === 0;
}

function isIntText(value: unknown): value is string {
  return typeof value === "string" && INT_TEXT.test(value.trim());
}

function isDecText(value: unknown): value is string {
  return typeof value === "string" && DEC_TEXT.test(value.trim());
}

function hint(native: boolean, kind: string): string {
  return native
    ? `${kind} is a JSON number in native mode; the default is RFC 7951`
    : `${kind} is a string in RFC 7951; pass --native-json for a JSON number`;
}

function decodeScalar(
  value: unknown,
  type: TypeShape,
  module: YangModule,
  checker: TypeChecker,
  native: boolean
): unknown {
  const eff = unwrap(module, type);
  if (!eff || typeof eff.name !== "string") return value;
  const name = eff.name;
  if (name === "union") {
    const members = Array.isArray(eff.types) ? (eff.types as TypeShape[]) : [];
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
    if ((native && Array.isArray(value) && value.length === 1 && value[0] === null) || (!native && value === null)) {
      return NO;
    }
    return value;
  }
  if (INT64.has(name)) {
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

function resolveCached(
  key: string,
  schema: SchemaLike,
  children: YangStatement[],
  parent: string,
  native: boolean,
  atRoot: boolean
): YangStatement[] {
  const cache = walkCache;
  if (!cache) return resolveName(key, children, parent, native, atRoot);
  const owner = schemaKey(schema);
  let byKey = cache.resolved.get(owner);
  if (!byKey) {
    byKey = new Map();
    cache.resolved.set(owner, byKey);
  }
  const memo = atRoot ? `\u0000${key}` : key;
  let hits = byKey.get(memo);
  if (!hits) {
    hits = resolveName(key, children, parent, native, atRoot);
    byKey.set(memo, hits);
  }
  return hits;
}

function resolveName(
  key: string,
  children: YangStatement[],
  parent: string,
  native: boolean,
  atRoot: boolean
): YangStatement[] {
  if (native) {
    if (key.includes(":")) return byQualifiedName(key, children, parent);
    return children.filter((child) => child.name === key);
  }
  const canonical = children.filter((child) => memberKey(child, parent) === key);
  if (canonical.length > 0 || !atRoot || !key.includes(":")) return canonical;
  return byQualifiedName(key, children, parent);
}

/** Children matching a `module:name` key by local name and defining module. */
function byQualifiedName(key: string, children: YangStatement[], parent: string): YangStatement[] {
  const colon = key.indexOf(":");
  const moduleName = key.slice(0, colon);
  const local = key.slice(colon + 1);
  if (!moduleName || !local) return [];
  return children.filter((child) => child.name === local && definingModule(child, parent) === moduleName);
}

function node(
  stmt: YangStatement | null,
  value: unknown,
  ptr: string,
  kind: string,
  extra: Partial<InstanceNode> = {}
): InstanceNode {
  return { stmt, value, pointer: ptr, children: [], kind, errors: [], include: true, ...extra };
}

function expandDotted(data: Record<string, unknown>, prefix: string): { data: Record<string, unknown>; error?: [string, string] } {
  const pointers = walkCache!.pointers;
  const clone = (obj: Record<string, unknown>, path: string): Record<string, unknown> => {
    const copy = { ...obj };
    pointers.set(copy, new Map(pointers.get(obj) ?? Object.keys(obj).map(key => [key, join(path, key)])));
    return copy;
  };
  const result = clone(data, prefix);
  const source = pointers.get(result)!;
  for (const key of Object.keys(result).filter(k => k.includes("."))) {
    const value = result[key], pointer = source.get(key)!; delete result[key]; source.delete(key);
    const parts = key.split(".");
    if (parts.some(p => !p)) return { data: result, error: [pointer, `invalid dotted key '${key}'`] };
    let cur = result;
    for (const part of parts.slice(0, -1)) {
      const map = pointers.get(cur)!;
      if (!Object.hasOwn(cur, part)) { cur[part] = Object.create(null) as Record<string, unknown>; pointers.set(cur[part] as object, new Map()); map.set(part, pointer); }
      else if (!cur[part] || typeof cur[part] !== "object" || Array.isArray(cur[part])) return { data: result, error: [pointer, `dotted key '${key}' conflicts with '${part}'`] };
      else cur[part] = clone(cur[part] as Record<string, unknown>, map.get(part) ?? pointer);
      cur = cur[part] as Record<string, unknown>;
    }
    const last = parts[parts.length - 1];
    if (Object.hasOwn(cur, last)) return { data: result, error: [pointer, `dotted key '${key}' conflicts with an existing member`] };
    cur[last] = value; pointers.get(cur)!.set(last, pointer);
  }
  return { data: result };
}

function walkObject(
  data: Record<string, unknown>,
  schema: SchemaLike,
  module: YangModule,
  checker: TypeChecker,
  parent: string,
  prefix: string,
  native: boolean,
  atRoot: boolean
): InstanceNode[] {
  if (atRoot) {
    const structure = resolveStructureInstance(data, module);
    // A nested structure is not a data-node child. A top-level one already is, via data_node_kind.
    if (structure && structure.schema.data_node_kind !== "container") {
      return [
        walkNode(structure.inner, structure.schema, module, checker, parent, join(prefix, structure.key), native)
      ];
    }
  }
  if (walkCache?.normalization.expandDotted) {
    const expanded = expandDotted(data, prefix);
    if (expanded.error) return [node(null, null, expanded.error[0], "opaque", { errors: [["normalize", expanded.error[1]]], include: false })];
    data = expanded.data;
  }
  const children = dataNodes(schema);
  const nodes: InstanceNode[] = [];
  const claimed = new Set<YangStatement>();
  for (const [key, raw] of Object.entries(data)) {
    const here = walkCache?.pointers.get(data)?.get(key) ?? join(prefix, key);
    const hits = resolveCached(key, schema, children, parent, native, atRoot);
    if (hits.length === 0) {
      nodes.push(node(null, raw, here, "unknown", { inputKey: key }));
      continue;
    }
    if (hits.length > 1) {
      nodes.push(
        node(null, null, here, "ambiguous", {
          errors: [["ambiguous-name", `member name '${key}' matches more than one node`]],
          include: false
        })
      );
      continue;
    }
    const stmt = hits[0];
    if (claimed.has(stmt)) {
      if (walkCache?.normalization.expandDotted) nodes.push(node(null, null, here, "ambiguous", { errors: [["normalize", `member '${key}' conflicts with another spelling of the same node`]], include: false }));
      continue;
    }
    claimed.add(stmt);
    nodes.push(walkNode(raw, stmt, module, checker, parent, here, native));
  }
  return nodes;
}

function walkLeaf(
  raw: unknown,
  stmt: YangStatement,
  module: YangModule,
  checker: TypeChecker,
  ptr: string,
  native: boolean
): InstanceNode {
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
      const message =
        name === "empty"
          ? native
            ? "empty is null in native mode; RFC 7951 encodes empty as [null]"
            : "empty is [null] in RFC 7951; pass --native-json for null"
          : hint(native, name);
      return node(stmt, null, ptr, "leaf", { errors: [["type", message]], include: false });
    }
    return node(stmt, raw, ptr, "leaf");
  }
  return node(stmt, decoded, ptr, "leaf");
}

function walkNode(
  raw: unknown,
  stmt: YangStatement,
  module: YangModule,
  checker: TypeChecker,
  parent: string,
  ptr: string,
  native: boolean
): InstanceNode {
  const keyword = keywordOf(stmt);
  if (keyword !== "list" && keyword !== "leaf-list" && walkCache) {
    try { raw = walkCache.normalization.visit(stmt, raw); }
    catch (e) { return node(stmt, null, ptr, "opaque", { errors: [["normalize", String(e instanceof Error ? e.message : e)]], include: false }); }
  }
  if ((keyword === "list" || keyword === "leaf-list") && walkCache) raw = walkCache.normalization.collection(stmt, raw);
  if (keyword === "anydata" || keyword === "anyxml") return node(stmt, raw, ptr, "anydata");
  if (keyword === "container" || isStructureSchema(stmt)) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      return node(stmt, null, ptr, "container", { errors: [["type", "container must be an object"]], include: false });
    }
    return node(stmt, null, ptr, "container", {
      children: walkObject(raw as Record<string, unknown>, stmt, module, checker, definingModule(stmt, parent), ptr, native, false)
    });
  }
  if (keyword === "list") return walkList(raw, stmt, module, checker, parent, ptr, native);
  if (keyword === "leaf-list") {
    if (!Array.isArray(raw)) {
      return node(stmt, null, ptr, "leaf-list", { errors: [["type", "leaf-list must be an array"]], include: false });
    }
    const children = raw.map((item, index) => {
      try { item = walkCache!.normalization.visit(stmt, item); }
      catch (e) { return node(stmt, null, `${ptr}/${index}`, "leaf-list-item", { errors: [["normalize", String(e instanceof Error ? e.message : e)]], include: false }); }
      const child = walkLeaf(item, stmt, module, checker, `${ptr}/${index}`, native);
      child.kind = "leaf-list-item";
      return child;
    });
    return node(stmt, null, ptr, "leaf-list", { children });
  }
  if (keyword === "leaf") return walkLeaf(raw, stmt, module, checker, ptr, native);
  return node(stmt, raw, ptr, "opaque");
}

function keyNames(stmt: YangStatement): string[] {
  const raw = typeof stmt.key === "string" ? stmt.key.trim() : "";
  return raw ? raw.split(/\s+/).filter(Boolean) : [];
}

function convertKey(text: string, leaf: YangStatement, module: YangModule, checker: TypeChecker, native: boolean): unknown {
  const type = leafType(leaf);
  if (!type) return text;
  const eff = unwrap(module, type);
  const name = typeof eff?.name === "string" ? eff.name : "";
  let candidate: unknown = text;
  if (INTEGER_KEY.has(name)) {
    if (!INT_TEXT.test(text)) return NO;
    candidate = INT64.has(name) ? BigInt(text) : Number(text);
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

function walkList(
  raw: unknown,
  stmt: YangStatement,
  module: YangModule,
  checker: TypeChecker,
  parent: string,
  ptr: string,
  native: boolean
): InstanceNode {
  const keys = keyNames(stmt);
  let entries: Array<[string, unknown]> = [];
  let keyed = false;
  if (Array.isArray(raw)) {
    entries = raw.map((item, index) => [String(index), item]);
  } else if (
    native &&
    raw &&
    typeof raw === "object" &&
    !Array.isArray(raw) &&
    keys.length === 1 &&
    (Object.values(raw as object).every((item) => item && typeof item === "object" && !Array.isArray(item)) || (walkCache?.normalization.rules(stmt).length ?? 0) > 0)
  ) {
    entries = Object.entries(raw as Record<string, unknown>);
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
  const keyLeaf = keys.length === 1 ? dataNodes(stmt).find((child) => child.name === keys[0]) : undefined;
  const children = entries.map(([token, original]) => {
    const entryPointer = join(ptr, token);
    let item = original;
    try { item = walkCache!.normalization.visit(stmt, item); }
    catch (e) { return node(stmt, null, entryPointer, "entry", { errors: [["normalize", String(e instanceof Error ? e.message : e)]], include: false }); }
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      return node(stmt, null, entryPointer, "entry", {
        errors: [["type", "list item must be an object"]],
        include: false
      });
    }
    const body = walkObject(item as Record<string, unknown>, stmt, module, checker, definingModule(stmt, parent), entryPointer, native, false);
    if (keyed && keyLeaf?.keyword === "leaf") {
      const converted = convertKey(token, keyLeaf, module, checker, native);
      const present = body.find((child) => child.kind === "leaf" && child.stmt?.name === keyLeaf.name && child.include);
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
  return node(stmt, null, ptr, "list", { children });
}

export type IterInstanceOptions = {
  nativeJson?: boolean;
  schema?: { statements?: YangStatement[] };
  /** Module whose children are unqualified under `schema` (default: the module itself, none for another schema). */
  parentModule?: string;
  /** False when `data` is the body of a container such as an rpc `input` (RFC 7951 §4). Default true. */
  atRoot?: boolean;
  /** Internal snapshot excludes recursive key projection. */
  skipProjection?: boolean;
};

/** Yield a node for each top-level instance node in `data` as written. */
export function* iterInstance(data: unknown, module: YangModule, options: IterInstanceOptions = {}): Generator<InstanceNode> {
  if (!data || typeof data !== "object" || Array.isArray(data)) return;
  const native = options.nativeJson === true;
  const schema = options.schema ?? module;
  const parent = options.parentModule ?? (schema === module ? (module.name ?? "") : "");
  const checker = new TypeChecker(module);
  const outer = walkCache;
  walkCache = { nodes: new WeakMap(), resolved: new WeakMap(), unwrapped: new WeakMap(), pointers: new WeakMap(), normalization: new Normalization(module) };
  walkCache.normalization.skipProjection = options.skipProjection === true;
  let snapshot: Record<string, unknown> | undefined;
  walkCache.normalization.rootContext = () => {
    snapshot ??= projectInstance([...iterInstance(data, module, { ...options, skipProjection: true })], parent).data;
    return { data: snapshot, schema: schema as YangStatement, parent: null };
  };
  let nodes: InstanceNode[];
  try {
    const prepare = (current: SchemaLike, isModule = false): void => {
      walkCache!.normalization.rules(current, isModule);
      for (const child of dataNodes(current)) prepare(child);
    };
    prepare(schema, schema === module);
    let rootData: unknown;
    try { rootData = walkCache.normalization.visit(schema as YangStatement, data); }
    catch (e) { nodes = [node(null, null, "", "opaque", { errors: [["normalize", String(e instanceof Error ? e.message : e)]], include: false })]; yield* nodes; return; }
    if (!rootData || typeof rootData !== "object" || Array.isArray(rootData)) {
      nodes = [node(null, null, "", "opaque", { errors: [["normalize", "root normalization must produce an object"]], include: false })];
    } else nodes = walkObject(rootData as Record<string, unknown>, schema, module, checker, parent, "", native, options.atRoot ?? true);
  } finally {
    walkCache = outer;
  }
  yield* nodes;
}

type Issue = { path: string; code: string; message: string };

function sameJson(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (!left || !right || typeof left !== "object" || typeof right !== "object") return false;
  if (Array.isArray(left) !== Array.isArray(right)) return false;
  const a = left as Record<string, unknown>;
  const b = right as Record<string, unknown>;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every((key) => Object.hasOwn(b, key) && sameJson(a[key], b[key]));
}

function errorText(e: unknown): string {
  return String(e instanceof Error ? e.message : e);
}

/** False (and an issue) when a normalize rule fails or would change `raw`. */
function normalized(stmt: YangStatement, raw: unknown, ptr: string, out: Issue[], collection = false): boolean {
  let value: unknown;
  try {
    value = collection ? walkCache!.normalization.collection(stmt, raw) : walkCache!.normalization.visit(stmt, raw);
  } catch (e) {
    out.push({ path: ptr, code: "normalize", message: errorText(e) });
    return false;
  }
  if (!sameJson(value, raw)) {
    out.push({ path: ptr, code: "canonical", message: "an xt:normalize rule changes this value; it is applied only without canonical" });
    return false;
  }
  return true;
}

function leafIssues(raw: unknown, stmt: YangStatement, module: YangModule, checker: TypeChecker, ptr: string): Issue[] {
  return walkLeaf(raw, stmt, module, checker, ptr, true).errors.map(([code, message]) => ({ path: ptr, code, message }));
}

function checkObject(
  data: Record<string, unknown>,
  schema: SchemaLike,
  module: YangModule,
  checker: TypeChecker,
  parent: string,
  prefix: string,
  atRoot: boolean,
  out: Issue[]
): void {
  if (atRoot) {
    const structure = resolveStructureInstance(data, module);
    if (structure && structure.schema.data_node_kind !== "container") {
      checkNode(structure.inner, structure.schema, module, checker, parent, join(prefix, structure.key), out);
      return;
    }
  }
  const expand = walkCache!.normalization.expandDotted;
  const children = dataNodes(schema);
  for (const [key, raw] of Object.entries(data)) {
    const here = join(prefix, key);
    if (expand && key.includes(".")) {
      out.push({ path: here, code: "canonical", message: `dotted key '${key}' is expanded only without canonical` });
      continue;
    }
    // Native resolution first, so a member accepted here resolves exactly as without canonical.
    const hits = resolveCached(key, schema, children, parent, true, atRoot);
    if (hits.length === 0) continue;
    if (hits.length > 1) {
      out.push({ path: here, code: "ambiguous-name", message: `member name '${key}' matches more than one node` });
      continue;
    }
    const spelled = memberKey(hits[0], parent);
    if (key !== spelled) {
      out.push({ path: here, code: "canonical", message: `member '${key}' is spelled '${spelled}' in a canonical instance` });
      continue;
    }
    checkNode(raw, hits[0], module, checker, parent, here, out);
  }
}

function checkNode(
  raw: unknown,
  stmt: YangStatement,
  module: YangModule,
  checker: TypeChecker,
  parent: string,
  ptr: string,
  out: Issue[]
): void {
  const keyword = keywordOf(stmt);
  if (!normalized(stmt, raw, ptr, out, keyword === "list" || keyword === "leaf-list")) return;
  const isObject = (value: unknown): value is Record<string, unknown> =>
    Boolean(value) && typeof value === "object" && !Array.isArray(value);
  if (keyword === "leaf") {
    out.push(...leafIssues(raw, stmt, module, checker, ptr));
  } else if (keyword === "container" || isStructureSchema(stmt)) {
    if (!isObject(raw)) {
      out.push({ path: ptr, code: "type", message: "container must be an object" });
      return;
    }
    checkObject(raw, stmt, module, checker, definingModule(stmt, parent), ptr, false, out);
  } else if (keyword === "list") {
    if (isObject(raw)) {
      out.push({ path: ptr, code: "canonical", message: "a list is a JSON array in a canonical instance" });
      return;
    }
    if (!Array.isArray(raw)) {
      out.push({ path: ptr, code: "type", message: "list must be an array" });
      return;
    }
    raw.forEach((item, index) => {
      const here = `${ptr}/${index}`;
      if (!normalized(stmt, item, here, out)) return;
      if (!isObject(item)) {
        out.push({ path: here, code: "type", message: "list item must be an object" });
        return;
      }
      checkObject(item, stmt, module, checker, definingModule(stmt, parent), here, false, out);
    });
  } else if (keyword === "leaf-list") {
    if (!Array.isArray(raw)) {
      out.push({ path: ptr, code: "type", message: "leaf-list must be an array" });
      return;
    }
    raw.forEach((item, index) => {
      const here = `${ptr}/${index}`;
      if (normalized(stmt, item, here, out)) out.push(...leafIssues(item, stmt, module, checker, here));
    });
  }
}

/**
 * Issues wherever native `data` is not already canonical (Python `canonical_errors`). Canonical
 * native JSON is the tree `projectInstance` builds: members spelled as in that tree
 * (`module:name` only where the module changes), lists as JSON arrays, no dotted keys left to
 * expand, no `xt:normalize` rule that would change a value, and every leaf in its native
 * encoding. No issues means `data` can be validated as written.
 */
export function canonicalErrors(data: Record<string, unknown>, module: YangModule, options: Omit<IterInstanceOptions, "nativeJson" | "skipProjection"> = {}): Issue[] {
  const schema = options.schema ?? module;
  const parent = options.parentModule ?? (schema === module ? (module.name ?? "") : "");
  const checker = new TypeChecker(module);
  const outer = walkCache;
  walkCache = { nodes: new WeakMap(), resolved: new WeakMap(), unwrapped: new WeakMap(), pointers: new WeakMap(), normalization: new Normalization(module) };
  walkCache.normalization.rootContext = () => ({ data, schema: schema as YangStatement, parent: null });
  const out: Issue[] = [];
  try {
    const prepare = (current: SchemaLike, isModule = false): void => {
      walkCache!.normalization.rules(current, isModule);
      for (const child of dataNodes(current)) prepare(child);
    };
    prepare(schema, schema === module);
    if (normalized(schema as YangStatement, data, "", out)) {
      checkObject(data, schema, module, checker, parent, "", options.atRoot ?? true, out);
    }
  } finally {
    walkCache = outer;
  }
  return out;
}

export function encodingErrors(nodes: InstanceNode[]): Array<{ path: string; code: string; message: string }> {
  const found: Array<{ path: string; code: string; message: string }> = [];
  const walk = (item: InstanceNode): void => {
    for (const [code, message] of item.errors) found.push({ path: item.pointer, code, message });
    for (const child of item.children) walk(child);
  };
  for (const item of nodes) walk(item);
  return found;
}

export function projectInstance(
  nodes: InstanceNode[],
  parent = ""
): { data: Record<string, unknown>; pointerMap: Map<string, string> } {
  const pointerMap = new Map<string, string>();
  return { data: projectLevel(nodes, parent, "", pointerMap), pointerMap };
}

function projectLevel(
  nodes: InstanceNode[],
  parent: string,
  prefix: string,
  pointerMap: Map<string, string>
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const item of nodes) {
    if (item.kind === "unknown" && item.inputKey) {
      out[item.inputKey] = item.value;
      pointerMap.set(join(prefix, item.inputKey), item.pointer);
      continue;
    }
    if (!item.include || !item.stmt) continue;
    const key = memberKey(item.stmt, parent);
    const canon = join(prefix, key);
    pointerMap.set(canon, item.pointer);
    const childParent = definingModule(item.stmt, parent);
    if (item.kind === "container") {
      out[key] = projectLevel(item.children, childParent, canon, pointerMap);
    } else if (item.kind === "list") {
      const rows = item.children.filter((child) => child.include);
      out[key] = rows.map((entry, index) => {
        const entryCanon = `${canon}/${index}`;
        pointerMap.set(entryCanon, entry.pointer);
        return projectLevel(entry.children, childParent, entryCanon, pointerMap);
      });
    } else if (item.kind === "leaf-list") {
      const items = item.children.filter((child) => child.include);
      out[key] = items.map((child, index) => {
        pointerMap.set(`${canon}/${index}`, child.pointer);
        return child.projected !== undefined ? child.projected : child.value;
      });
    } else if (item.kind === "leaf" || item.kind === "anydata") {
      out[key] = item.projected !== undefined ? item.projected : item.value;
    }
  }
  return out;
}

export function remapPointer(path: string, pointerMap: Map<string, string>): string {
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
