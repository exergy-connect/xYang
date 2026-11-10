// validateDetailed issue JSON matches the Python validator for the same module (#79).
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseYangFile, YangValidator } from "../src";

const CASE = join(dirname(fileURLToPath(import.meta.url)), "../../tests/cases/structure/structured-errors");

// Identical to tests/test_validate_detailed.py.
const EXPECTED = {
  range: [
    {
      code: "range",
      path: "/top/u8",
      message: "Value 300 exceeds maximum 255",
      severity: "error"
    }
  ],
  "unknown-field": [
    {
      code: "unknown-field",
      path: "/top/items/0/x",
      message: "Unknown field 'x'",
      severity: "error"
    }
  ],
  must: [
    {
      code: "must",
      path: "/top/n",
      message: "must constraint not satisfied on 'n'",
      expression: ". >= 0",
      severity: "error"
    }
  ]
} as const;

type Code = keyof typeof EXPECTED;

function errors(data: unknown) {
  const module = parseYangFile(join(CASE, "m.yang"));
  const result = new YangValidator(module).validateDetailed(data);
  expect(result.valid).toBe(false);
  expect(result.warnings).toEqual([]);
  return result.errors;
}

describe("validateDetailed", () => {
  const caseFile = JSON.parse(readFileSync(join(CASE, "case.json"), "utf8")) as {
    instances: { data: unknown; errors: { code: Code }[] }[];
  };
  const byCode = Object.fromEntries(caseFile.instances.map((inst) => [inst.errors[0].code, inst.data])) as Record<
    Code,
    unknown
  >;

  it("returns the same errors JSON as Python for range, unknown-field, and must", () => {
    expect(errors(byCode.range)).toEqual(EXPECTED.range);
    expect(errors(byCode["unknown-field"])).toEqual(EXPECTED["unknown-field"]);
    expect(errors(byCode.must)).toEqual(EXPECTED.must);
  });
});
