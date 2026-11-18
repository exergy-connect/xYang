import { YangModule, YangStatement } from "../core/model";
import { XPathEvaluator, XPathNode } from "../xpath/evaluator";
import { parseXPath } from "../xpath/parser";

type Expr = (v: unknown) => unknown;
type Rule = [Expr, Expr];
const object = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v);
const truth = (v: unknown): boolean => v !== false && v !== null;

class Parser {
  private tokens: string[] = [];
  private at = 0;
  constructor(text: string) {
    const rx = /\s*("(?:[^"\\]|\\.)*"|[A-Za-z_][A-Za-z_0-9-]*|[0-9]+|==|!=|[.\[\]{}():,|])/y;
    let pos = 0;
    while (pos < text.length && text.slice(pos).trim()) {
      rx.lastIndex = pos; const match = rx.exec(text);
      if (!match) throw new Error(`unsupported expression syntax at offset ${pos}`);
      this.tokens.push(match[1]); pos = rx.lastIndex;
    }
  }
  private take(s: string): boolean { if (this.tokens[this.at] !== s) return false; this.at++; return true; }
  private need(s: string): void { if (!this.take(s)) throw new Error(`expected '${s}'`); }
  parse(): Expr { const e = this.pipe(); if (this.at !== this.tokens.length) throw new Error(`unexpected token '${this.tokens[this.at]}'`); return e; }
  private pipe(): Expr { let e = this.boolean(); while (this.take("|")) { const a = e, b = this.boolean(); e = v => b(a(v)); } return e; }
  private boolean(): Expr {
    let e = this.equal();
    while (["and", "or"].includes(this.tokens[this.at])) {
      const op = this.tokens[this.at++], a = e, b = this.equal();
      e = v => op === "and" ? truth(a(v)) && truth(b(v)) : truth(a(v)) || truth(b(v));
    }
    return e;
  }
  private equal(): Expr {
    let e = this.primary(); const op = this.tokens[this.at];
    if (op === "==" || op === "!=") { this.at++; const a = e, b = this.primary(); e = v => op === "==" ? a(v) === b(v) : a(v) !== b(v); }
    return e;
  }
  private primary(): Expr {
    if (this.take("[")) { this.need("]"); return () => []; }
    if (this.take("(")) { const e = this.pipe(); this.need(")"); return e; }
    if (this.take("{")) {
      const fields: Array<[string, Expr]> = [];
      if (!this.take("}")) while (true) {
        const raw = this.tokens[this.at++]; if (!raw || (!/^[A-Za-z_]/.test(raw) && !raw.startsWith('"'))) throw new Error("expected object field name");
        const key: string = raw.startsWith('"') ? JSON.parse(raw) : raw;
        if (fields.some(([name]) => name === key)) throw new Error(`duplicate object field '${key}'`);
        this.need(":"); fields.push([key, this.pipe()]); if (this.take("}")) break; this.need(",");
      }
      return v => Object.fromEntries(fields.map(([key, e]) => [key, e(v)]));
    }
    if (this.take(".")) {
      let e: Expr = v => v;
      while (this.take("[")) {
        const raw = this.tokens[this.at++]; if (!raw || (!/^\d+$/.test(raw) && !raw.startsWith('"'))) throw new Error("expected array index or object key");
        const key: string | number = raw.startsWith('"') ? JSON.parse(raw) : Number(raw); this.need("]"); const a = e;
        e = v => { const x = a(v); if (Array.isArray(x) && typeof key === "number") return x[key] ?? null;
          if (object(x) && typeof key === "string") return x[key] ?? null; throw new Error("index requires an array index or object key"); };
      }
      return e;
    }
    const word = this.tokens[this.at++]; if (!word) throw new Error("expected expression");
    if (word.startsWith('"')) { const x: unknown = JSON.parse(word); return () => x; }
    if (/^\d+$/.test(word)) return () => Number(word);
    if (["true", "false", "null"].includes(word)) return () => word === "null" ? null : word === "true";
    if (word === "type") return v => v === null ? "null" : Array.isArray(v) ? "array" : object(v) ? "object" : typeof v;
    if (word === "length") return v => { if (typeof v === "string") return Array.from(v).length; if (Array.isArray(v)) return v.length; if (object(v)) return Object.keys(v).length; throw new Error("length requires a string, array, or object"); };
    if (word === "to_entries") return v => { if (object(v)) return Object.entries(v).map(([key, value]) => ({key, value})); if (Array.isArray(v)) return v.map((value, key) => ({key, value})); throw new Error("to_entries requires an array or object"); };
    if (["contains", "split", "has"].includes(word)) {
      this.need("("); const arg = this.pipe(); this.need(")");
      return v => { const x = arg(v); if (word === "has") {
        if (object(v) && typeof x === "string") return Object.hasOwn(v, x);
        if (Array.isArray(v) && typeof x === "number" && Number.isInteger(x)) return x >= 0 && x < v.length;
        throw new Error("has requires an object key or array index"); }
        if (typeof v !== "string" || typeof x !== "string") throw new Error(`${word} requires string input and argument`);
        return word === "contains" ? v.includes(x) : x === "" ? Array.from(v) : v.split(x); };
    }
    throw new Error(`unsupported function or identifier '${word}'`);
  }
}

