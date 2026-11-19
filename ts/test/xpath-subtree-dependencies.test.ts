import { describe, expect, it } from "vitest";
import { expressionIsWithinSubtree } from "../src/xpath/subtree-dependencies";

describe("subtree XPath dependencies", () => {
  it.each([
    ["count(nodes) > 0", ["topology"], true],
    ["/m:topology/nodes/name", ["topology", "link"], true],
    ["../nodes/name", ["topology", "link"], true],
    ["../../state/status", ["topology", "link"], false],
    ["nodes[name = /m:state/name]", ["topology"], false],
    ["nodes and /m:state", ["topology"], false],
    ["current()", ["topology"], true],
  ])("classifies %s", (expression, context, expected) => {
    expect(expressionIsWithinSubtree(expression, context, ["topology"])).toBe(expected);
  });
});
