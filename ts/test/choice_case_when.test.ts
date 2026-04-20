import { describe, expect, it } from "vitest";
import { YangValidator, parseYangString } from "../src";

describe("python parity: test_choice_case_when", () => {
  const MODULE = `
module test-choice-when {
  yang-version 1.1;
  namespace "urn:test:cw";
  prefix "cw";

  container root {
    leaf mode {
      type string;
    }
    choice c {
      when "./mode = 'on'";
      case a {
        when "./mode = 'off'";
        leaf a { type string; }
      }
      case b {
        leaf b { type string; }
      }
    }
  }
}
`;

  it("parses choice when condition", () => {
    const module = parseYangString(MODULE);
    const root = module.findStatement("root");
    const choice = root?.findStatement("c");
    const whenShape = choice?.data.when as Record<string, unknown> | undefined;

    expect(root).toBeDefined();
    expect(choice).toBeDefined();
    expect(choice?.keyword).toBe("choice");
    expect(typeof whenShape?.expression).toBe("string");
    expect(String(whenShape?.expression ?? "")).toContain("mode = 'on'");
  });

  it("accepts data when choice when is false and no branch data is provided", () => {
    const module = parseYangString(MODULE);
    const validator = new YangValidator(module);

    const result = validator.validate({ root: { mode: "off" } });

    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("accepts data when choice when is true", () => {
    const module = parseYangString(MODULE);
    const validator = new YangValidator(module);

    const result = validator.validate({ root: { mode: "on", b: "y" } });

    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("rejects branch data when choice when is false", () => {
    const module = parseYangString(MODULE);
    const validator = new YangValidator(module);

    const result = validator.validate({ root: { mode: "off", a: "x" } });

    expect(result.isValid).toBe(false);
    expect(result.errors.some((error) => error.toLowerCase().includes("when"))).toBe(true);
  });

  it("rejects case data when case when is false", () => {
    const module = parseYangString(MODULE);
    const validator = new YangValidator(module);

    const result = validator.validate({ root: { mode: "on", a: "x" } });

    expect(result.isValid).toBe(false);
    expect(result.errors.some((error) => error.toLowerCase().includes("when"))).toBe(true);
  });
});
