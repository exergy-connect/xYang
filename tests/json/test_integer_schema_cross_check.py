"""The generated JSON Schema and YangValidator agree on RFC 7951 integers.

8/16/32-bit integers are JSON numbers. int64 is a decimal string.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from xyang import YangValidator
from xyang.json import generate_json_schema
from xyang.parser.yang_parser import YangParser

CASE = Path(__file__).resolve().parents[1] / "cases" / "types" / "integer"
CROSS = json.loads((CASE / "schema-cross-check.json").read_text(encoding="utf-8"))


def _schema_accepts(schema: dict, value: object) -> bool:
    options = schema.get("oneOf") or schema.get("anyOf")
    if options:
        return any(_schema_accepts(option, value) for option in options)
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            return False
        props = schema.get("properties") or {}
        if schema.get("additionalProperties") is False and any(key not in props for key in value):
            return False
        for key, item in value.items():
            if key in props and not _schema_accepts(props[key], item):
                return False
        return all(name in value for name in schema.get("required") or [])
    if kind == "integer":
        if isinstance(value, bool):
            return False
        if isinstance(value, float):
            if not value.is_integer():
                return False
            value = int(value)
        if not isinstance(value, int):
            return False
        if "minimum" in schema and value < schema["minimum"]:
            return False
        if "maximum" in schema and value > schema["maximum"]:
            return False
        return True
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if "minimum" in schema and value < schema["minimum"]:
            return False
        if "maximum" in schema and value > schema["maximum"]:
            return False
        return True
    if kind == "string":
        if not isinstance(value, str):
            return False
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            return False
        return True
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "array":
        if not isinstance(value, list):
            return False
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            return all(_schema_accepts(item_schema, item) for item in value)
        return True
    return False


def test_schema_and_validator_agree_on_integer_instances() -> None:
    module = YangParser().parse_file(CASE / CROSS["module"])
    schema = generate_json_schema(module)
    leaf = schema["properties"]["top"]["properties"]["u8"]
    assert leaf["type"] == "integer"
    validator = YangValidator(module)
    for inst in CROSS["instances"]:
        schema_ok = _schema_accepts(schema, inst["data"])
        validator_ok = validator.validate_detailed(inst["data"])["valid"]
        assert schema_ok == inst["valid"], inst["name"]
        assert validator_ok == inst["valid"], inst["name"]
        assert schema_ok == validator_ok, inst["name"]
