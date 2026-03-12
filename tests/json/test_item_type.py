"""
Item_type validation tests for two schema encodings: YANG and .yang.json.

The same schema (meta-model) is loaded either from .yang (native parser)
or from .yang.json (JSON parser). Each test uses a single shared data payload
and runs validation against both encodings so results are identical.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xyang import YangValidator, parse_yang_file
from xyang.json import parse_json_schema


_EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
META_MODEL_YANG = _EXAMPLES_DIR / "meta-model.yang"
META_MODEL_YANG_JSON = _EXAMPLES_DIR / "meta-model.yang.json"


def _minimal_data_model(entities: list) -> dict:
    """Minimal data-model wrapper so must expressions (consolidated, max_name_underscores) pass."""
    return {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",  # version-string pattern YY.MM.DD.N
            "author": "A",
            "consolidated": False,
            "max_name_underscores": 2,
            "entities": entities,
        }
    }


# Single shared data payloads: one object per scenario, reused for both encodings.
DATA_ITEM_TYPE_PRIMITIVE_VALID = _minimal_data_model([
    {
        "name": "e",
        "primary_key": "id",
        "fields": [
            {"name": "id", "type": "integer"},
            {"name": "tags", "type": "array", "item_type": {"primitive": "string"}},
        ],
    },
])

DATA_ITEM_TYPE_ENTITY_VALID = _minimal_data_model([
    {"name": "server", "primary_key": "id", "fields": [{"name": "id", "type": "integer"}]},
    {
        "name": "client",
        "primary_key": "id",
        "fields": [
            {"name": "id", "type": "integer"},
            {"name": "servers", "type": "array", "item_type": {"entity": "server"}},
        ],
    },
])

DATA_ITEM_TYPE_EMPTY_INVALID = _minimal_data_model([
    {
        "name": "e",
        "primary_key": "id",
        "fields": [
            {"name": "id", "type": "integer"},
            {"name": "tags", "type": "array", "item_type": {}},
        ],
    },
])

DATA_ITEM_TYPE_WHEN_FALSE_INVALID = _minimal_data_model([
    {
        "name": "e",
        "primary_key": "id",
        "fields": [
            {"name": "id", "type": "integer"},
            {"name": "title", "type": "string", "item_type": {"primitive": "string"}},
        ],
    },
])


@pytest.fixture
def module_from_yang():
    """Load meta-model from .yang (native parser)."""
    assert META_MODEL_YANG.exists(), f"Missing {META_MODEL_YANG}"
    return parse_yang_file(str(META_MODEL_YANG))


@pytest.fixture
def module_from_yang_json():
    """Load meta-model from .yang.json (JSON parser)."""
    assert META_MODEL_YANG_JSON.exists(), f"Missing {META_MODEL_YANG_JSON}"
    return parse_json_schema(META_MODEL_YANG_JSON)


def _validate(module, data: dict) -> tuple[bool, list]:
    validator = YangValidator(module)
    is_valid, errors, _ = validator.validate(data)
    return is_valid, list(errors)


# ---- Positive: type=array with item_type.primitive ----
def test_item_type_primitive_valid(module_from_yang, module_from_yang_json):
    """Both encodings: array field with item_type.primitive is valid."""
    valid_yang, errors_yang = _validate(module_from_yang, DATA_ITEM_TYPE_PRIMITIVE_VALID)
    valid_json, errors_json = _validate(module_from_yang_json, DATA_ITEM_TYPE_PRIMITIVE_VALID)
    assert valid_yang == valid_json, "YANG and YANG.json encodings must agree"
    assert valid_yang, errors_yang


# ---- Positive: type=array with item_type.entity ----
def test_item_type_entity_valid(module_from_yang, module_from_yang_json):
    """Both encodings: array field with item_type.entity is valid when entity exists."""
    valid_yang, errors_yang = _validate(module_from_yang, DATA_ITEM_TYPE_ENTITY_VALID)
    valid_json, errors_json = _validate(module_from_yang_json, DATA_ITEM_TYPE_ENTITY_VALID)
    assert valid_yang == valid_json, "YANG and YANG.json encodings must agree"
    assert valid_yang, errors_yang


# ---- Negative: type=array but item_type empty (mandatory choice missing) ----
def test_item_type_empty_invalid(module_from_yang, module_from_yang_json):
    """Both encodings: array field with empty item_type fails (mandatory choice)."""
    valid_yang, errors_yang = _validate(module_from_yang, DATA_ITEM_TYPE_EMPTY_INVALID)
    valid_json, errors_json = _validate(module_from_yang_json, DATA_ITEM_TYPE_EMPTY_INVALID)
    assert valid_yang == valid_json, "YANG and YANG.json encodings must agree"
    assert not valid_yang, "Expected invalid: item_type must have primitive or entity"
    assert len(errors_yang) > 0
    assert len(errors_json) > 0


# ---- Negative: item_type present when type != 'array' (when condition false) ----
def test_item_type_when_false_invalid(module_from_yang, module_from_yang_json):
    """Both encodings: item_type present with type=string is invalid (when false)."""
    valid_yang, errors_yang = _validate(module_from_yang, DATA_ITEM_TYPE_WHEN_FALSE_INVALID)
    valid_json, errors_json = _validate(module_from_yang_json, DATA_ITEM_TYPE_WHEN_FALSE_INVALID)
    assert valid_yang == valid_json, "YANG and YANG.json encodings must agree"
    assert not valid_yang, "Expected invalid: item_type only applicable when type=array"
    assert any("item_type" in str(e).lower() for e in errors_yang)
    assert any("item_type" in str(e).lower() for e in errors_json)
