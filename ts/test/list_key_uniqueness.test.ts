import { describe, expect, it } from "vitest";
import { parseYangString, YangSemanticError } from "../src";

describe("python parity: test_list_key_uniqueness", () => {
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
