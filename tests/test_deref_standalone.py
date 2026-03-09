"""
Standalone tests for deref() using the xyang package.

Tests deref() explicitly in:
- Path expressions: e.g. count(deref(...)) = 1, deref(...)/../child
- Predicates: e.g. /path[node = string(deref(...))]
"""

import pytest
from xyang import parse_yang_string, YangValidator


# YANG with must constraints that explicitly use deref() in paths and predicates
DEREF_YANG = """
module deref-test {
  yang-version 1.1;
  namespace "urn:test:deref";
  prefix "dt";

  container data-model {
    list entities {
      key name;
      leaf name { type string; mandatory true; }
      leaf primary_key { type string; mandatory true; }
      list fields {
        key name;
        leaf name { type string; mandatory true; }
        leaf type { type string; }
        list foreignKeys {
          key entity;
          leaf entity {
            type leafref {
              path "/data-model/entities/name";
              require-instance true;
            }
            mandatory true;
          }
          must "count(deref(current()/entity)) = 1" {
            error-message "deref() in path expression must resolve to exactly one node";
          }
          must "/data-model/entities[name = string(deref(current()/entity))]" {
            error-message "deref() in predicate: referenced entity must exist";
          }
        }
      }
    }
  }
}
"""


def _validator():
    return YangValidator(parse_yang_string(DEREF_YANG))


def test_deref_in_path_expression_valid():
    """deref() in path expression: count(deref(current()/entity)) = 1 passes when entity exists."""
    validator = _validator()
    data = {
        "data-model": {
            "entities": [
                {"name": "company", "primary_key": "id", "fields": [{"name": "id", "type": "string"}]},
                {
                    "name": "department",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "string"},
                        {"name": "company_id", "type": "string", "foreignKeys": [{"entity": "company"}]},
                    ],
                },
            ]
        }
    }
    is_valid, errors, _ = validator.validate(data)
    assert is_valid, f"deref() in path expression should pass when entity exists. Errors: {errors}"


def test_deref_in_path_expression_invalid():
    """deref() in path expression: count(deref(current()/entity)) = 1 fails when entity missing."""
    validator = _validator()
    data = {
        "data-model": {
            "entities": [
                {
                    "name": "only",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "string"},
                        {"name": "ref", "type": "string", "foreignKeys": [{"entity": "missing"}]},
                    ],
                },
            ]
        }
    }
    is_valid, errors, _ = validator.validate(data)
    assert not is_valid, "deref() in path expression should fail when entity does not exist"
    assert any("deref" in e.lower() or "path" in e.lower() or "leafref" in e.lower() for e in errors), (
        f"Expected deref/path/leafref related error. Got: {errors}"
    )


def test_deref_in_predicate_valid():
    """deref() in predicate: /entities[name = string(deref(current()/entity))] passes when entity exists."""
    validator = _validator()
    data = {
        "data-model": {
            "entities": [
                {"name": "parent", "primary_key": "pk", "fields": [{"name": "pk", "type": "string"}]},
                {
                    "name": "child",
                    "primary_key": "pk",
                    "fields": [
                        {"name": "pk", "type": "string"},
                        {"name": "parent_id", "type": "string", "foreignKeys": [{"entity": "parent"}]},
                    ],
                },
            ]
        }
    }
    is_valid, errors, _ = validator.validate(data)
    assert is_valid, f"deref() in predicate should pass when entity exists. Errors: {errors}"


def test_deref_in_predicate_invalid():
    """deref() in predicate: /entities[name = string(deref(current()/entity))] fails when entity missing."""
    validator = _validator()
    data = {
        "data-model": {
            "entities": [
                {
                    "name": "one",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "string"},
                        {"name": "fk", "type": "string", "foreignKeys": [{"entity": "ghost"}]},
                    ],
                },
            ]
        }
    }
    is_valid, errors, _ = validator.validate(data)
    assert not is_valid, "deref() in predicate should fail when referenced entity does not exist"
    assert any("deref" in e.lower() or "predicate" in e.lower() or "entity" in e.lower() or "leafref" in e.lower() for e in errors), (
        f"Expected deref/predicate/entity/leafref related error. Got: {errors}"
    )
