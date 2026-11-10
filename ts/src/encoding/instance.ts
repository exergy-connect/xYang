/**
 * Normalize RFC 7951 and dict-style instance JSON into one tree.
 *
 * This is the only code that knows about either encoding. Validators see its
 * output: containers are objects, lists are arrays of objects with key leaves
 * filled in, member names follow the RFC 7951 local-or-qualified rule, `empty`
 * is `null`, and int64/uint64/decimal64 use one canonical value.
 */
import { YangModule, YangStatement } from "../core/model";
import { TypeChecker } from "../validator/type-checker";

const NORMALIZATION_ERRORS = Symbol.for("xyang.normalizationErrors");

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
const INTEGER_KEY = new Set([
  "int8",
  "int16",
  "int32",
  "int64",
  "uint8",
  "uint16",
  "uint32",
  "uint64",
  "integer"
]);
const BUILTINS = new Set([
  ...INT64,
  ...DECIMAL,
  ...STRINGISH,
  ...INTEGER_KEY,
  "boolean",
  "empty",
  "union"
]);
const DATA_KEYWORDS = new Set(["container", "list", "leaf", "leaf-list", "anydata", "anyxml"]);
const SKIP_KEYWORDS = new Set(["notification", "rpc", "action", "input", "output"]);

export type EncodingError = { code: string; path: string; message: string };

type TypeShape = Record<string, unknown>;

type NormCtx = {
  module: YangModule;
  parent: string;
  checker: TypeChecker;
  errors: EncodingError[];
};

function pointer(tokens: string[]): string {
  if (tokens.length === 0) {
    return "";
  }
  return "/" + tokens.map((token) => token.replace(/~/g, "~0").replace(/\//g, "~1")).join("/");
}

function clone<T>(value: T): T {
  if (Array.isArray(value)) {
    return value.map((item) => clone(item)) as T;
  }
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      out[key] = clone(item);
    }
    return out as T;
  }
  return value;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function normalizationErrors(data: unknown): EncodingError[] {
  if (data && typeof data === "object" && NORMALIZATION_ERRORS in data) {
    return (data as { [NORMALIZATION_ERRORS]?: EncodingError[] })[NORMALIZATION_ERRORS] ?? [];
  }
  return [];
}

function tag(tree: Record<string, unknown>, errors: EncodingError[]): Record<string, unknown> {
  Object.defineProperty(tree, NORMALIZATION_ERRORS, { value: errors, enumerable: false });
  return tree;
}

function definingModule(stmt: YangStatement, parent: string): string {
  const explicit = stmt.data.defining_module;
  if (typeof explicit === "string" && explicit.length > 0) {
    return explicit;
  }
  return parent;
}

function canonicalKey(stmt: YangStatement, parent: string): string {
  const name = stmt.name ?? "";
  if (!name) {
    return "";
  }
  const owner = definingModule(stmt, parent);
  return owner === parent ? name : `${owner}:${name}`;
}

function dataNodes(schema: { statements?: YangStatement[] }): YangStatement[] {
  const out: YangStatement[] = [];
  for (const stmt of schema.statements ?? []) {
    const keyword = stmt.keyword ?? "";
    if (SKIP_KEYWORDS.has(keyword)) {
      continue;
    }
    if (keyword === "choice" || keyword === "case") {
      out.push(...dataNodes(stmt));
      continue;
    }
    if (DATA_KEYWORDS.has(keyword)) {
      out.push(stmt);
    }
  }
  return out;
}

function resolveName(key: string, children: YangStatement[], parent: string): YangStatement[] {
  if (key.includes(":")) {
    const colon = key.indexOf(":");
    const moduleName = key.slice(0, colon);
    const local = key.slice(colon + 1);
    if (!moduleName || !local) {
      return [];
    }
    return children.filter((child) => child.name === local && definingModule(child, parent) === moduleName);
  }
  return children.filter((child) => child.name === key);
}

function leafType(stmt: YangStatement): TypeShape | undefined {
  const type = stmt.data.type;
  if (type && typeof type === "object") {
    return type as TypeShape;
  }
  return undefined;
}

function unwrap(module: YangModule, type: TypeShape | undefined, seen = new Set<string>()): TypeShape | undefined {
  if (!type || typeof type.name !== "string") {
    return type;
  }
  if (typeof type.prefix === "string" && type.prefix.length > 0) {
    return type;
  }
  const name = type.name;
  if (BUILTINS.has(name) || seen.has(name)) {
    return type;
  }
  const typedefs = module.typedefs as Record<string, { type?: TypeShape }>;
  const typedef = typedefs[name];
  if (typedef?.type && typeof typedef.type.name === "string") {
    seen.add(name);
    return unwrap(module, typedef.type, seen);
  }
  return type;
}

function accepts(ctx: NormCtx, value: unknown, type: TypeShape): boolean {
  const name = typeof type.name === "string" ? type.name : "string";
  const [ok] = ctx.checker.validate(value, name, type);
  return ok;
}

function stringMemberAccepts(ctx: NormCtx, value: string, members: TypeShape[]): boolean {
  for (const member of members) {
    const eff = unwrap(ctx.module, member);
    if (!eff || typeof eff.name !== "string") {
      continue;
    }
    if (eff.name === "union") {
      const nested = Array.isArray(eff.types) ? (eff.types as TypeShape[]) : [];
      if (stringMemberAccepts(ctx, value, nested)) {
        return true;
      }
      continue;
    }
    if (STRINGISH.has(eff.name) && accepts(ctx, value, member)) {
      return true;
    }
  }
  return false;
}

function canonInt64(value: unknown, tokens: string[], errors: EncodingError[]): unknown {
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) {
      errors.push({
        code: "type",
        path: pointer(tokens),
        message: "integer is outside the safe JSON number range; use the RFC 7951 string form"
      });
      return value;
    }
    return value;
  }
  if (typeof value === "string" && /^-?\d+$/.test(value.trim())) {
    const text = value.trim();
    const parsed = Number(text);
    if (Number.isSafeInteger(parsed)) {
      return parsed;
    }
    return value;
  }
  return value;
}

