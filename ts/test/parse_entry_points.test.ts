import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { parseYangFile, parseYangString } from "../src";

const IMPORTER = `module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  import base { prefix b; }
  container top {
    leaf name { type b:id; }
  }
}
`;

function writeBase(dir: string): void {
  writeFileSync(
    join(dir, "base.yang"),
    `module base {
  yang-version 1.1;
  namespace "urn:base";
  prefix b;
  typedef id { type string; }
}
`
  );
}

function importedName(module: { data: Record<string, unknown> }): string | undefined {
  const imports = module.data.import_prefixes as Record<string, { name?: string }> | undefined;
  return imports?.b?.name;
}

describe("parse entry points (#77)", () => {
  it("resolves a string import from includePath and from sourcePath", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-parse-string-"));
    writeBase(dir);

    const fromInclude = parseYangString(IMPORTER, { includePath: [dir] });
    expect(fromInclude.name).toBe("m");
    expect(importedName(fromInclude)).toBe("base");

    const fromSource = parseYangString(IMPORTER, { sourcePath: join(dir, "m.yang") });
    expect(fromSource.name).toBe("m");
    expect(importedName(fromSource)).toBe("base");
  });

  it("re-reads a file edited between parseYangFile calls", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-parse-file-"));
    const file = join(dir, "m.yang");
    const source = (leaf: string) => `module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  container top {
    leaf ${leaf} { type string; }
  }
}
`;
    writeFileSync(file, source("before"));
    const first = parseYangFile(file);
    expect(first.findStatement("top")?.findStatement("before")?.name).toBe("before");

    writeFileSync(file, source("after"));
    const second = parseYangFile(file);
    expect(second.findStatement("top")?.findStatement("before")).toBeUndefined();
    expect(second.findStatement("top")?.findStatement("after")?.name).toBe("after");
    expect(second).not.toBe(first);
  });
});
