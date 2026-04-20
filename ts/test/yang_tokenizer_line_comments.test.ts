import { describe, expect, it } from "vitest";
import { parseYangString } from "../src";
import { diagnosticSourceLines } from "../src/parser/parser-context";

describe("python parity: test_yang_tokenizer_line_comments", () => {
  it.each([
    ['  contact "https://github.com/foo";  ', ['  contact "https://github.com/foo";  ']],
    ["  leaf x 'a//b'; // tail", ["  leaf x 'a//b'; // tail"]],
    ['foo "x" // c', ['foo "x" // c']],
    ["no comment", ["no comment"]],
    ["// only comment", ["// only comment"]],
    ["  ", ["  "]]
  ] as const)("diagnosticSourceLines(%j) -> %j", (line, expectedLines) => {
    expect(diagnosticSourceLines(line)).toEqual(expectedLines);
  });

  it("parses module contact with https URL (slashes not treated as comment)", () => {
    const yang = `
module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix "t";
  contact "https://example.org/path";
  container data-model { leaf x { type string; } }
}
`;
    const mod = parseYangString(yang);
    expect(mod.contact).toBe("https://example.org/path");
  });

  it("parses leaf default string containing //", () => {
    const yang = `
module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix "t";
  leaf u {
    type string;
    default "https://example.org/a/b";
  }
}
`;
    const mod = parseYangString(yang);
    const u = mod.findStatement("u");
    expect(u).toBeDefined();
    expect(u?.data.default).toBe("https://example.org/a/b");
  });
});