function canonDecimal(value: unknown): unknown {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  if (typeof value === "string") {
    return value;
  }
  return value;
}

function memberList(type: TypeShape): TypeShape[] {
  return Array.isArray(type.types) ? (type.types as TypeShape[]) : [];
}

function normalizeUnion(value: unknown, unionType: TypeShape, ctx: NormCtx, tokens: string[]): unknown {
  const members = memberList(unionType);
  if (typeof value === "string") {
    if (stringMemberAccepts(ctx, value, members)) {
      return value;
    }
    const text = value.trim();
    for (const member of members) {
      const eff = unwrap(ctx.module, member);
      if (!eff || typeof eff.name !== "string") {
        continue;
      }
      if (eff.name === "union") {
        const nested = normalizeUnion(value, eff, ctx, tokens);
        if (nested !== value || stringMemberAccepts(ctx, value, memberList(eff))) {
          return nested;
        }
        continue;
      }
      if (INT64.has(eff.name) && /^-?\d+$/.test(text)) {
        const parsed = Number(text);
        if (Number.isSafeInteger(parsed) && accepts(ctx, parsed, member)) {
          return parsed;
        }
        if (!Number.isSafeInteger(parsed)) {
          return value;
        }
      }
      if (DECIMAL.has(eff.name) && /^-?\d+(\.\d+)?$/.test(text) && accepts(ctx, text, member)) {
        return text;
      }
    }
    return value;
  }
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    for (const member of members) {
      const eff = unwrap(ctx.module, member);
      if (!eff || typeof eff.name !== "string") {
        continue;
      }
      if (INT64.has(eff.name) && accepts(ctx, value, member)) {
        return canonInt64(value, tokens, ctx.errors);
      }
      if (DECIMAL.has(eff.name) && accepts(ctx, value, member)) {
        return canonDecimal(value);
      }
      if (eff.name === "union") {
        const nested = normalizeUnion(value, eff, ctx, tokens);
        if (accepts(ctx, nested, member)) {
          return nested;
        }
        continue;
      }
      if (accepts(ctx, value, member)) {
        return value;
      }
    }
    return value;
  }
  if (Array.isArray(value) && value.length === 1 && value[0] === null) {
    for (const member of members) {
      const eff = unwrap(ctx.module, member);
      if (eff?.name === "empty") {
        return null;
      }
    }
  }
  return value;
}

function normalizeLeaf(value: unknown, type: TypeShape | undefined, ctx: NormCtx, tokens: string[]): unknown {
  const eff = unwrap(ctx.module, type);
  if (!eff || typeof eff.name !== "string") {
    return value;
  }
  if (eff.name === "empty") {
    if (Array.isArray(value) && value.length === 1 && value[0] === null) {
      return null;
    }
    return value;
  }
  if (eff.name === "union") {
    return normalizeUnion(value, eff, ctx, tokens);
  }
  if (INT64.has(eff.name)) {
    return canonInt64(value, tokens, ctx.errors);
  }
  if (DECIMAL.has(eff.name)) {
    return canonDecimal(value);
  }
  return value;
}

function convertKey(text: string, leaf: YangStatement, ctx: NormCtx): { value: unknown; ok: boolean } {
  const eff = unwrap(ctx.module, leafType(leaf));
  const name = typeof eff?.name === "string" ? eff.name : "";
  if (name === "boolean") {
    if (text === "true") return { value: true, ok: true };
    if (text === "false") return { value: false, ok: true };
    return { value: text, ok: false };
  }
  if (name === "empty") {
    return { value: text, ok: false };
  }
  if (INTEGER_KEY.has(name)) {
    if (!/^-?\d+$/.test(text)) {
      return { value: text, ok: false };
    }
    const parsed = Number(text);
    if (!Number.isSafeInteger(parsed)) {
      return { value: text, ok: false };
    }
    return { value: parsed, ok: true };
  }
  if (DECIMAL.has(name)) {
    if (!/^-?\d+(\.\d+)?$/.test(text)) {
      return { value: text, ok: false };
    }
    return { value: text, ok: true };
  }
  if (name === "union" && eff) {
    return { value: normalizeUnion(text, eff, ctx, []), ok: true };
  }
  return { value: text, ok: true };
}

