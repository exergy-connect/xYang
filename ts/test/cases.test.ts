// Shared conformance cases (tests/cases, see README there) run against the TypeScript implementation.
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseYangFile, YangValidator } from "../src";

type Expected = { path: string; code: string; message?: string };
type Instance = { name: string; data: unknown; valid: boolean; errors?: Expected[]; xfail?: Record<string, string> };
type Case = {
  module: string;
  features?: Record<string, string[]>;
  schema_error?: boolean;
  xfail?: Record<string, string>;
  instances?: Instance[];
};

const CASES = join(dirname(fileURLToPath(import.meta.url)), "../../tests/cases");
const readJson = (p: string) => JSON.parse(readFileSync(p, "utf8"));
const CODES: [string, RegExp][] = readJson(join(CASES, "error-codes.json")).codes.map(
  ([code, rx]: [string, string]) => [code, new RegExp(rx)]
);

/** '<path>: <message>' -> [path, message]; TS paths look like top.items[0].v and never contain spaces. */
function split(err: string): [string, string] {
  const m = /^([^\s:]+): (.*)$/s.exec(err);
  return m ? [m[1], m[2]] : ["", err];
}

/** TS path (top.items[0].tags[1]) -> JSON Pointer (/top/items/0/tags/1). */
const pointer = (path: string) => path.split(".").filter(Boolean).map((s) => "/" + s.replace(/\[(\d+)\]/g, "/$1")).join("");

function code(message: string, expected: Expected[]): string {
  const hint = expected.find((e) => e.message && message.includes(e.message));
  return hint?.code ?? CODES.find(([, rx]) => rx.test(message))?.[0] ?? "unclassified";
}

function run(dir: string, c: Case, inst: Instance | undefined): void {
  const module = parseYangFile(join(dir, c.module), { includePath: [dir] });
  if (!inst) return;
  const features = c.features && Object.fromEntries(Object.entries(c.features).map(([m, f]) => [m, new Set(f)]));
  const { errors } = new YangValidator(module, { enabledFeaturesByModule: features }).validate(inst.data);
  const expected = inst.errors ?? [];
  const got = new Set(errors.map(split).map(([p, m]) => `${pointer(p)} ${code(m, expected)}`));
  expect([...got].sort(), `raw errors: ${JSON.stringify(errors)}`).toEqual(
    [...new Set(expected.map((e) => `${e.path} ${e.code}`))].sort()
  );
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
      test(`${inst?.name ?? "schema error"}${reason ? ` (xfail: ${reason})` : ""}`, () =>
        c.schema_error ? expect(() => run(dir, c, inst)).toThrow() : run(dir, c, inst)
      );
    }
  });
}
