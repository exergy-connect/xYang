import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, parseYangFile, YangValidator } from "../../src";

const dir = mkdtempSync(join(tmpdir(), "xyang-typedef-chain-"));
writeFileSync(join(dir, "base.yang"), `module base { yang-version 1.1; namespace "urn:base"; prefix b;
  typedef mac { type string { pattern '[0-9a-f]{2}'; } }
}`);
writeFileSync(join(dir, "middle.yang"), `module middle { yang-version 1.1; namespace "urn:middle"; prefix m;
  import base { prefix b; }
  typedef unicast { type b:mac { pattern '[0-9a-f][02468ace]'; } }
}`);
writeFileSync(join(dir, "top.yang"), `module top { yang-version 1.1; namespace "urn:top"; prefix t;
  import middle { prefix m; }
  leaf address { type m:unicast { pattern '[0-7].*'; } }
  leaf-list addresses { type m:unicast; }
}`);
const original = parseYangFile(join(dir, "top.yang"), { includePath: [dir], expandUses: true });

describe("imported typedef restrictions", () => {
  const schema = generateJsonSchema(original).schema;
  const restored = parseJsonSchema(JSON.parse(JSON.stringify(schema)));
  it.each([
    [{ address: "12", addresses: ["ae"] }, true],
    [{ address: "zz" }, false],
    [{ address: "13" }, false],
    [{ address: "82" }, false],
    [{ addresses: ["af"] }, false],
  ])("preserves validation for %j", (value, expected) => {
    expect(new YangValidator(original).validate(value, { nativeJson: true }).isValid).toBe(expected);
    expect(new YangValidator(restored).validate(value, { nativeJson: true }).isValid).toBe(expected);
  });
  it("preserves the exported form after reimport", () => {
    expect(generateJsonSchema(restored).schema).toEqual(schema);
  });
});
