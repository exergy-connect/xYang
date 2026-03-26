"""required / default on new-meta-model.yang (generic-field vs composite subfields)."""

from __future__ import annotations

from pathlib import Path

import pytest

from xyang import YangValidator, parse_yang_file

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
NEW_META_MODEL_YANG = REPO_ROOT / "examples" / "new-meta-model.yang"


@pytest.fixture
def new_meta_model_module():
    assert NEW_META_MODEL_YANG.is_file(), f"Missing {NEW_META_MODEL_YANG}"
    return parse_yang_file(str(NEW_META_MODEL_YANG))


def _base_data_model() -> dict:
    return {
        "data-model": {
            "name": "t",
            "version": "1",
            "consolidated": True,
            "entities": [
                {
                    "name": "e",
                    "primary_key": "pk",
                    "fields": [
                        {
                            "name": "pk",
                            "type": {"primitive": "string"},
                        },
                    ],
                }
            ],
        }
    }


def test_required_and_default_valid_when_exclusive(new_meta_model_module):
    """required true without default, and default without required true, validate."""
    dm = _base_data_model()["data-model"]
    ent = dm["entities"][0]
    ent["fields"].append(
        {
            "name": "with_default",
            "type": {"primitive": "integer"},
            "required": False,
            "default": 42,
        }
    )
    ent["fields"].append(
        {
            "name": "mandatory_flag",
            "type": {"primitive": "string"},
            "required": True,
        }
    )
    validator = YangValidator(new_meta_model_module)
    ok, errors, _warnings = validator.validate({"data-model": dm})
    assert ok, errors


def test_required_true_with_default_fails_must(new_meta_model_module):
    """Same node cannot have required true and default (generic-field must)."""
    dm = _base_data_model()["data-model"]
    ent = dm["entities"][0]
    ent["fields"].append(
        {
            "name": "bad",
            "type": {"primitive": "string"},
            "required": True,
            "default": "x",
        }
    )
    validator = YangValidator(new_meta_model_module)
    ok, errors, _warnings = validator.validate({"data-model": dm})
    assert not ok
    assert any("required" in e.lower() or "default" in e.lower() for e in errors)


def test_primitive_enum_valid_for_string(new_meta_model_module):
    """Optional type.enum allowed when primitive is string (grouping primitive-type-and-enum)."""
    dm = _base_data_model()["data-model"]
    ent = dm["entities"][0]
    ent["fields"].append(
        {
            "name": "status",
            "type": {"primitive": "string", "enum": ["a", "b"]},
        }
    )
    validator = YangValidator(new_meta_model_module)
    ok, errors, _warnings = validator.validate({"data-model": dm})
    assert ok, errors


def test_primitive_enum_invalid_for_boolean(new_meta_model_module):
    """enum list is rejected when primitive is not string, integer, or number."""
    dm = _base_data_model()["data-model"]
    ent = dm["entities"][0]
    ent["fields"].append(
        {
            "name": "bad_enum",
            "type": {"primitive": "boolean", "enum": [True, False]},
        }
    )
    validator = YangValidator(new_meta_model_module)
    ok, errors, _warnings = validator.validate({"data-model": dm})
    assert not ok
    assert any("enum" in e.lower() for e in errors)


def test_default_on_composite_subfield_valid(new_meta_model_module):
    """default is allowed on composite subcomponents (no required leaf there)."""
    dm = _base_data_model()["data-model"]
    ent = dm["entities"][0]
    ent["fields"] = [
        ent["fields"][0],
        {
            "name": "comp",
            "type": {
                "composite": [
                    {
                        "name": "sub",
                        "type": {"primitive": "number"},
                        "default": 1.5,
                    }
                ]
            },
        },
    ]
    ent["primary_key"] = "pk"
    validator = YangValidator(new_meta_model_module)
    ok, errors, _warnings = validator.validate({"data-model": dm})
    assert ok, errors
