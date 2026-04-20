import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

const YANG = `
module minimal-computed {
  namespace "urn:minimal";
  prefix "m";

  container root {
    list entities {
      key name;
      leaf name { type string; }
      list fields {
        key name;
        leaf name { type string; }
        container computed {
          leaf operation { type string; }
          list fields {
            key field;
            leaf field {
              type string;
              must "count(../../../../fields[name = current()]) = 1" {
                error-message "field must exist in entity";
              }
            }
            leaf note {
              type string;
              must "count(../../../../fields[name = current()]) = 1" {
                error-message "note: referenced field must exist in entity";
              }
            }
          }
        }
      }
    }
  }
}
`;

describe("python parity: test_duplicate_must_bug", () => {
  it("accepts valid data when must count(../../../../fields[name = current()]) resolves in correct context", () => {
    const module = parseYangString(YANG);
    const validator = new YangValidator(module);
    const result = validator.validate({
      root: {
        entities: [
          {
            name: "e",
            fields: [
              { name: "a" },
              {
                name: "ref",
                computed: {
                  operation: "add",
                  fields: [{ field: "a", note: "a" }]
                }
              }
            ]
          }
        ]
      }
    });
    expect(result.isValid, result.errors.join("\n")).toBe(true);
  });
});
