import { copyFileSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseYangFile, YangParser, YangValidator } from "../src";

const repoRoot = resolve(__dirname, "..", "..");
const ex3Dir = resolve(repoRoot, "tests/data/yangson-ex3");
const yangLibrarySchema = resolve(ex3Dir, "yang-library-ex3.yang");

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf-8")) as unknown;
}

function buildYangLibraryData(): Record<string, unknown> {
  const legacy = readJson(resolve(ex3Dir, "yang-library-ex3.json")) as Record<string, unknown>;
  const rfc8525 = readJson(resolve(ex3Dir, "rfc8525-ex3.json")) as Record<string, unknown>;
  return {
    "modules-state": legacy["ietf-yang-library:modules-state"],
    "yang-library": rfc8525["ietf-yang-library:yang-library"]
  };
}

describe("python parity: test_yangson_ex3_import", () => {
  it("parses example-3-a fixture with uses expansion disabled", () => {
    const mod = new YangParser({ expand_uses: false }).parseFile(resolve(ex3Dir, "example-3-a@2017-08-01.yang"));
    const groupings = mod.data.groupings as Record<string, unknown> | undefined;
    expect(mod.name).toBe("example-3-a");
    expect(mod.namespace).toBe("http://example.com/example-3/a");
    expect(groupings?.gbar).toBeDefined();
  });

  it("parses example-3-b fixture with imports when canonical filenames are available", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-ex3-import-"));
    try {
      copyFileSync(resolve(ex3Dir, "example-3-a@2017-08-01.yang"), join(dir, "example-3-a.yang"));
      copyFileSync(resolve(ex3Dir, "example-3-b@2016-08-22.yang"), join(dir, "example-3-b.yang"));
      copyFileSync(resolve(ex3Dir, "ietf-inet-types@2010-09-24.yang"), join(dir, "ietf-inet-types.yang"));

      const mod = new YangParser({ expand_uses: false }).parseFile(join(dir, "example-3-b.yang"));
      const imports = mod.data.import_prefixes as Record<string, { name?: string }> | undefined;
      const augment = mod.statements.find((stmt) => stmt.keyword === "augment");
      const augmentPath = (augment?.data.augment_path as string | undefined) ?? augment?.argument;

      expect(mod.name).toBe("example-3-b");
      expect(imports).toBeDefined();
      expect(Object.keys(imports ?? {}).sort()).toEqual(["ex3a", "oin"]);
      expect(imports?.ex3a?.name).toBe("example-3-a");
      expect(imports?.oin?.name).toBe("ietf-inet-types");
      expect(augmentPath).toBe("/ex3a:top");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("rejects parsing a standalone submodule via parseFile", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-ex3-submodule-"));
    try {
      copyFileSync(resolve(ex3Dir, "example-3-suba@2017-08-01.yang"), join(dir, "example-3-suba.yang"));
      copyFileSync(resolve(ex3Dir, "ietf-inet-types@2013-07-15.yang"), join(dir, "ietf-inet-types.yang"));
      expect(() => new YangParser({ expand_uses: false }).parseFile(join(dir, "example-3-suba.yang"))).toThrow(
        /top-level 'module'/i
      );
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("validates legacy modules-state JSON against yang-library-ex3.yang", () => {
    const module = parseYangFile(yangLibrarySchema);
    const data = buildYangLibraryData();

    const result = new YangValidator(module).validate(data);
    expect(result.isValid, result.errors.join("\n")).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("validates RFC 8525 yang-library JSON against yang-library-ex3.yang", () => {
    const module = parseYangFile(yangLibrarySchema);
    const data = buildYangLibraryData();

    const result = new YangValidator(module).validate(data);
    expect(result.isValid, result.errors.join("\n")).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("parseString import without source path is rejected", () => {
    expect(() =>
      new YangParser().parseString(`
module ex {
  yang-version 1.1;
  namespace "urn:ex";
  prefix ex;
  import missing {
    prefix m;
  }
}
`)
    ).toThrow(/filesystem location|parseYangFile|parseYangString/i);
  });
});
