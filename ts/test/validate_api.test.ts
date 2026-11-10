// One-call validate returns validateDetailed's object (#82).
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { parseYangString, validate } from "../src";

const MODULE = `
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  container top {
    leaf name { type string; }
  }
}
`;

describe("validate", () => {
  it("accepts a valid instance from a path", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-validate-"));
    const yang = join(dir, "m.yang");
    writeFileSync(yang, MODULE);
    const result = validate(yang, { top: { name: "example" } });
    expect(result.valid).toBe(true);
    expect(result.errors).toEqual([]);
    expect(result.warnings).toEqual([]);
  });

  it("reports a structured error for a parsed module", () => {
    const result = validate(parseYangString(MODULE), { top: { missing: 1 } });
    expect(result.valid).toBe(false);
    expect(result.warnings).toEqual([]);
    expect(result.errors).toEqual([
      {
        code: "unknown-field",
        path: "/top/missing",
        message: "Unknown field 'missing'",
        severity: "error"
      }
    ]);
  });
});
