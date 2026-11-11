import { describe, expect, it } from "vitest";
import { parseXPath } from "../src/xpath/parser";

describe("python parity: test_xpath_value_list", () => {
  it("parses value list in equality", () => {
    const ast = parseXPath("../type = ('string', 'integer', 'number')");
    expect(ast).toBeDefined();
  });
});
