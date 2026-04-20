import { YangModule } from "../core/model";
import { isDerivedFromOrSelfQNames, isDerivedFromStrictQNames } from "../identity-graph";
import { XPathAstNode, XPathBinaryNode, XPathPathNode } from "./ast";

export type XPathSchema = {
  keyword?: string;
  name?: string;
  data?: Record<string, unknown>;
  statements?: XPathSchema[];
};

export type XPathNode = {
  data: unknown;
  schema: XPathSchema | null;
  parent: XPathNode | null;
};

export type XPathContext = {
  current: XPathNode;
  root: XPathNode;
};

function isNode(value: unknown): value is XPathNode {
  return Boolean(value) && typeof value === "object" && "schema" in (value as Record<string, unknown>) && "parent" in (value as Record<string, unknown>);
}

function isNodeSet(value: unknown): value is XPathNode[] {
  return Array.isArray(value) && (value.length === 0 || isNode(value[0]));
}

function toYangBool(value: unknown): boolean {
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
  return value !== null && value !== undefined;
}

function nodeSetValues(value: unknown): unknown[] {
  if (Array.isArray(value)) {
    return value.map((item) => (isNode(item) ? item.data : item));
  }
  if (isNode(value)) {
    return [value.data];
  }
  if (value === undefined || value === null) {
    return [];
  }
  return [value];
}

function firstValue(value: unknown): unknown {
  const values = nodeSetValues(value);
  return values[0];
}

