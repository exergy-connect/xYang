import { describe, expect, it } from "vitest";
import { parseYangString, YangSemanticError, YangValidator } from "../src";

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

  it.each(["when \"../enabled = 'true'\";", "if-feature \"f\";"])(
    "rejects %s on a list key leaf (RFC 7950)",
    (illegalStmt) => {
      const bad = `
module test-list-key-condition {
  yang-version 1.1;
  namespace "urn:test-list-key-condition";
  prefix "t";

  feature f;

  container root {
    leaf enabled {
      type boolean;
    }
    list items {
      key name;
      leaf name {
        ${illegalStmt}
        type string;
      }
      leaf value {
        type string;
      }
    }
  }
}
`;

      expect(() => parseYangString(bad)).toThrow(YangSemanticError);
      expect(() => parseYangString(bad)).toThrow(/key leaf|list key|list keys/i);
    }
  );

  it("rejects a list key that names no child leaf (RFC 7950)", () => {
    const bad = `
module test-list-missing-key {
  yang-version 1.1;
  namespace "urn:test-list-missing-key";
  prefix "t";

  container root {
    list items {
      key missing;
      leaf name {
        type string;
      }
    }
  }
}
`;

    expect(() => parseYangString(bad)).toThrow(YangSemanticError);
    expect(() => parseYangString(bad)).toThrow(/key leaf|missing|not found|does not exist/i);
  });
});
