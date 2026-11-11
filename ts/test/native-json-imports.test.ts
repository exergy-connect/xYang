// #158: the native JSON form carries the imported identities it needs, and fails loudly otherwise.
import { mkdtempSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { build } from "esbuild";
import { beforeAll, describe, expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema } from "../src";

const tsRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const CASES = resolve(tsRoot, "../tests/cases/modules");
const FORMS = ["json-form-imported-identity-augment", "json-form-identity-alias"];
const cli = join(mkdtempSync(join(tmpdir(), "xyang-imports-")), "cli.mjs");

beforeAll(async () => {
  await build({
    absWorkingDir: tsRoot,
    entryPoints: [resolve(tsRoot, "src/cli.ts")],
    bundle: true,
    platform: "node",
    format: "esm",
    target: "node22",
    outfile: cli,
    logLevel: "silent"
  });
});

function refs(node: unknown): string[] {
  if (Array.isArray(node)) {
    return node.flatMap(refs);
  }
  if (node && typeof node === "object") {
    return Object.entries(node).flatMap(([key, value]) => (key === "$ref" ? [String(value)] : refs(value)));
  }
  return [];
}

function pointer(doc: unknown, ref: string): any {
  return ref
    .replace(/^#\//, "")
    .split("/")
    .reduce((node: any, part) => node[part], doc);
}

describe("native JSON form of imported identities", () => {
  for (const name of FORMS) {
    it(`${name} is self-contained and reversible`, () => {
      const form = JSON.parse(readFileSync(join(CASES, name, "expected.yang.json"), "utf8"));
      const found = refs(form.properties);
      expect(found.length).toBeGreaterThan(0);
      for (const ref of found) {
        expect(pointer(form, ref)["x-yang"].type, `dangling ${ref}`).toBe("identity");
      }
      expect(JSON.parse(JSON.stringify(generateJsonSchema(parseJsonSchema(form))))).toEqual(form);
    });
  }

  it("fails convert with exit 2 and writes nothing for an augment of another module's tree", () => {
    const dir = join(CASES, "json-form-foreign-augment");
    const proc = spawnSync(process.execPath, [cli, "convert", "--include-path", dir, join(dir, "m.yang")], {
      encoding: "utf-8",
      input: "",
      timeout: 15_000
    });
    expect(proc.status).toBe(2);
    expect(proc.stdout).toBe("");
    expect(proc.stderr).toContain("augment '/b:top'");
    expect(readdirSync(dir).sort()).toEqual(["base.yang", "case.json", "m.yang"]);
  });
});
