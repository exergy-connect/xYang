// Import revision-date must not fall back silently (#66).
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { parseYangFile } from "../src";

function writeModule(dir: string, filename: string, name: string, prefix: string, body = ""): string {
  const path = join(dir, filename);
  writeFileSync(
    path,
    `module ${name} {
  yang-version 1.1;
  namespace "urn:${name}";
  prefix ${prefix};
${body}
}
`
  );
  return path;
}

describe("import revision-date (#66)", () => {
  let warnSpy: ReturnType<typeof vi.spyOn>;

  afterEach(() => {
    warnSpy?.mockRestore();
  });

  it("warns when the requested revision is missing and a dated file is used", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-import-rev-"));
    writeModule(dir, "base@2019-01-01.yang", "base", "b", '  description "2019";');
    const root = writeModule(dir, "m.yang", "m", "m", "  import base { prefix b; revision-date 2020-01-01; }");
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const module = parseYangFile(root);
    const imported = (module.data as { import_prefixes: Record<string, { description?: string }> }).import_prefixes.b;
    expect(imported?.description).toBe("2019");
    const messages = warnSpy.mock.calls.map((call: unknown[]) => String(call[0]));
    expect(messages).toContain(
      "import 'base' revision-date 2020-01-01 not found; using base@2019-01-01.yang"
    );
  });

  it("prefers the exact revision file over a newer one", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-import-exact-"));
    writeModule(dir, "base@2020-01-01.yang", "base", "b", '  description "2020";');
    writeModule(dir, "base@2021-01-01.yang", "base", "b", '  description "2021";');
    const root = writeModule(dir, "m.yang", "m", "m", "  import base { prefix b; revision-date 2020-01-01; }");
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const module = parseYangFile(root);
    const imported = (module.data as { import_prefixes: Record<string, { description?: string }> }).import_prefixes.b;
    expect(imported?.description).toBe("2020");
    const messages = warnSpy.mock.calls.map((call: unknown[]) => String(call[0]));
    expect(messages.some((message: string) => message.includes("revision-date"))).toBe(false);
  });

  it("says module when the import cannot be found", () => {
    const dir = mkdtempSync(join(tmpdir(), "xyang-import-missing-"));
    const root = writeModule(dir, "m.yang", "m", "m", "  import base { prefix b; }");
    expect(() => parseYangFile(root)).toThrow(/Could not find module 'base'/);
    try {
      parseYangFile(root);
    } catch (err) {
      expect(String(err)).not.toContain("submodule");
    }
  });
});
