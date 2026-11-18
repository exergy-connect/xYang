/**
 * Evaluate model-defined, jq-style instance normalization rules.
 * Mirrors `src/xyang/ext/transform/__init__.py`.
 */
import type { YangModule, YangStatement } from "../core/model";
import { Normalization as InstanceNormalization } from "../encoding/normalization";

const TOKEN =
  /\s*(?:("(?:[^"\\]|\\.)*")|([A-Za-z_][A-Za-z_0-9-]*)|([0-9]+)|(==|!=|[.\[\]{}():,|]))/y;

export class ExpressionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ExpressionError";
  }
}

type Expr =
  | ["input"]
  | ["literal", unknown]
  | ["pipe", Expr, Expr]
  | ["type"]
  | ["length"]
  | ["to_entries"]
  | ["object", Array<[string, Expr]>]
  | ["index", Expr, number | string]
  | ["eq" | "ne" | "and" | "or", Expr, Expr]
  | ["contains" | "split" | "has", Expr];

type Token = { kind: string; value: unknown };

class Parser {
  private tokens: Token[] = [];
  private i = 0;

  constructor(text: string) {
    let pos = 0;
    while (pos < text.length) {
      if (!text.slice(pos).trim()) break;
      TOKEN.lastIndex = pos;
      const match = TOKEN.exec(text);
      if (!match || match.index !== pos) {
        throw new ExpressionError(`unsupported expression syntax at offset ${pos}`);
      }
      const [, string, word, number, symbol] = match;
      if (string !== undefined) {
        try {
          this.tokens.push({ kind: "literal", value: JSON.parse(string) });
        } catch (exc) {
          throw new ExpressionError(`invalid string: ${exc instanceof Error ? exc.message : String(exc)}`);
        }
      } else if (word !== undefined) {
        this.tokens.push({ kind: "word", value: word });
      } else if (number !== undefined) {
        this.tokens.push({ kind: "number", value: Number(number) });
      } else {
        this.tokens.push({ kind: symbol!, value: symbol! });
      }
      pos = TOKEN.lastIndex;
    }
  }

  private take(value: string): boolean {
    const token = this.tokens[this.i];
    if (!token) return false;
    if (token.kind === value || token.value === value) {
      this.i += 1;
      return true;
    }
    return false;
  }

  private require(value: string): void {
    if (!this.take(value)) throw new ExpressionError(`expected ${JSON.stringify(value)}`);
  }

  parse(): Expr {
    const result = this.pipeline();
    if (this.i !== this.tokens.length) {
      throw new ExpressionError(`unexpected token ${JSON.stringify(this.tokens[this.i].value)}`);
    }
    return result;
  }

  private pipeline(): Expr {
    let node = this.boolean();
    while (this.take("|")) node = ["pipe", node, this.boolean()];
    return node;
  }

  private boolean(): Expr {
    let node = this.equality();
    while (this.i < this.tokens.length && (this.tokens[this.i].value === "and" || this.tokens[this.i].value === "or")) {
      const op = this.tokens[this.i].value as "and" | "or";
      this.i += 1;
      node = [op, node, this.equality()];
    }
    return node;
  }

  private equality(): Expr {
    const node = this.primary();
    if (this.take("==")) return ["eq", node, this.primary()];
    if (this.take("!=")) return ["ne", node, this.primary()];
    return node;
  }

