"""Tests for ``instance-identifier`` JSON Schema round-trip.

Validation coverage: tests/cases/references/instance-identifier.
"""

from __future__ import annotations

from xyang import parse_yang_string
from xyang.ast import YangLeafStmt
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


def test_instance_identifier_json_schema_round_trip():
    """generate_json_schema → parse_json_schema preserves instance-identifier + require-instance."""
    module = parse_yang_string(_minimal_module_yang())
    schema = generate_json_schema(module)
    module2 = parse_json_schema(schema)
    dm = module2.find_statement("data-model")
    assert dm is not None
    ptr = dm.find_statement("ptr")
    assert isinstance(ptr, YangLeafStmt) and ptr.type is not None
    assert ptr.type.name == "instance-identifier"
    assert ptr.type.require_instance is True
    loose = dm.find_statement("ptr_loose")
    assert isinstance(loose, YangLeafStmt) and loose.type is not None
    assert loose.type.name == "instance-identifier"
    assert loose.type.require_instance is False


def test_instance_identifier_json_schema_validate():
    """JSON schema produced from YANG validates instance data like the YANG module."""
    from xyang import YangValidator

    module = parse_yang_string(_minimal_module_yang())
    schema = generate_json_schema(module)
    m = parse_json_schema(schema)
    v = YangValidator(m)
    ok, errors, _ = v.validate(
        {"data-model": {"top": {"x": "a"}, "ptr": "/data-model/top/x", "ptr_loose": "x"}}
    )
    assert ok, errors
