"""
Minimal self-contained test: one must with relative path ../../../../fields[name = current()].

Structure: root -> entities (list) -> fields (list) -> computed -> fields (list) -> leaf field.
When the relative path is resolved in the wrong context, validation wrongly fails.
"""
from __future__ import annotations

import pytest

from xyang import YangValidator, parse_yang_string

YANG = """
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
"""


def _validate(module, data: dict) -> tuple[bool, list]:
    validator = YangValidator(module)
    is_valid, errors, _ = validator.validate(data)
    return is_valid, errors


@pytest.fixture
def module():
    return parse_yang_string(YANG)


def test_computed_field_ref_valid_minimal(module):
    """
    Field "ref" references "a"; "a" exists in entity. Should pass.
    Fails when relative path ../../../../fields[name = current()] resolves in wrong context.
    """
    data = {
        "root": {
            "entities": [
                {
                    "name": "e",
                    "fields": [
                        {"name": "a"},
                        {
                            "name": "ref",
                            "computed": {
                                "operation": "add",
                                "fields": [{"field": "a", "note": "a"}],
                            },
                        },
                    ],
                },
            ],
        }
    }
    valid, errors = _validate(module, data)
    assert valid, errors
