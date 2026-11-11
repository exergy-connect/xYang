import { describe, expect, it } from "vitest";
import { YangParser } from "../src";

const YANG_GENERIC_FIELD_NO_ARRAY_CASE = `
module generic_field_no_array {
  yang-version 1.1;
  namespace "urn:test:generic-field-no-array";
  prefix "gfna";

  typedef primitive-type-name {
    type enumeration {
      enum string;
      enum integer;
    }
    description "Primitive type tag.";
  }

  grouping generic-field {
    description "Like examples/generic-field.yang but without the case-array branch.";
    leaf name {
      type string {
        length "1..128";
      }
      mandatory true;
      description "Field name.";
    }
    container type {
      description "Field type: primitive or composite only.";
      choice choice-type {
        mandatory true;
        description "Primitive or composite object.";
        case primitive {
          leaf primitive {
            type primitive-type-name;
            mandatory true;
            description "Primitive type.";
          }
        }
        case case-composite {
          description "Composite field: named subfields, each a full generic-field.";
          list fields {
            key name;
            min-elements 1;
            description "Subfields (recursive generic field).";
            uses generic-field {
              refine type/choice-type/case-composite/fields {
                max-elements 0;
                description "Exclude nested composite subfields; breaks recursive uses expansion.";
              }
            }
          }
        }
      }
    }
  }

  container field {
    description "Example instance root for one generic field.";
    uses generic-field;
  }
}
`;

describe("python parity: test_refine_list", () => {
  it("same module parses with expandUses disabled", () => {
    const parser = new YangParser({ expandUses: false });
    const module = parser.parseString(YANG_GENERIC_FIELD_NO_ARRAY_CASE);
    expect(module.name).toBe("generic_field_no_array");
  });
});
