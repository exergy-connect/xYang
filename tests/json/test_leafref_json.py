"""
JSON-level tests for leafref handling in the JSON parser and validator.

Covers three cases:
- valid path expression, valid data (target exists) -> validation succeeds
- valid path expression, missing target node -> validation fails (require-instance)
- invalid path expression -> parse_json_schema raises XPathSyntaxError
"""

from __future__ import annotations

from typing import Any

import pytest

from xyang import YangValidator, parse_yang_string
from xyang.errors import XPathSyntaxError
from xyang.json import generate_json_schema, parse_json_schema


def _make_schema(path: str) -> dict[str, Any]:
    """Minimal JSON Schema with x-yang leafref path under data-model/ref."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:test:leafref-json",
        "description": "Minimal schema for leafref path tests",
        "x-yang": {
            "module": "leafref-json-test",
            "yang-version": "1.1",
            "namespace": "urn:test:leafref-json",
            "prefix": "lr",
            "organization": "",
            "contact": "",
        },
        "type": "object",
        "properties": {
            "data-model": {
                "type": "object",
                "description": "Root container",
                "x-yang": {"type": "container"},
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Target value referenced by ref",
                        "x-yang": {"type": "leaf"},
                    },
                    "ref": {
                        "type": "string",
                        "description": "Leafref to /data-model/target",
                        "x-yang": {
                            "type": "leafref",
                            "path": path,
                            "require-instance": True,
                        },
                    },
                },
                "additionalProperties": False,
            }
        },
        "additionalProperties": False,
    }


def _validate(schema: dict[str, Any], data: dict[str, Any]) -> tuple[bool, list[str]]:
    module = parse_json_schema(schema)
    validator = YangValidator(module)
    is_valid, errors, _ = validator.validate(data)
    return is_valid, list(errors)


def test_leafref_json_valid_path_and_existing_target():
    """Valid path expression and target present -> validation succeeds."""
    schema = _make_schema("/data-model/target")
    data = {"data-model": {"target": "x", "ref": "x"}}

    valid, errors = _validate(schema, data)
    assert valid, f"Expected valid data, got errors: {errors}"


def test_leafref_json_valid_path_missing_target():
    """Valid path expression but missing target node -> validation fails (require-instance)."""
    schema = _make_schema("/data-model/target")
    data = {"data-model": {"ref": "x"}}

    valid, errors = _validate(schema, data)
    assert not valid, "Expected invalid data when target node is missing"
    assert any("leafref" in e.lower() or "require-instance" in e.lower() for e in errors)


def test_leafref_json_invalid_path_expression_raises():
    """Invalid path expression in x-yang leafref should cause parse_json_schema to raise XPathSyntaxError."""
    # Missing closing bracket makes this an invalid path for parse_path()
    schema = _make_schema("/data-model/target[")

    with pytest.raises(XPathSyntaxError):
        parse_json_schema(schema)


def test_leafref_to_integer_leaf_emits_integer_in_generated_schema():
    """YANG leafref to an integer leaf is emitted as JSON Schema type integer (not string)."""
    # Root container name is arbitrary; paths use /data-model/... to match this module.
    yang = """
module lr-int {
  yang-version 1.1;
  namespace "urn:lr-int";
  prefix "lri";
  container data-model {
    leaf port {
      type int32;
    }
    leaf peer {
      type leafref {
        path "/data-model/port";
      }
    }
  }
}
"""
    module = parse_yang_string(yang)
    schema = generate_json_schema(module)
    peer = schema["properties"]["data-model"]["properties"]["peer"]
    assert peer["type"] == "integer"
    assert peer["x-yang"]["type"] == "leafref"
    assert peer["x-yang"]["path"] == "/data-model/port"

    round_module = parse_json_schema(schema)
    validator = YangValidator(round_module)
    ok, errors, _ = validator.validate(
        {"data-model": {"port": 42, "peer": 42}}
    )
    assert ok, f"Expected valid instance data, got: {errors}"

