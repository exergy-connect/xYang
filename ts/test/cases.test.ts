// Shared conformance cases (tests/cases, see README there) run against the TypeScript implementation.
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { generateJsonSchema, parseJsonSchema, YangParser, YangValidator } from "../src";

type Expected = { path: string; code: string; message?: string; document?: string };
type Instance = {
  name: string;
  data: unknown;
  valid: boolean;
  errors?: Expected[];
  xfail?: Record<string, string>;
  encoding?: string;
  rpc?: string;
  action?: string;
  direction?: "input" | "output";
  context?: Record<string, unknown>;
  usage_error?: string;
};
type Case = {
  module: string;
  features?: Record<string, string[]>;
  schema_error?: boolean;
  code?: string;
  xfail?: Record<string, string>;
  json_form?: boolean;
  export_error?: string;
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

/** The case module's native JSON form, as a Worker without a filesystem would receive it. */
function jsonForm(dir: string, moduleFile: string): Record<string, unknown> {
  const parsed = new YangParser({ include_path: [dir], expand_uses: false }).parseFile(resolve(dir, moduleFile));
  return JSON.parse(JSON.stringify(generateJsonSchema(parsed)));
}

function run(dir: string, c: Case, inst: Instance | undefined, form: "yang" | "json" = "yang"): void {
  const module = form === "json" ? parseJsonSchema(jsonForm(dir, c.module)) : loadCaseModule(dir, c.module);
  if (!inst) return;
  const features = c.features && Object.fromEntries(Object.entries(c.features).map(([m, f]) => [m, new Set(f)]));
  const operation = {
    ...(inst.rpc !== undefined ? { rpc: inst.rpc } : {}),
    ...(inst.action !== undefined ? { action: inst.action } : {}),
    ...(inst.direction !== undefined ? { direction: inst.direction } : {}),
    ...(inst.context !== undefined ? { context: inst.context } : {})
  };
  const validator = new YangValidator(module, { enabledFeaturesByModule: features });
  if (inst.usage_error) {
    expect(() => validator.validateDetailed(inst.data, { nativeJson: inst.encoding === "native", ...operation })).toThrow(
      inst.usage_error
    );
    return;
  }
  const { errors } = validator.validateDetailed(inst.data, { nativeJson: inst.encoding === "native", ...operation });
  const expected = inst.errors ?? [];
  // An issue about the server data context of an rpc or action is keyed `context:<path>`.
  const where = (e: { path: string; document?: string }) => (e.document ? `${e.document}:${e.path}` : e.path);
  const got = new Set(errors.map((e) => `${where(e)} ${e.code}`));
  expect([...got].sort(), `raw errors: ${JSON.stringify(errors)}`).toEqual(
    [...new Set(expected.map((e) => `${where(e)} ${e.code}`))].sort()
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
        if (c.export_error) {
          expect(() => jsonForm(dir, c.module)).toThrow(c.export_error);
          return;
        }
        if (c.json_form) {
          expect(jsonForm(dir, c.module)).toEqual(readJson(join(dir, "expected.yang.json")));
        }
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
      if (c.json_form && inst) {
        test(`${inst.name} (from the native JSON form)${reason ? ` (xfail: ${reason})` : ""}`, () => run(dir, c, inst, "json"));
      }
    }
  });
}
