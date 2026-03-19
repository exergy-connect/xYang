"""
Standalone xYang regression test for nested choice + uses + refine.

Captures the xFrame-style shape where a grouping provides either legacy `type`
or explicit `field_type` through a nested choice, then a downstream uses/refine
targets `type`.
"""
from __future__ import annotations

from xyang import YangValidator, parse_yang_string


YANG_NESTED_CHOICE_WITH_REFINE = """
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
"""


def test_nested_choice_with_uses_refine_keeps_sibling_fields():
    """Nested choice + uses/refine should preserve sibling leaves like name/description."""
    module = parse_yang_string(YANG_NESTED_CHOICE_WITH_REFINE)
    validator = YangValidator(module)
    data = {
        "data": {
            "fields": [
                {
                    "name": "id",
                    "description": "identifier",
                    "type": "integer",
                    "required": True,
                }
            ]
        }
    }
    is_valid, errors, _ = validator.validate(data)
    assert is_valid, errors
