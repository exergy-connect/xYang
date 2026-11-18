import { YangModule, YangStatement } from "../core/model";
import { XPathEvaluator, XPathNode } from "../xpath/evaluator";
import { parseXPath } from "../xpath/parser";
import { compileExpression, evaluateExpression, ExpressionError } from "../ext/transform";

type Expr = (v: unknown) => unknown;
type Rule = [Expr, Expr];
const object = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v);
const truth = (v: unknown): boolean => v !== false && v !== null;

function ext(stmt: YangStatement, name: string): boolean { return stmt.resolved_module_name === "xyang-transform" && stmt.resolved_extension_name === name; }

export class Normalization {
  readonly expandDotted: boolean;
  private compiled = new WeakMap<object, Rule[]>();
  private annotated = new WeakSet<object>();
  rootContext?: () => XPathNode;
  skipProjection = false;
  private compile(s: string | undefined): Expr {
    if (s === undefined) throw new ExpressionError("normalization expression is required");
    const stringMap = /^\s*map\s*\(\s*split\s*\(\s*("(?:[^"\\]|\\.)*")\s*\)\s*,\s*([A-Za-z_][A-Za-z_0-9-]*)\s*:\s*\{\s*([A-Za-z_][A-Za-z_0-9-]*)\s*:\s*\$value\s*\}\s*\)\s*$/.exec(s);
    if (stringMap) {
      const delimiter: unknown = JSON.parse(stringMap[1]);
      if (typeof delimiter !== "string") throw new ExpressionError("split requires string input and argument");
      return value => {
        if (typeof value !== "string") throw new ExpressionError("split requires string input and argument");
        const parts = delimiter === "" ? Array.from(value) : value.split(delimiter);
        return { [stringMap[2]]: parts.map(part => ({ [stringMap[3]]: part })) };
      };
    }
    const match = /^\s*map\s*\(\s*keys\s*\(\s*(\/[^()]*)\s*\)\s*,\s*([A-Za-z_][A-Za-z_0-9-]*)\s*:\s*\{\s*([A-Za-z_][A-Za-z_0-9-]*)\s*:\s*\$key\s*,\s*\.\.\.\$value\s*\}\s*\)\s*$/.exec(s);
    if (!match) { const expr = compileExpression(s); return value => evaluateExpression(expr, value); }
    const path = parseXPath(match[1].trim());
    return value => {
      if (this.skipProjection) return value;
      if (!object(value)) throw new ExpressionError("key projection requires an object");
      const [, , target, keyField] = match;
      if (!this.rootContext) throw new ExpressionError("key projection requires an instance root");
      const root = this.rootContext();
      const selected = new XPathEvaluator().eval(path, { current: root, root }, root);
      if (!Array.isArray(selected) || selected.some(n => !n || typeof n !== "object" || typeof n.data !== "string")) throw new ExpressionError("keys XPath must select string nodes");
      const matches = new Set(selected.map(n => n.data as string));
      if (!Object.keys(value).some(key => matches.has(key))) return value;
      if (Object.hasOwn(value, target)) throw new ExpressionError(`projection target '${target}' already exists`);
      const result: Record<string, unknown> = Object.create(null), rows: Record<string, unknown>[] = [];
      for (const [key, item] of Object.entries(value)) {
        if (!matches.has(key)) { result[key] = item; continue; }
        if (item !== null && !object(item)) throw new ExpressionError(`value for '${key}' must be an object or null`);
        if (object(item) && Object.hasOwn(item, keyField)) throw new ExpressionError(`projected key field '${keyField}' already exists`);
        rows.push({ [keyField]: key, ...(item ?? {}) });
      }
      result[target] = rows; return result;
    };
  }
  constructor(module: YangModule) {
    const opts = (module.statements ?? []).filter(s => ext(s, "expand-dotted-keys"));
    if (opts.length > 1) throw new ExpressionError("duplicate module option 'expand_dotted_keys'");
    const option = opts[0];
    if (option && ((option.argument !== "true" && option.argument !== "false") || option.statements?.length)) throw new ExpressionError("xt:expand-dotted-keys requires true or false and no body");
    this.expandDotted = option?.argument === "true";
  }
  rules(schema: { statements?: YangStatement[] }, isModule = false): Rule[] {
    const old = this.compiled.get(schema); if (old) return old;
    const result: Rule[] = [];
    for (const stmt of schema.statements ?? []) {
      if (!isModule && ext(stmt, "expand-dotted-keys")) throw new ExpressionError("xt:expand-dotted-keys is allowed only at module level");
      if (!ext(stmt, "normalize")) continue;
      if (stmt.argument !== undefined) throw new ExpressionError("xt:normalize does not take an argument");
      this.annotated.add(schema); const clauses = stmt.statements ?? [];
      if (clauses.length === 1 && ext(clauses[0], "apply") && !clauses[0].statements?.length) {
        result.push([() => true, this.compile(clauses[0].argument)]);
      } else if (clauses.length === 2 && ext(clauses[0], "if") && !clauses[0].statements?.length && ext(clauses[1], "apply")) {
        if (clauses[1].statements?.length) throw new ExpressionError("xt:apply requires an expression and no body");
        result.push([this.compile(clauses[0].argument), this.compile(clauses[1].argument)]);
      } else if (clauses.length && clauses.every(s => ext(s, "if"))) {
        for (const clause of clauses) { const parts = clause.statements ?? [];
          if (parts.length !== 1 || !ext(parts[0], "apply") || parts[0].statements?.length) throw new ExpressionError("nested xt:if requires exactly one xt:apply");
          result.push([this.compile(clause.argument), this.compile(parts[0].argument)]); }
      } else throw new ExpressionError("xt:normalize requires exactly xt:if followed by xt:apply");
    }
    this.compiled.set(schema, result); return result;
  }
  collection(schema: YangStatement, value: unknown): unknown { this.rules(schema); return value === null && this.annotated.has(schema) ? [] : value; }
  visit(schema: YangStatement, value: unknown): unknown { for (const [test, apply] of this.rules(schema)) if (truth(test(value))) value = apply(value); return value; }
}