function ext(stmt: YangStatement, name: string): boolean { return stmt.resolved_module_name === "xyang-transform" && stmt.resolved_extension_name === name; }

export class Normalization {
  readonly expandDotted: boolean;
  private compiled = new WeakMap<object, Rule[]>();
  private annotated = new WeakSet<object>();
  rootContext?: () => XPathNode;
  skipProjection = false;
  private compile(s: string | undefined): Expr {
    if (s === undefined) throw new Error("normalization expression is required");
    const stringMap = /^\s*map\s*\(\s*split\s*\(\s*("(?:[^"\\]|\\.)*")\s*\)\s*,\s*([A-Za-z_][A-Za-z_0-9-]*)\s*:\s*\{\s*([A-Za-z_][A-Za-z_0-9-]*)\s*:\s*\$value\s*\}\s*\)\s*$/.exec(s);
    if (stringMap) {
      const delimiter: unknown = JSON.parse(stringMap[1]);
      if (typeof delimiter !== "string") throw new Error("split requires string input and argument");
      return value => {
        if (typeof value !== "string") throw new Error("split requires string input and argument");
        const parts = delimiter === "" ? Array.from(value) : value.split(delimiter);
        return { [stringMap[2]]: parts.map(part => ({ [stringMap[3]]: part })) };
      };
    }
    const match = /^\s*map\s*\(\s*keys\s*\(\s*(\/[^()]*)\s*\)\s*,\s*([A-Za-z_][A-Za-z_0-9-]*)\s*:\s*\{\s*([A-Za-z_][A-Za-z_0-9-]*)\s*:\s*\$key\s*,\s*\.\.\.\$value\s*\}\s*\)\s*$/.exec(s);
    if (!match) return new Parser(s).parse();
    const path = parseXPath(match[1].trim());
    return value => {
      if (this.skipProjection) return value;
      if (!object(value)) throw new Error("key projection requires an object");
      const [, , target, keyField] = match;
      if (!this.rootContext) throw new Error("key projection requires an instance root");
      const root = this.rootContext();
      const selected = new XPathEvaluator().eval(path, { current: root, root }, root);
      if (!Array.isArray(selected) || selected.some(n => !n || typeof n !== "object" || typeof n.data !== "string")) throw new Error("keys XPath must select string nodes");
      const matches = new Set(selected.map(n => n.data as string));
      if (!Object.keys(value).some(key => matches.has(key))) return value;
      if (Object.hasOwn(value, target)) throw new Error(`projection target '${target}' already exists`);
      const result: Record<string, unknown> = Object.create(null), rows: Record<string, unknown>[] = [];
      for (const [key, item] of Object.entries(value)) {
        if (!matches.has(key)) { result[key] = item; continue; }
        if (item !== null && !object(item)) throw new Error(`value for '${key}' must be an object or null`);
        if (object(item) && Object.hasOwn(item, keyField)) throw new Error(`projected key field '${keyField}' already exists`);
        rows.push({ [keyField]: key, ...(item ?? {}) });
      }
      result[target] = rows; return result;
    };
  }
  constructor(module: YangModule) {
    const opts = (module.statements ?? []).filter(s => ext(s, "expand-dotted-keys"));
    if (opts.length > 1) throw new Error("duplicate module option 'expand_dotted_keys'");
    const option = opts[0];
    if (option && ((option.argument !== "true" && option.argument !== "false") || option.statements?.length)) throw new Error("xt:expand-dotted-keys requires true or false and no body");
    this.expandDotted = option?.argument === "true";
  }
  rules(schema: { statements?: YangStatement[] }, isModule = false): Rule[] {
    const old = this.compiled.get(schema); if (old) return old;
    const result: Rule[] = [];
    for (const stmt of schema.statements ?? []) {
      if (!isModule && ext(stmt, "expand-dotted-keys")) throw new Error("xt:expand-dotted-keys is allowed only at module level");
      if (!ext(stmt, "normalize")) continue;
      if (stmt.argument !== undefined) throw new Error("xt:normalize does not take an argument");
      this.annotated.add(schema); const clauses = stmt.statements ?? [];
      if (clauses.length === 2 && ext(clauses[0], "if") && !clauses[0].statements?.length && ext(clauses[1], "apply")) {
        if (clauses[1].statements?.length) throw new Error("xt:apply requires an expression and no body");
        result.push([this.compile(clauses[0].argument), this.compile(clauses[1].argument)]);
      } else if (clauses.length && clauses.every(s => ext(s, "if"))) {
        for (const clause of clauses) { const parts = clause.statements ?? [];
          if (parts.length !== 1 || !ext(parts[0], "apply") || parts[0].statements?.length) throw new Error("nested xt:if requires exactly one xt:apply");
          result.push([this.compile(clause.argument), this.compile(parts[0].argument)]); }
      } else throw new Error("xt:normalize requires exactly xt:if followed by xt:apply");
    }
    this.compiled.set(schema, result); return result;
  }
  collection(schema: YangStatement, value: unknown): unknown { this.rules(schema); return value === null && this.annotated.has(schema) ? [] : value; }
  visit(schema: YangStatement, value: unknown): unknown { for (const [test, apply] of this.rules(schema)) if (truth(test(value))) value = apply(value); return value; }
}
