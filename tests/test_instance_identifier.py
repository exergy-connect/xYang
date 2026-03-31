"""Tests for ``instance-identifier`` type (YANG parse, validation, JSON round-trip)."""

from __future__ import annotations

from typing import Any

from xyang import YangValidator, parse_yang_string
from xyang.json import generate_json_schema, parse_json_schema


def _minimal_module_yang() -> str:
    return """
module iid-test {
  yang-version 1.1;
  namespace "urn:iid-test";
  prefix "iid";

  container data-model {
    container top {
      leaf x {
        type string;
      }
    }
    leaf ptr {
      type instance-identifier {
        require-instance true;
      }
    }
    leaf ptr_loose {
      type instance-identifier {
        require-instance false;
      }
    }
  }
}
"""


def test_instance_identifier_yang_valid_when_target_exists():
    """Absolute path to an existing leaf passes when require-instance is true."""
    module = parse_yang_string(_minimal_module_yang())
    v = YangValidator(module)
    data: dict[str, Any] = {
        "data-model": {
            "top": {"x": "hello"},
            "ptr": "/data-model/top/x",
            "ptr_loose": "not-a-valid-path-syntax-(",
        }
    }
    ok, errors, _ = v.validate(data)
    assert ok, f"expected valid: {errors}"


def test_instance_identifier_yang_invalid_missing_target():
    """require-instance true: path must resolve to at least one node."""
    module = parse_yang_string(_minimal_module_yang())
    v = YangValidator(module)
    data: dict[str, Any] = {
        "data-model": {
            "top": {"x": "hello"},
            "ptr": "/data-model/top/missing-leaf",
            "ptr_loose": "/any",
        }
    }
    ok, errors, _ = v.validate(data)
    assert not ok
    assert any("instance-identifier" in e.lower() for e in errors)


def test_instance_identifier_yang_invalid_not_absolute():
    """Only absolute paths are supported for require-instance checks."""
    module = parse_yang_string(_minimal_module_yang())
    v = YangValidator(module)
    data: dict[str, Any] = {
        "data-model": {
            "top": {"x": "hello"},
            "ptr": "top/x",
            "ptr_loose": "x",
        }
    }
    ok, errors, _ = v.validate(data)
    assert not ok
    assert any("absolute" in e.lower() for e in errors)


def test_instance_identifier_json_schema_round_trip():
    """generate_json_schema → parse_json_schema preserves instance-identifier + require-instance."""
    module = parse_yang_string(_minimal_module_yang())
    schema = generate_json_schema(module)
    module2 = parse_json_schema(schema)
    dm = module2.find_statement("data-model")
    assert dm is not None
    ptr = dm.find_statement("ptr")
    assert ptr is not None and ptr.type is not None
    assert ptr.type.name == "instance-identifier"
    assert ptr.type.require_instance is True
    loose = dm.find_statement("ptr_loose")
    assert loose is not None and loose.type is not None
    assert loose.type.name == "instance-identifier"
    assert loose.type.require_instance is False


def test_instance_identifier_json_schema_validate():
    """JSON schema produced from YANG validates instance data like the YANG module."""
    module = parse_yang_string(_minimal_module_yang())
    schema = generate_json_schema(module)
    m = parse_json_schema(schema)
    v = YangValidator(m)
    ok, errors, _ = v.validate(
        {"data-model": {"top": {"x": "a"}, "ptr": "/data-model/top/x", "ptr_loose": "x"}}
    )
    assert ok, errors
