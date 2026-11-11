import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { parseYangFile, YangValidator } from "../src";

const example = resolve(__dirname, "..", "..", "examples", "ontology-hypergraph");
const models = resolve(example, "models");
const fixtures = resolve(example, "fixtures");
const root = "/example-audit:graph";

type Expected = { path: string; code: string; message?: string };
const expected = JSON.parse(readFileSync(resolve(fixtures, "expected-errors.json"), "utf8")) as Record<string, Expected[]>;

function load(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8"));
}

function key(e: Expected): string {
  // Built-in messages (leafref, pattern) are worded per language; must messages come from the model.
  return JSON.stringify([e.path, e.code, e.code === "must" ? e.message : null]);
}

describe("ontology hypergraph audit example", () => {
  let validator: YangValidator;

  beforeAll(() => {
    validator = new YangValidator(
      parseYangFile(resolve(models, "example-audit@2026-11-10.yang"), { includePath: [models] })
    );
  });

  it("accepts the collected engagement projection", () => {
    const result = validator.validateDetailed(load(resolve(fixtures, "valid.json")));
    expect(result.errors).toEqual([]);
    expect(result.valid).toBe(true);
  });

  it("has exactly the documented invalid fixtures", () => {
    const names = readdirSync(resolve(fixtures, "invalid")).map((f) => f.replace(/\.json$/, "")).sort();
    expect(names).toEqual(Object.keys(expected).sort());
  });

  for (const [name, errors] of Object.entries(expected)) {
    it(`rejects ${name} with exactly the documented errors`, () => {
      const result = validator.validateDetailed(load(resolve(fixtures, "invalid", `${name}.json`)));
      const got = result.errors.map((e) => key({ path: e.path.replace(root, ""), code: e.code, message: e.message })).sort();
      expect(got).toEqual(errors.map(key).sort());
    });
  }
});
