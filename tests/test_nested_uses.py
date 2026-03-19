"""
Standalone xYang test for YANG modules that contain nested uses statements.

Defines a minimal YANG module with nested grouping/uses (grouping A uses B,
B uses C) and checks that xYang parses it and can validate data against it.
"""
from __future__ import annotations

from xyang import parse_yang_string, YangValidator


# Standalone YANG module with nested uses: outer uses middle, middle uses inner.
YANG_NESTED_USES = """
module nested_uses {
  yang-version 1.1;
  namespace "urn:test:nested-uses";
  prefix "nu";

  grouping inner {
    leaf x {
      type string;
      description "From inner grouping";
    }
  }

  grouping middle {
    uses inner;
    leaf y {
      type string;
      description "From middle grouping";
    }
  }

  grouping outer {
    uses middle;
    leaf z {
      type string;
      description "From outer grouping";
    }
  }

  container root {
    description "Root container that uses the nested grouping chain";
    uses outer;
  }
}
"""


def test_parse_nested_uses_module():
    """xYang parses a YANG module that contains nested uses statements."""
    module = parse_yang_string(YANG_NESTED_USES)
    assert module.name == "nested_uses"
    assert module.yang_version == "1.1"
    root = module.find_statement("root")
    assert root is not None


def test_validate_data_against_nested_uses():
    """xYang validates data against a schema built from nested uses."""
    module = parse_yang_string(YANG_NESTED_USES)
    validator = YangValidator(module)
    data = {"root": {"x": "a", "y": "b", "z": "c"}}
    is_valid, errors, _ = validator.validate(data)
    assert is_valid, errors
