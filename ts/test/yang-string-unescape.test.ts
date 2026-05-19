import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseYangString } from "../src/parser";
import { unescapeYangQuotedString } from "../src/parser/yang-strings";

describe("RFC 7950 quoted string unescape", () => {
  it("decodes double-quoted backslashes", () => {
    expect(unescapeYangQuotedString("\\\\d{4}", '"')).toBe("\\d{4}");
  });

  it("decodes double-quoted quotes and newlines", () => {
    expect(unescapeYangQuotedString('say \\"hi\\"', '"')).toBe('say "hi"');
    expect(unescapeYangQuotedString("line1\\nline2", '"')).toBe("line1\nline2");
  });

  it("decodes single-quoted backslashes for regex patterns", () => {
    expect(unescapeYangQuotedString("\\\\.", "'")).toBe("\\.");
  });

  it("preserves unrecognized single-quoted escapes", () => {
    expect(unescapeYangQuotedString("\\.[1-3]", "'")).toBe("\\.[1-3]");
  });

  it("date-and-time pattern matches RFC 3339 timestamps", () => {
    const mod = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  typedef date-and-time {
    type string {
      pattern "\\\\d{4}-\\\\d{2}-\\\\d{2}T\\\\d{2}:\\\\d{2}:\\\\d{2}(\\\\.\\\\d+)?"
            + "(Z|[\\\\+\\\\-]\\\\d{2}:\\\\d{2})";
    }
  }
  leaf t { type date-and-time; }
}
`);
    const td = mod.typedefs["date-and-time"] as {
      type?: { patterns?: Array<{ pattern: string }> };
    };
    const pat = td?.type?.patterns?.[0]?.pattern ?? "";
    expect(pat).toMatch(/\\d\{4\}/);
    expect(pat).not.toMatch(/\\\\d/);
    expect("2026-01-22T06:20:36.511Z").toMatch(new RegExp(pat));
  });

  it("ietf-yang-types date-and-time from vendor module", () => {
    const path = resolve(
      "..",
      "examples/ietf-yang-push/modules/ietf-yang-types@2013-07-15.yang"
    );
    const text = readFileSync(path, "utf8");
    const mod = parseYangString(text);
    const td = mod.typedefs["date-and-time"] as {
      type?: { patterns?: Array<{ pattern: string }> };
    };
    const pat = td?.type?.patterns?.[0]?.pattern ?? "";
    expect(pat).toContain("\\d{4}");
    expect(pat).not.toContain("\\\\d{4}");
    expect("2026-01-22T06:20:36.511Z").toMatch(new RegExp(pat));
  });

  it("pattern string concatenation with escapes (parity)", () => {
    const mod = parseYangString(`module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix "t";
  typedef oid {
    type string {
      pattern '(([0-1](\\.[1-3]?[0-9]))|(2\\.(0|([1-9]\\d*))))'
            + '(\\.(0|([1-9]\\d*)))*';
    }
  }
}`);
    const td = mod.typedefs["oid"] as { type?: { patterns?: Array<{ pattern: string }> } };
    const expected =
      "(([0-1](\\.[1-3]?[0-9]))|(2\\.(0|([1-9]\\d*))))" +
      "(\\.(0|([1-9]\\d*)))*";
    expect(td?.type?.patterns?.[0]?.pattern).toBe(expected);
  });
});
