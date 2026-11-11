import { describe, expect, it } from "vitest";
import { parseYangString } from "../src";

describe("python parity: test_choice_case_when", () => {
  // Validation coverage: tests/cases/choice/choice-case-when
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
    const whenShape = choice?.when as Record<string, unknown> | undefined;

    expect(root).toBeDefined();
    expect(choice).toBeDefined();
    expect(choice?.keyword).toBe("choice");
    expect(typeof whenShape?.expression).toBe("string");
    expect(String(whenShape?.expression ?? "")).toContain("mode = 'on'");
  });
});