function coercePair(left: unknown, right: unknown): [unknown, unknown] {
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

function compareEq(left: unknown, right: unknown): boolean {
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

function compareLt(left: unknown, right: unknown): boolean {
  for (const leftValue of nodeSetValues(left)) {
    for (const rightValue of nodeSetValues(right)) {
      const [cl, cr] = coercePair(leftValue, rightValue);
      if (typeof cl === "number" && typeof cr === "number") {
        if (cl < cr) {
          return true;
        }
        continue;
      }
      if (`${cl}` < `${cr}`) {
        return true;
      }
    }
  }
  return false;
}

function compareGt(left: unknown, right: unknown): boolean {
  for (const leftValue of nodeSetValues(left)) {
    for (const rightValue of nodeSetValues(right)) {
      const [cl, cr] = coercePair(leftValue, rightValue);
      if (typeof cl === "number" && typeof cr === "number") {
        if (cl > cr) {
          return true;
        }
        continue;
      }
      if (`${cl}` > `${cr}`) {
        return true;
      }
    }
  }
  return false;
}

function getSchemaChildren(schema: XPathSchema | null): XPathSchema[] {
  if (!schema || !Array.isArray(schema.statements)) {
    return [];
  }
  return schema.statements;
}

function findSchemaChild(schema: XPathSchema | null, name: string): XPathSchema | null {
  for (const child of getSchemaChildren(schema)) {
    if (child?.name === name) {
      return child;
    }
  }
  return null;
}

function defaultValue(schema: XPathSchema | null): unknown {
  if (!schema || schema.keyword !== "leaf") {
    return undefined;
  }
  const raw = schema.data?.default;
  const typeName = (schema.data?.type as Record<string, unknown> | undefined)?.name;
  if (typeName === "boolean" && typeof raw === "string") {
    const lower = raw.toLowerCase();
    if (lower === "true") return true;
    if (lower === "false") return false;
  }
  return raw;
}

function stepNode(node: XPathNode, step: string): XPathNode[] {
  const data = node.data;
  const schema = node.schema;

  if (Array.isArray(data) && (schema?.keyword === "list" || schema?.keyword === "leaf-list")) {
    const expanded: XPathNode[] = [];
    for (const item of data) {
      const entryNode: XPathNode = { data: item, schema, parent: node };
      expanded.push(...stepNode(entryNode, step));
    }
    return expanded;
  }

  const childSchema = findSchemaChild(schema, step);

  let value: unknown;
  if (data && typeof data === "object" && !Array.isArray(data)) {
    const asRecord = data as Record<string, unknown>;
    if (step in asRecord) {
      value = asRecord[step];
      if (value === null) {
        value = true;
      }
    } else {
      value = defaultValue(childSchema);
    }
  }

  if (value === undefined) {
    return [];
  }

  if (childSchema?.keyword === "list" || childSchema?.keyword === "leaf-list") {
    if (Array.isArray(value)) {
      return value.map((item) => ({ data: item, schema: childSchema, parent: node }));
    }
    return [{ data: value, schema: childSchema, parent: node }];
  }

  return [{ data: value, schema: childSchema, parent: node }];
}

export class XPathEvaluator {
  eval(ast: XPathAstNode, context: XPathContext, node: XPathNode): unknown {
    switch (ast.kind) {
      case "literal":
        return ast.value;
      case "path":
        return this.evalPath(ast, context, node);
      case "binary":
        return this.evalBinary(ast, context, node);
      case "function":
        return this.evalFunction(ast.name, ast.args, context, node);
      default:
        return null;
    }
  }

  evalPath(path: XPathPathNode, context: XPathContext, node: XPathNode): XPathNode[] {
    let nodes: XPathNode[] = [path.isAbsolute ? context.root : node];

    for (const segment of path.segments) {
      if (segment.step === ".") {
        // keep current nodes
      } else if (segment.step === "..") {
        nodes = nodes.map((entry) => entry.parent).filter((entry): entry is XPathNode => Boolean(entry));
      } else {
        const next: XPathNode[] = [];
        for (const entry of nodes) {
          next.push(...stepNode(entry, segment.step));
        }
        nodes = next;
      }

      if (segment.predicate) {
        const filtered: XPathNode[] = [];
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

  private evalBinary(ast: XPathBinaryNode, context: XPathContext, node: XPathNode): unknown {
    const op = ast.operator;

    if (op === "or") {
      const left = this.eval(ast.left, context, node);
      if (toYangBool(left)) {
        return true;
      }
      return toYangBool(this.eval(ast.right, context, node));
    }

    if (op === "and") {
      const left = this.eval(ast.left, context, node);
      if (!toYangBool(left)) {
        return false;
      }
      return toYangBool(this.eval(ast.right, context, node));
    }

    if (op === "/") {
      const left = this.eval(ast.left, context, node);
      const leftNodes = isNodeSet(left) ? left : isNode(left) ? [left] : [];
      const results: XPathNode[] = [];
      for (const leftNode of leftNodes) {
        const right = this.eval(ast.right, context, leftNode);
        if (isNodeSet(right)) {
          results.push(...right);
        } else if (isNode(right)) {
          results.push(right);
        }
      }
      return results;
    }

    const left = this.eval(ast.left, context, node);
    const right = this.eval(ast.right, context, node);

    if (op === "=") {
      return compareEq(left, right);
    }
    if (op === "!=") {
      return !compareEq(left, right);
    }
    if (op === "<") {
      return compareLt(left, right);
    }
    if (op === ">") {
      return compareGt(left, right);
    }
    if (op === "<=") {
      return compareEq(left, right) || compareLt(left, right);
    }
    if (op === ">=") {
      return compareEq(left, right) || compareGt(left, right);
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

    return null;
  }

  private evalFunction(name: string, args: XPathAstNode[], context: XPathContext, node: XPathNode): unknown {
    const fn = name.toLowerCase();

    if (fn === "current") {
      return context.current;
    }
    if (fn === "not") {
      if (args.length !== 1) {
        return null;
      }
      return !toYangBool(this.eval(args[0], context, node));
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
      const value = this.eval(args[0], context, node);
      return isNodeSet(value) ? value.length : value == null ? 0 : 1;
    }
    if (fn === "string") {
      if (args.length !== 1) {
        return "";
      }
      const value = firstValue(this.eval(args[0], context, node));
      return value == null ? "" : String(value);
    }
    if (fn === "number") {
      if (args.length !== 1) {
        return Number.NaN;
      }
      const value = firstValue(this.eval(args[0], context, node));
      const numberValue = Number(value);
      return Number.isNaN(numberValue) ? Number.NaN : numberValue;
    }
    if (fn === "boolean") {
      if (args.length !== 1) {
        return false;
      }
      return toYangBool(this.eval(args[0], context, node));
    }
    if (fn === "string-length") {
      if (args.length !== 1) {
        return 0;
      }
      const value = firstValue(this.eval(args[0], context, node));
      return value == null ? 0 : String(value).length;
    }
    if (fn === "concat") {
      return args.map((arg) => String(firstValue(this.eval(arg, context, node)) ?? "")).join("");
    }
    if (fn === "translate") {
      if (args.length !== 3) {
        return "";
      }
      const source = String(firstValue(this.eval(args[0], context, node)) ?? "");
      const fromChars = String(firstValue(this.eval(args[1], context, node)) ?? "");
      const toChars = String(firstValue(this.eval(args[2], context, node)) ?? "");
      if (fromChars.length === 0) {
        return source;
      }
      const map = new Map<string, string | null>();
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
      const start = context.current ?? node;
      const raw = this.eval(args[0], context, start);
      const sourceNodes = isNodeSet(raw) ? raw : isNode(raw) ? [raw] : [];
      const results: XPathNode[] = [];
      for (const sourceNode of sourceNodes) {
        const typeShape = sourceNode.schema?.data?.type as Record<string, unknown> | undefined;
        if (!typeShape || typeShape.name !== "leafref") {
          continue;
        }
        const leafrefPath = typeShape.path as XPathPathNode | undefined;
        if (!leafrefPath || leafrefPath.kind !== "path") {
          continue;
        }
        const targets = this.evalPath(leafrefPath, context, sourceNode);
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
      const start = context.current ?? node;
      let v1: unknown = this.eval(args[0], context, start);
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

    return null;
  }
}

export function evaluateXPath(ast: XPathAstNode, context: XPathContext, node: XPathNode): unknown {
  return new XPathEvaluator().eval(ast, context, node);
}