  private primary(): Expr {
    if (this.take("[")) { this.require("]"); return ["literal", []]; }
    if (this.take("(")) {
      const node = this.pipeline();
      this.require(")");
      return node;
    }
    if (this.take("{")) {
      const fields: Array<[string, Expr]> = [];
      if (!this.take("}")) {
        for (;;) {
          const token = this.tokens[this.i];
          if (!token || (token.kind !== "word" && token.kind !== "literal")) {
            throw new ExpressionError("expected object field name");
          }
          const key = String(token.value);
          this.i += 1;
          if (fields.some(([existing]) => existing === key)) {
            throw new ExpressionError(`duplicate object field ${JSON.stringify(key)}`);
          }
          this.require(":");
          fields.push([key, this.pipeline()]);
          if (this.take("}")) break;
          this.require(",");
        }
      }
      return ["object", fields];
    }
    if (this.take(".")) {
      let node: Expr = ["input"];
      while (this.take("[")) {
        const token = this.tokens[this.i];
        if (!token || (token.kind !== "number" && token.kind !== "literal")) {
          throw new ExpressionError("expected array index or object key");
        }
        const key = token.value as number | string;
        this.i += 1;
        this.require("]");
        node = ["index", node, key];
      }
      return node;
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
}

const compiled = new Map<string, Expr>();

export function compileExpression(expression: string): Expr {
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

function truth(value: unknown): boolean {
  return value !== null && value !== false;
}

function sameType(a: unknown, b: unknown): boolean {
  if (a === null || b === null) return a === null && b === null;
  if (Array.isArray(a) || Array.isArray(b)) return Array.isArray(a) && Array.isArray(b);
  if (typeof a === "object" || typeof b === "object") {
    return typeof a === "object" && typeof b === "object" && !Array.isArray(a) && !Array.isArray(b);
  }
  return typeof a === typeof b;
}

export function evaluateExpression(expr: Expr, value: unknown): unknown {
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
    const out: Record<string, unknown> = {};
    for (const [key, child] of expr[1]) out[key] = evaluateExpression(child, value);
    return out;
  }
  if (op === "length") {
    if (typeof value === "string") return Array.from(value).length;
    if (Array.isArray(value)) return value.length;
    if (value && typeof value === "object") return Object.keys(value as object).length;
    throw new ExpressionError("length requires a string, array, or object");
  }
  if (op === "to_entries") {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return Object.entries(value as Record<string, unknown>).map(([key, item]) => ({ key, value: item }));
    }
    if (Array.isArray(value)) {
      return value.map((item, index) => ({ key: index, value: item }));
    }
    throw new ExpressionError("to_entries requires an array or object");
  }
  if (op === "index") {
    const obj = evaluateExpression(expr[1], value);
    const key = expr[2];
    if (Array.isArray(obj) && typeof key === "number") return key >= 0 && key < obj.length ? obj[key] : null;
    if (obj && typeof obj === "object" && !Array.isArray(obj) && typeof key === "string") {
      return (obj as Record<string, unknown>)[key] ?? null;
    }
    throw new ExpressionError("index requires an array index or object key");
  }
  if (op === "eq" || op === "ne") {
    const a = evaluateExpression(expr[1], value);
    const b = evaluateExpression(expr[2], value);
    const equal =
      sameType(a, b) &&
      (typeof a === "object" && a !== null ? JSON.stringify(a) === JSON.stringify(b) : a === b);
    return op === "eq" ? equal : !equal;
  }
  if (op === "and" || op === "or") {
    const left = truth(evaluateExpression(expr[1], value));
    return op === "and" ? left && truth(evaluateExpression(expr[2], value)) : left || truth(evaluateExpression(expr[2], value));
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

export type SchemaLike = { statements?: YangStatement[] };

export class Normalization {
  private readonly implementation: InstanceNormalization;

  constructor(module: YangModule) {
    this.implementation = new InstanceNormalization(module);
  }

  get expandDottedKeys(): boolean {
    return this.implementation.expandDotted;
  }

  rules(schema: SchemaLike): ReturnType<InstanceNormalization["rules"]> {
    return this.implementation.rules(schema, "import_prefixes" in schema);
  }

  prepare(schema: SchemaLike, children: (schema: SchemaLike) => YangStatement[]): void {
    this.rules(schema);
    for (const child of children(schema)) this.prepare(child, children);
  }

  visit(schema: SchemaLike, value: unknown): [unknown, string | null] {
    try {
      return [this.implementation.visit(schema as YangStatement, value), null];
    } catch (exc) {
      if (exc instanceof ExpressionError) return [value, exc.message];
      throw exc;
    }
  }
}

export type ExpandedObject = Record<string, unknown>;

const POINTER_MAP = new WeakMap<object, Record<string, string>>();

function join(prefix: string, token: string): string {
  const escaped = token.replace(/~/g, "~0").replace(/\//g, "~1");
  return `${prefix}/${escaped}`;
}

function pointersOf(data: object): Record<string, string> | undefined {
  return POINTER_MAP.get(data);
}

function asExpanded(data: Record<string, unknown>, prefix: string): ExpandedObject {
  const existing = POINTER_MAP.get(data);
  const pointers = existing
    ? { ...existing }
    : Object.fromEntries(Object.keys(data).map((key) => [key, join(prefix, key)]));
  const out: ExpandedObject = { ...data };
  POINTER_MAP.set(out, pointers);
  return out;
}

export function expandDottedObject(
  data: Record<string, unknown>,
  prefix: string
): [ExpandedObject, [string, string] | null] {
  const result = asExpanded(data, prefix);
  const resultPointers = POINTER_MAP.get(result)!;
  const dotted = Object.keys(result).filter((key) => key.includes("."));
  for (const key of dotted) {
    const value = result[key];
    delete result[key];
    const pointer = resultPointers[key];
    delete resultPointers[key];
    const parts = key.split(".");
    if (parts.some((part) => !part)) return [result, [pointer, `invalid dotted key ${JSON.stringify(key)}`]];
    let current: ExpandedObject = result;
    let currentPointers = resultPointers;
    for (const part of parts.slice(0, -1)) {
      if (!(part in current)) {
        current[part] = asExpanded({}, pointer);
        currentPointers[part] = pointer;
      } else if (!current[part] || typeof current[part] !== "object" || Array.isArray(current[part])) {
        return [result, [pointer, `dotted key ${JSON.stringify(key)} conflicts with ${JSON.stringify(part)}`]];
      } else if (!POINTER_MAP.has(current[part] as object)) {
        current[part] = asExpanded(current[part] as Record<string, unknown>, currentPointers[part]);
      } else {
        const copy = asExpanded({}, pointer);
        Object.assign(copy, current[part]);
        POINTER_MAP.set(copy, { ...POINTER_MAP.get(current[part] as object)! });
        current[part] = copy;
      }
      current = current[part] as ExpandedObject;
      currentPointers = POINTER_MAP.get(current)!;
    }
    const final = parts[parts.length - 1];
    if (final in current) {
      return [result, [pointer, `dotted key ${JSON.stringify(key)} conflicts with an existing member`]];
    }
    current[final] = value;
    currentPointers[final] = pointer;
  }
  return [result, null];
}

export function memberPointer(data: object, key: string, prefix: string): string {
  return pointersOf(data)?.[key] ?? join(prefix, key);
}
