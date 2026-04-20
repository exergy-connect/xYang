import { describe, expect, it } from "vitest";
import { parseYangString, YangValidator } from "../src";

const YANG_NESTED_CHOICE_WITH_REFINE = `
module nested_choice_with_refine {
  yang-version 1.1;
  namespace "urn:test:nested-choice-with-refine";
  prefix "nc";

  typedef primitive-type {
    type enumeration {
      enum string;
      enum integer;
      enum number;
      enum boolean;
      enum array;
    }
  }

  typedef type-or-definition-ref {
    type union {
      type primitive-type;
      type string;
    }
  }

  grouping field-type-source {
    choice field-type-source-choice {
      case legacy-type-case {
        leaf type {
          type primitive-type;
        }
      }
      case explicit-field-type-case {
        container field_type {
          choice field-type-choice {
            mandatory true;
            case primitive-case {
              leaf primitive {
                type primitive-type;
              }
            }
            case definition-case {
              leaf definition_ref {
                type string;
              }
            }
          }
        }
      }
    }
  }

  grouping field-type-and-constraints {
    uses field-type-source;
    leaf name {
      type string;
      mandatory true;
    }
    leaf description {
      type string;
      mandatory true;
    }
  }

  grouping field-definition {
    uses field-type-and-constraints;
    leaf required {
      type boolean;
      default false;
    }
  }

  container data {
    list fields {
      key name;
      uses field-definition {
        refine type {
          type type-or-definition-ref;
        }
      }
    }
  }
}
`;

describe("python parity: test_nested_choice_with_refine", () => {
  it("nested choice + uses/refine preserves sibling leaves like name/description", () => {
    const module = parseYangString(YANG_NESTED_CHOICE_WITH_REFINE);
    const validator = new YangValidator(module);
    const result = validator.validate({
      data: {
        fields: [
          {
            name: "id",
            description: "identifier",
            type: "integer",
            required: true
          }
        ]
      }
    });
    expect(result.isValid, result.errors.join("\n")).toBe(true);
  });
});
