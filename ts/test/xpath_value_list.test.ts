import { describe, expect, it } from "vitest";
import { parseXPath } from "../src/xpath/parser";
import { XPathEvaluator, type XPathContext, type XPathNode } from "../src/xpath/evaluator";

function xpathBoolean(value: unknown): boolean {
  if (value === true || value === false) {
    return value;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return value !== 0;
  }
  if (typeof value === "string") {
    return value.length > 0;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  return value != null;
}

describe("python parity: test_xpath_value_list", () => {
  it("parses value list in equality", () => {
    const ast = parseXPath("../type = ('string', 'integer', 'number')");
    expect(ast).toBeDefined();
  });

  it("evaluates type = ('string', 'integer', 'number') true when type is integer", () => {
    const rootData = { type: "integer" };
    const root: XPathNode = { data: rootData, schema: null, parent: null };
    const ctx: XPathContext = { current: root, root };
    const ev = new XPathEvaluator();
    const ast = parseXPath("type = ('string', 'integer', 'number')");
    const result = ev.eval(ast, ctx, root);
    expect(xpathBoolean(result)).toBe(true);
  });

  it("evaluates type = ('string', 'integer') false when type is number", () => {
    const rootData = { type: "number" };
    const root: XPathNode = { data: rootData, schema: null, parent: null };
    const ctx: XPathContext = { current: root, root };
    const ev = new XPathEvaluator();
    const ast = parseXPath("type = ('string', 'integer')");
    const result = ev.eval(ast, ctx, root);
    expect(xpathBoolean(result)).toBe(false);
  });

  it("evaluates numeric value list x = (1, 2, 3) when x is 2", () => {
    const rootData = { x: 2 };
    const root: XPathNode = { data: rootData, schema: null, parent: null };
    const ctx: XPathContext = { current: root, root };
    const ev = new XPathEvaluator();
    const ast = parseXPath("x = (1, 2, 3)");
    const result = ev.eval(ast, ctx, root);
    expect(xpathBoolean(result)).toBe(true);
  });
});