function findNamed(schema: YangStatement, name: string): YangStatement | undefined {
  return dataNodes(schema).find((child) => child.name === name);
}

function sameValue(left: unknown, right: unknown): boolean {
  return left === right;
}

function normalizeObject(
  data: Record<string, unknown>,
  schema: { statements?: YangStatement[] },
  ctx: NormCtx,
  tokens: string[]
): Record<string, unknown> {
  const children = dataNodes(schema);
  const out: Record<string, unknown> = {};
  const claimed = new Set<YangStatement>();
  for (const [key, value] of Object.entries(data)) {
    const hits = resolveName(key, children, ctx.parent);
    if (hits.length === 0) {
      out[key] = clone(value);
      continue;
    }
    if (hits.length > 1) {
      ctx.errors.push({
        code: "ambiguous-name",
        path: pointer([...tokens, key]),
        message: `member name '${key}' matches more than one node`
      });
      continue;
    }
    const stmt = hits[0];
    if (claimed.has(stmt)) {
      continue;
    }
    claimed.add(stmt);
    const canon = canonicalKey(stmt, ctx.parent);
    out[canon] = normalizeNode(value, stmt, ctx, [...tokens, canon]);
  }
  return out;
}

function normalizeList(value: unknown, stmt: YangStatement, ctx: NormCtx, tokens: string[]): unknown {
  const keyRaw = typeof stmt.data.key === "string" ? stmt.data.key.trim() : "";
  const keyNames = keyRaw.length > 0 ? keyRaw.split(/\s+/).filter(Boolean) : [];
  if (Array.isArray(value)) {
    return value.map((entry, index) =>
      isObject(entry) ? normalizeObject(entry, stmt, ctx, [...tokens, String(index)]) : clone(entry)
    );
  }
  if (!isObject(value)) {
    return clone(value);
  }
  if (keyNames.length !== 1) {
    ctx.errors.push({
      code: "list-encoding",
      path: pointer(tokens),
      message: "a list with more than one key must be a JSON array"
    });
    return [];
  }
  if (!Object.values(value).every((entry) => isObject(entry))) {
    return clone(value);
  }
  const keyLeaf = findNamed(stmt, keyNames[0]);
  return Object.entries(value).map(([dictKey, entry], index) => {
    const entryTokens = [...tokens, String(index)];
    const normalized = normalizeObject(entry as Record<string, unknown>, stmt, ctx, entryTokens);
    if (keyLeaf?.keyword === "leaf") {
      const canonName = canonicalKey(keyLeaf, ctx.parent);
      const converted = convertKey(dictKey, keyLeaf, ctx);
      const keyPath = pointer([...entryTokens, canonName]);
      if (!converted.ok) {
        ctx.errors.push({
          code: "type",
          path: keyPath,
          message: `dict key '${dictKey}' cannot be converted to the key type`
        });
        if (!(canonName in normalized)) {
          normalized[canonName] = dictKey;
        }
      } else if (canonName in normalized) {
        if (!sameValue(normalized[canonName], converted.value)) {
          ctx.errors.push({
            code: "key-mismatch",
            path: keyPath,
            message: `key leaf does not match dict key '${dictKey}'`
          });
        } else {
          normalized[canonName] = converted.value;
        }
      } else {
        normalized[canonName] = converted.value;
      }
    }
    return normalized;
  });
}

function normalizeNode(value: unknown, stmt: YangStatement, ctx: NormCtx, tokens: string[]): unknown {
  const keyword = stmt.keyword ?? "";
  if (keyword === "anydata" || keyword === "anyxml") {
    return clone(value);
  }
  if (keyword === "list") {
    return normalizeList(value, stmt, ctx, tokens);
  }
  if (keyword === "container") {
    if (!isObject(value)) {
      return clone(value);
    }
    return normalizeObject(value, stmt, ctx, tokens);
  }
  if (keyword === "leaf-list") {
    if (!Array.isArray(value)) {
      return clone(value);
    }
    return value.map((item) => normalizeLeaf(item, leafType(stmt), ctx, tokens));
  }
  if (keyword === "leaf") {
    return normalizeLeaf(value, leafType(stmt), ctx, tokens);
  }
  return clone(value);
}

/** Normalize *data* to the canonical instance tree for *module*. */
export function normalizeInstance(data: unknown, module: YangModule): unknown {
  if (!isObject(data)) {
    return data;
  }
  const ctx: NormCtx = {
    module,
    parent: module.name ?? "",
    checker: new TypeChecker(module),
    errors: []
  };
  const tree = normalizeObject(data, module, ctx, []);
  return tag(tree, ctx.errors);
}
