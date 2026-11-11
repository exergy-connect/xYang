import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

// Validity outcomes: tests/cases/xpath/type-coercion.

const BOOL_INT = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf enabled {
      type boolean;
      must "current() = true()";
    }
    leaf count {
      type int32;
      must "current() > 0";
    }
  }
}
`;

describe("python parity: test_coercion", () => {
  it("validate does not mutate boolean or int input", () => {
    const validator = new YangValidator(parseYangString(BOOL_INT));

    const boolData = { data: { enabled: "true" } };
    const boolResult = validator.validate(boolData);
    expect(boolResult.isValid, boolResult.errors.join("; ")).toBe(true);
    expect(boolData.data.enabled).toBe("true");
    expect(typeof boolData.data.enabled).toBe("string");

    const intData = { data: { count: "123" } };
    const intResult = validator.validate(intData);
    expect(intResult.isValid).toBe(false);
    expect(intData.data.count).toBe("123");
    expect(typeof intData.data.count).toBe("string");
  });
});
