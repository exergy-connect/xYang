import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

const MODULE_YANG = `
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container root {
    list items {
      key name;
      leaf name {
        type string;
      }
      leaf value {
        type string;
      }
    }
  }
}
`;

describe("python parity: test_list_key_uniqueness", () => {
  function moduleWithKeyedList() {
    return parseYangString(MODULE_YANG);
  }

  it("accepts list entries with unique key values", () => {
    const validator = new YangValidator(moduleWithKeyedList());
    const result = validator.validate({
      root: {
        items: [
          { name: "a", value: "one" },
          { name: "b", value: "two" }
        ]
      }
    });
    expect(result.isValid, result.errors.join("; ")).toBe(true);
  });

  it("rejects duplicate key values in the same list", () => {
    const validator = new YangValidator(moduleWithKeyedList());
    const result = validator.validate({
      root: {
        items: [
          { name: "a", value: "one" },
          { name: "a", value: "two" }
        ]
      }
    });
    expect(result.isValid).toBe(false);
    expect(result.errors.some((err) => err.toLowerCase().includes("duplicate key"))).toBe(true);
  });

  it("duplicate key error mentions list name and key field", () => {
    const validator = new YangValidator(moduleWithKeyedList());
    const result = validator.validate({
      root: {
        items: [
          { name: "x", value: "1" },
          { name: "x", value: "2" }
        ]
      }
    });
    expect(result.isValid).toBe(false);
    const errStr = result.errors.join(" ").toLowerCase();
    expect(errStr).toContain("items");
    expect(errStr).toContain("name");
  });
});
