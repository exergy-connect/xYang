/**
 * Walk instance JSON as written and yield one node per schema instance node.
 * The input is never modified. RFC 7951 is the default; native JSON is opt-in.
 */
import { YangModule, YangStatement } from "../core/model";
import { ExactDecimal } from "../types";
import { TypeChecker } from "../validator/type-checker";

const INT64 = new Set(["int64", "uint64"]);
const DECIMAL = new Set(["decimal64", "number"]);
const STRINGISH = new Set([
  "string",
  "enumeration",
  "bits",
  "binary",
  "identityref",
  "instance-identifier",
  "leafref"
]);
const SMALL_INT = new Set(["int8", "int16", "int32", "uint8", "uint16", "uint32", "integer"]);
const BUILTINS = new Set([...INT64, ...DECIMAL, ...STRINGISH, ...SMALL_INT, "boolean", "empty", "union"]);
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

type SchemaLike = { statements?: YangStatement[]; data?: unknown };

/** Per-walk caches. Statement wrappers are rebuilt by every `.statements` read, so key on `.data`. */
type WalkCache = {
  nodes: WeakMap<object, YangStatement[]>;
  resolved: WeakMap<object, Map<string, YangStatement[]>>;
  unwrapped: WeakMap<object, TypeShape | undefined>;
};

let walkCache: WalkCache | null = null;

function schemaKey(schema: SchemaLike): object {
  const data = schema.data;
  return data && typeof data === "object" ? (data as object) : schema;
}

function keywordOf(stmt: YangStatement): string {
  const raw = stmt.keyword ?? "";
  if (raw === "notification") return "container";
  if (raw.includes(":")) {
    const kind = stmt.data.data_node_kind;
    if (kind === "container" || kind === "list") return kind;
  }
  return raw;
}

function definingModule(stmt: YangStatement, parent: string): string {
  const explicit = stmt.data.defining_module;
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
  const type = stmt.data.type;
  return type && typeof type === "object" ? (type as TypeShape) : undefined;
}

function unwrap(module: YangModule, type: TypeShape | undefined): TypeShape | undefined {
  if (!type) return type;
  const cache = walkCache;
  if (!cache) return unwrapType(module, type, new Set<string>());
  if (cache.unwrapped.has(type)) return cache.unwrapped.get(type);
  const eff = unwrapType(module, type, new Set<string>());
  cache.unwrapped.set(type, eff);
  return eff;
}

function unwrapType(module: YangModule, type: TypeShape | undefined, seen: Set<string>): TypeShape | undefined {
  if (!type || typeof type.name !== "string") return type;
  if (typeof type.prefix === "string" && type.prefix) return type;
  const name = type.name;
  if (BUILTINS.has(name) || seen.has(name)) return type;
  const typedefs = module.typedefs as Record<string, { type?: TypeShape }>;
  const typedef = typedefs[name];
  if (typedef?.type && typeof typedef.type.name === "string") {
    seen.add(name);
    return unwrapType(module, typedef.type, seen);
  }
  return type;
}

function accepts(checker: TypeChecker, value: unknown, type: TypeShape): boolean {
  const name = typeof type.name === "string" ? type.name : "string";
  return checker.validate(value, name, type)[0];
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
    if (key.includes(":")) {
      const colon = key.indexOf(":");
      const moduleName = key.slice(0, colon);
      const local = key.slice(colon + 1);
      if (!moduleName || !local) return [];
      return children.filter((child) => child.name === local && definingModule(child, parent) === moduleName);
    }
    return children.filter((child) => child.name === key);
  }
  const canonical = children.filter((child) => memberKey(child, parent) === key);
  if (canonical.length > 0 || !atRoot || !key.includes(":")) return canonical;
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
  const children = dataNodes(schema);
  const nodes: InstanceNode[] = [];
  const claimed = new Set<YangStatement>();
  for (const [key, raw] of Object.entries(data)) {
    const here = join(prefix, key);
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
    if (claimed.has(stmt)) continue;
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
  if (keyword === "anydata" || keyword === "anyxml") return node(stmt, raw, ptr, "anydata");
  if (keyword === "container") {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      return node(stmt, null, ptr, "container", { errors: [["type", "container must be an object"]], include: false });
    }
    return node(stmt, null, ptr, "container", {
      children: walkObject(raw as Record<string, unknown>, stmt, module, checker, parent, ptr, native, false)
    });
  }
  if (keyword === "list") return walkList(raw, stmt, module, checker, parent, ptr, native);
  if (keyword === "leaf-list") {
    if (!Array.isArray(raw)) {
      return node(stmt, null, ptr, "leaf-list", { errors: [["type", "leaf-list must be an array"]], include: false });
    }
    const children = raw.map((item, index) => {
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
  const raw = typeof stmt.data.key === "string" ? stmt.data.key.trim() : "";
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
    Object.values(raw as object).every((item) => item && typeof item === "object" && !Array.isArray(item))
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
  const children = entries.map(([token, item]) => {
    const entryPointer = join(ptr, token);
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      return node(stmt, null, entryPointer, "entry", {
        errors: [["type", "list item must be an object"]],
        include: false
      });
    }
    const body = walkObject(item as Record<string, unknown>, stmt, module, checker, parent, entryPointer, native, false);
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

export type IterInstanceOptions = { nativeJson?: boolean; schema?: { statements?: YangStatement[] } };

/** Yield a node for each top-level instance node in `data` as written. */
export function* iterInstance(data: unknown, module: YangModule, options: IterInstanceOptions = {}): Generator<InstanceNode> {
  if (!data || typeof data !== "object" || Array.isArray(data)) return;
  const native = options.nativeJson === true;
  const schema = options.schema ?? module;
  const parent = schema === module ? (module.name ?? "") : "";
  const checker = new TypeChecker(module);
  const outer = walkCache;
  walkCache = { nodes: new WeakMap(), resolved: new WeakMap(), unwrapped: new WeakMap() };
  let nodes: InstanceNode[];
  try {
    nodes = walkObject(data as Record<string, unknown>, schema, module, checker, parent, "", native, true);
  } finally {
    walkCache = outer;
  }
  yield* nodes;
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
      continue;
    }
    if (!item.include || !item.stmt) continue;
    const key = memberKey(item.stmt, parent);
    const canon = join(prefix, key);
    pointerMap.set(canon, item.pointer);
    if (item.kind === "container") {
      out[key] = projectLevel(item.children, parent, canon, pointerMap);
    } else if (item.kind === "list") {
      const rows = item.children.filter((child) => child.include);
      out[key] = rows.map((entry, index) => {
        const entryCanon = `${canon}/${index}`;
        pointerMap.set(entryCanon, entry.pointer);
        return projectLevel(entry.children, parent, entryCanon, pointerMap);
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
