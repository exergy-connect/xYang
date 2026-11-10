// Shared conformance cases (tests/cases, see README there) run against the TypeScript implementation.
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { YangParser, YangValidator } from "../src";

type Expected = { path: string; code: string; message?: string };
type Instance = {
  name: string;
  data: unknown;
  valid: boolean;
  errors?: Expected[];
  xfail?: Record<string, string>;
  encoding?: string;
};
type Case = {
  module: string;
  features?: Record<string, string[]>;
  schema_error?: boolean;
  code?: string;
  xfail?: Record<string, string>;
  instances?: Instance[];
};

const CASES = join(dirname(fileURLToPath(import.meta.url)), "../../tests/cases");
const readJson = (p: string) => JSON.parse(readFileSync(p, "utf8"));

function loadCaseModule(dir: string, moduleFile: string) {
  const parser = new YangParser({ include_path: [dir], expand_uses: true });
  const primary = resolve(dir, moduleFile);
  const module = parser.parseFile(primary);
  for (const file of readdirSync(dir)) {
    if (!file.endsWith(".yang") || resolve(dir, file) === primary) {
      continue;
    }
    if (readFileSync(join(dir, file), "utf8").trimStart().startsWith("submodule")) {
      continue;
    }
    parser.parseFile(join(dir, file));
  }
  return module;
}

function run(dir: string, c: Case, inst: Instance | undefined): void {
  const module = loadCaseModule(dir, c.module);
  if (!inst) return;
  const features = c.features && Object.fromEntries(Object.entries(c.features).map(([m, f]) => [m, new Set(f)]));
  const { errors } = new YangValidator(module, { enabledFeaturesByModule: features }).validateDetailed(inst.data, {
    nativeJson: inst.encoding === "native"
  });
  const expected = inst.errors ?? [];
  const got = new Set(errors.map((e) => `${e.path} ${e.code}`));
  expect([...got].sort(), `raw errors: ${JSON.stringify(errors)}`).toEqual(
    [...new Set(expected.map((e) => `${e.path} ${e.code}`))].sort()
  );
  for (const exp of expected) {
    if (exp.message) {
      expect(errors.some((e) => e.code === exp.code && e.message.includes(exp.message!))).toBe(true);
    }
  }
  expect(errors.length === 0).toBe(inst.valid);
}

const caseFiles = readdirSync(CASES, { recursive: true, encoding: "utf8" }).filter((f) => f.endsWith("case.json")).sort();
for (const file of caseFiles) {
  const dir = dirname(join(CASES, file));
  const c: Case = readJson(join(CASES, file));
  describe(dirname(file).replaceAll("\\", "/"), () => {
    for (const inst of c.instances ?? [undefined]) {
      const reason = { ...c.xfail, ...inst?.xfail }.ts;
      const test = reason ? it.fails : it;
      test(`${inst?.name ?? "schema error"}${reason ? ` (xfail: ${reason})` : ""}`, () => {
        if (c.schema_error) {
          if (c.code) {
            expect(() => run(dir, c, inst)).toThrow(c.code);
          } else {
            expect(() => run(dir, c, inst)).toThrow();
          }
          return;
        }
        run(dir, c, inst);
      });
    }
  });
}
