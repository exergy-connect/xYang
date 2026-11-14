import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { YangParser } from "../src/parser/yang-parser";
import { YangValidator } from "../src/validator/yang-validator";

function writeModule(dir: string, name: string, text: string): string {
  const path = join(dir, name);
  writeFileSync(path, text, "utf-8");
  return path;
}

describe("deviate not-supported", () => {
  it("removes an imported leaf so the base module rejects it as an unknown field", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-deviation-"));
    writeModule(
      dir,
      "base.yang",
      `
module base {
  yang-version 1.1;
  namespace "urn:b";
  prefix b;
  container top {
    leaf a { type string; }
    leaf b { type uint8; }
  }
}
`
    );
    const devPath = writeModule(
      dir,
      "dev.yang",
      `
module dev {
  yang-version 1.1;
  namespace "urn:dev";
  prefix d;
  import base { prefix b; }
  deviation "/b:top/b:a" {
    description "a is not used";
    reference "RFC 7950";
    deviate not-supported;
  }
}
`
    );
    const parser = new YangParser();
    const dev = parser.parseFile(devPath);
    const base = dev.import_prefixes.b!;
    const invalid = new YangValidator(base).validate({ top: { a: "x" } });
    expect(invalid.isValid).toBe(false);
    expect(invalid.errors.some((err) => err.includes("Unknown field 'a'"))).toBe(true);
    const sibling = new YangValidator(base).validate({ top: { b: 1 } });
    expect(sibling.isValid).toBe(true);
  });

  it("keeps the node when the target module is parsed alone after the deviation", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-deviation-cache-"));
    const basePath = writeModule(
      dir,
      "base.yang",
      `
module base {
  yang-version 1.1;
  namespace "urn:b";
  prefix b;
  container top {
    leaf a { type string; }
    leaf b { type uint8; }
  }
}
`
    );
    const devPath = writeModule(
      dir,
      "dev.yang",
      `
module dev {
  yang-version 1.1;
  namespace "urn:dev";
  prefix d;
  import base { prefix b; }
  deviation "/b:top/b:a" { deviate not-supported; }
}
`
    );
    const parser = new YangParser();
    const dev = parser.parseFile(devPath);
    const deviated = dev.import_prefixes.b!;
    const removed = new YangValidator(deviated).validate({ top: { a: "x" } });
    expect(removed.isValid).toBe(false);
    expect(removed.errors.some((err) => err.includes("Unknown field 'a'"))).toBe(true);
    const alone = parser.parseFile(basePath);
    const kept = new YangValidator(alone).validate({ top: { a: "x" } });
    expect(kept.isValid).toBe(true);
    expect(alone).not.toBe(deviated);
  });

  it("deviate replace edits a copy of the imported leaf; the cached module keeps the original (#196)", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-deviation-replace-"));
    const basePath = writeModule(
      dir,
      "base.yang",
      'module base { yang-version 1.1; namespace "urn:b"; prefix b; container top { leaf a { type string; } } }'
    );
    const devPath = writeModule(
      dir,
      "dev.yang",
      'module dev { yang-version 1.1; namespace "urn:dev"; prefix d; import base { prefix b; }' +
        ' deviation "/b:top/b:a" { deviate replace { type uint8; } } }'
    );
    const parser = new YangParser();
    const dev = parser.parseFile(devPath);
    const replaced = new YangValidator(dev.import_prefixes.b!).validate({ top: { a: "x" } });
    expect(replaced.isValid).toBe(false);
    const alone = parser.parseFile(basePath);
    expect(new YangValidator(alone).validate({ top: { a: "x" } }).isValid).toBe(true);
  });
});
