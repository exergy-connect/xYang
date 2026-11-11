import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseYangFile, YangValidator } from "../src";

const example = resolve(__dirname, "..", "..", "examples", "ontology-hypergraph");
const models = resolve(example, "models");
const fixtures = resolve(example, "fixtures");

const expected: Record<string, { code: string; message: string }> = {
  "dangling-evidence": { code: "leafref", message: "" },
  "assessment-without-evidence": { code: "must", message: "cite at least one evidence" },
  "reviewer-is-assessor": { code: "must", message: "must not be the assessor" },
  "review-with-two-reviewers": { code: "must", message: "exactly one reviewer" },
  "finding-on-supported-assessment": { code: "must", message: "outcome is exception" },
  "evidence-type-not-accepted": { code: "must", message: "control accepts" }
};

function validator(): YangValidator {
  return new YangValidator(parseYangFile(resolve(models, "example-audit@2026-11-10.yang"), { includePath: [models] }));
}

function load(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8"));
}

describe("ontology hypergraph audit example", () => {
  it("accepts the collected engagement projection", () => {
    const result = validator().validateDetailed(load(resolve(fixtures, "valid.json")));
    expect(result.errors).toEqual([]);
    expect(result.valid).toBe(true);
  });

  it("has exactly the documented invalid fixtures", () => {
    const names = readdirSync(resolve(fixtures, "invalid")).map((f) => f.replace(/\.json$/, "")).sort();
    expect(names).toEqual(Object.keys(expected).sort());
  });

  for (const [name, { code, message }] of Object.entries(expected)) {
    it(`rejects ${name}`, () => {
      const result = validator().validateDetailed(load(resolve(fixtures, "invalid", `${name}.json`)));
      expect(result.valid).toBe(false);
      expect(result.errors.some((e) => e.code === code && e.message.toLowerCase().includes(message))).toBe(true);
    });
  }
});
