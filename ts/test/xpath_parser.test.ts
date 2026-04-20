import { describe, expect, it } from "vitest";
import { XPathSyntaxError } from "../src/core/errors";
import type { XPathBinaryNode, XPathLiteralNode, XPathPathNode } from "../src/xpath/ast";
import { parseXPath } from "../src/xpath/parser";
import { XPathEvaluator, type XPathContext, type XPathNode } from "../src/xpath/evaluator";

function expectParseError(expr: string, matcher: RegExp): void {
  expect(() => parseXPath(expr)).toThrow(XPathSyntaxError);
  try {
    parseXPath(expr);
    expect.fail("expected throw");
  } catch (e) {
    expect(e).toBeInstanceOf(XPathSyntaxError);
    const err = e as XPathSyntaxError;
    expect(err.messageText).toMatch(matcher);
  }
}

describe("python parity: test_xpath_parser", () => {
  it("empty expression raises XPathSyntaxError", () => {
    expectParseError("", /empty expression/i);
  });

  it("trailing token raises XPathSyntaxError", () => {
    expectParseError("1 2", /unexpected token/i);
    expectParseError("a = 1 ,", /unexpected token/i);
  });

  it("unexpected primary token raises XPathSyntaxError", () => {
    expectParseError("]", /unexpected token/i);
  });

  it("missing closing paren in not() raises XPathSyntaxError", () => {
    expectParseError("not( 1", /expected.*paren_close|got/i);
  });

  it("value list missing closing paren raises XPathSyntaxError", () => {
    expectParseError("x = ( 'a' , 'b' ", /expected|got/i);
  });

  it("expression 1/foo parses as binary division-like slash", () => {
    const ast = parseXPath("1 / foo");
    expect(ast.kind).toBe("binary");
    const bin = ast as XPathBinaryNode;
    expect(bin.operator).toBe("/");
    expect(bin.left.kind).toBe("literal");
    expect((bin.left as XPathLiteralNode).value).toBe(1);
    expect(bin.right.kind).toBe("path");
  });

  it("a/b/c parses as a single PathNode", () => {
    const ast = parseXPath("a / b / c");
    expect(ast.kind).toBe("path");
    const path = ast as XPathPathNode;
    expect(path.segments.map((s) => s.step)).toEqual(["a", "b", "c"]);
  });

  it("multiplication 2*3 parses", () => {
    const ast = parseXPath("2 * 3");
    expect(ast.kind).toBe("binary");
    const bin = ast as XPathBinaryNode;
    expect(bin.operator).toBe("*");
    expect((bin.left as XPathLiteralNode).value).toBe(2);
    expect((bin.right as XPathLiteralNode).value).toBe(3);
  });

  it("not(false) parses and evaluates to true", () => {
    const ast = parseXPath("not( false )");
    expect(ast).not.toBeNull();
    const root: XPathNode = { data: {}, schema: null, parent: null };
    const ctx: XPathContext = { current: root, root };
    const result = new XPathEvaluator().eval(ast, ctx, root);
    expect(result).toBe(true);
  });

  it("unary + parses and reduces to inner literal", () => {
    const ast = parseXPath("+ 1");
    expect(ast.kind).toBe("literal");
    expect((ast as XPathLiteralNode).value).toBe(1);
  });

  it("true() parses as literal true", () => {
    const ast = parseXPath("true()");
    expect(ast.kind).toBe("literal");
    expect((ast as XPathLiteralNode).value).toBe(true);
  });

  it("leading .. parses as path", () => {
    const ast = parseXPath("../foo");
    expect(ast.kind).toBe("path");
    const path = ast as XPathPathNode;
    expect(path.segments.length).toBeGreaterThanOrEqual(1);
    expect(path.segments[0].step).toBe("..");
  });

  it("value list with non-literal raises XPathSyntaxError", () => {
    expectParseError("x = ( 1, foo )", /value list may only contain literals/i);
    expectParseError("x = ( 'a', bar )", /value list may only contain literals/i);
  });

  it("single parenthesized literal ( 42 ) parses", () => {
    const ast = parseXPath("( 42 )");
    expect(ast.kind).toBe("literal");
    expect((ast as XPathLiteralNode).value).toBe(42);
  });

  it("path .[1]/a parses with predicate on first step", () => {
    const ast = parseXPath(".[ 1 ] / a");
    expect(ast.kind).toBe("path");
    const path = ast as XPathPathNode;
    expect(path.segments.length).toBeGreaterThanOrEqual(1);
    expect(path.segments[0].step).toBe(".");
    expect(path.segments[0].predicate).toBeDefined();
  });

  it("path ..[x=1] parses with predicate", () => {
    const ast = parseXPath("..[ x = 1 ]");
    expect(ast.kind).toBe("path");
    const path = ast as XPathPathNode;
    expect(path.segments[0].step).toBe("..");
    expect(path.segments[0].predicate).toBeDefined();
  });

  it("path . [1] parses with predicate on dot step", () => {
    const ast = parseXPath(". [ 1 ]");
    expect(ast.kind).toBe("path");
    const path = ast as XPathPathNode;
    expect(path.segments[0].step).toBe(".");
    expect(path.segments[0].predicate).toBeDefined();
  });

  it("path identifier with predicate parses", () => {
    const ast = parseXPath("a[ 1 ]");
    expect(ast.kind).toBe("path");
    const p1 = ast as XPathPathNode;
    expect(p1.segments[0].step).toBe("a");
    expect(p1.segments[0].predicate).toBeDefined();

    const ast2 = parseXPath("foo[ bar = 1 ]");
    expect(ast2.kind).toBe("path");
    const p2 = ast2 as XPathPathNode;
    expect(p2.segments[0].step).toBe("foo");
    expect(p2.segments[0].predicate).toBeDefined();
  });

  it("invalid number literal raises XPathSyntaxError", () => {
    expect(() => parseXPath("1e2e3")).toThrow(XPathSyntaxError);
  });
});
