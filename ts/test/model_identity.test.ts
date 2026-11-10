import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { parseYangFile } from "../src";

describe("statement wrapper identity (#73)", () => {
  it("returns the same statement objects for a one-container module", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-model-identity-"));
    const file = join(dir, "demo.yang");
    writeFileSync(
      file,
      `module demo {
  container top {
    leaf name { type string; }
  }
}
`
    );

    const m = parseYangFile(file);
    expect(m.statements[0]).toBe(m.statements[0]);
    expect(m.findStatement("top")).toBe(m.statements[0]);

    const top = m.findStatement("top");
    expect(top?.statements[0]).toBe(top?.statements[0]);
    expect(top?.findStatement("name")).toBe(top?.statements[0]);
  });
});
