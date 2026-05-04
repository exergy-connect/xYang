"""required / default on examples/meta-model.yang (generic-field vs composite subfields)."""

from __future__ import annotations

from pathlib import Path

import pytest

from xyang import YangValidator, parse_yang_file

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
META_MODEL_YANG = REPO_ROOT / "examples" / "meta-model.yang"


@pytest.fixture(name="meta_model_module")
def _meta_model_module_fixture():
    assert META_MODEL_YANG.is_file(), f"Missing {META_MODEL_YANG}"
    return parse_yang_file(str(META_MODEL_YANG))


def _base_data_model() -> dict:
    return {
        "data-model": {
            "name": "t",
            "version": "26.03.29.1",
            "author": "test",
            "description": "required/default tests",
            "consolidated": True,
            "entities": [
                {
                    "name": "e",
                    "description": "Entity e.",
                    "primary_key": "pk",
                    "fields": [
                        {
                            "name": "pk",
                            "description": "Primary key.",
                            "type": {"primitive": "string"},
                        },
                    ],
                }
            ],
        }
    }


def test_required_and_default_valid_when_exclusive(meta_model_module):
    """required true without default, and default without required true, validate."""
    dm = _base_data_model()["data-model"]
    ent = dm["entities"][0]
    ent["fields"].append(
        {
            "name": "with_default",
            "description": "Has default.",
            "type": {"primitive": "integer"},
            "required": False,
            "default": 42,
        }
    )
    ent["fields"].append(
        {
            "name": "mandatory_flag",
            "description": "Required flag.",
            "type": {"primitive": "string"},
            "required": True,
        }
    )
    validator = YangValidator(meta_model_module)
    ok, errors, _warnings = validator.validate({"data-model": dm})
    assert ok, errors


def test_required_true_with_default_fails_must(meta_model_module):
    """Same node cannot have required true and default (generic-field must)."""
    dm = _base_data_model()["data-model"]
    ent = dm["entities"][0]
    ent["fields"].append(
        {
            "name": "bad",
            "description": "Invalid required+default.",
            "type": {"primitive": "string"},
            "required": True,
            "default": "x",
        }
    )
    validator = YangValidator(meta_model_module)
    ok, errors, _warnings = validator.validate({"data-model": dm})
    assert not ok
    assert any("required" in e.lower() or "default" in e.lower() for e in errors)


def test_primitive_enum_valid_for_string(meta_model_module):
    """Enum-only closed list (no primitive leaf); valid primitive-type-and-enum case."""
    dm = _base_data_model()["data-model"]
    ent = dm["entities"][0]
    ent["fields"].append(
        {
            "name": "status",
            "description": "Status enum.",
            "type": {"enum": ["a", "b"]},
        }
    )
    validator = YangValidator(meta_model_module)
    ok, errors, _warnings = validator.validate({"data-model": dm})
    assert ok, errors


def test_primitive_enum_invalid_for_boolean(meta_model_module):
    """enum list is rejected when primitive is not string, integer, or number."""
    dm = _base_data_model()["data-model"]
    ent = dm["entities"][0]
    ent["fields"].append(
        {
            "name": "bad_enum",
            "description": "Invalid enum on boolean.",
            "type": {"primitive": "boolean", "enum": [True, False]},
        }
    )
    validator = YangValidator(meta_model_module)
    ok, errors, _warnings = validator.validate({"data-model": dm})
    assert not ok
    assert any("enum" in e.lower() for e in errors)


def test_min_max_and_minDate_on_field_valid(meta_model_module):
    """min/max/minDate/maxDate live under type with primitive (primitive-type-and-enum)."""
    dm = _base_data_model()["data-model"]
    ent = dm["entities"][0]
    ent["fields"].append(
        {
            "name": "qty",
            "description": "Quantity bounds.",
            "type": {"primitive": "integer", "min": 0, "max": 100},
        }
    )
    ent["fields"].append(
        {
            "name": "dob",
            "description": "Date of birth.",
            "type": {
                "primitive": "date",
                "minDate": "2020-01-01",
                "maxDate": "2030-12-31",
            },
        }
    )
    validator = YangValidator(meta_model_module)
    ok, errors, _warnings = validator.validate({"data-model": dm})
    assert ok, errors


def test_minDate_rejected_for_string_primitive(meta_model_module):
    """minDate must only apply when primitive is date or datetime."""
    dm = _base_data_model()["data-model"]
    ent = dm["entities"][0]
    ent["fields"].append(
        {
            "name": "bad_dates",
            "description": "minDate on string.",
            "type": {"primitive": "string", "minDate": "2020-01-01"},
        }
    )
    validator = YangValidator(meta_model_module)
    ok, errors, _warnings = validator.validate({"data-model": dm})
    assert not ok
    assert any("mindate" in e.lower() for e in errors)


def test_default_on_entity_field_with_type_definition_accepted(meta_model_module):
    """``default`` on a field with ``type.definition`` is valid (site-specific override)."""
    dm = _base_data_model()["data-model"]
    dm["consolidated"] = True
    ent = dm["entities"][0]
    ent["field_definitions"] = [
        {
            "name": "priority_level",
            "description": "Shared priority enum.",
            "type": {"enum": ["low", "medium", "high"]},
            "default": "low",
        }
    ]
    ent["fields"].append(
        {
            "name": "priority",
            "description": "Reference site overrides default to medium.",
            "type": {"definition": "priority_level"},
            "default": "medium",
        }
    )
    validator = YangValidator(meta_model_module)
    ok, errors, _warnings = validator.validate({"data-model": dm})
    assert ok, errors


def test_default_on_entity_field_primitive_definition_accepted(meta_model_module):
    """``default`` on a definition reference is valid when the definition is primitive."""
    dm = _base_data_model()["data-model"]
    ent = dm["entities"][0]
    ent["field_definitions"] = [
        {
            "name": "count_def",
            "description": "Reusable non-negative integer.",
            "type": {"primitive": "integer", "min": 0, "max": 99},
            "default": 1,
        }
    ]
    ent["fields"].append(
        {
            "name": "qty",
            "description": "Quantity from definition with site default 3.",
            "type": {"definition": "count_def"},
            "default": 3,
        }
    )
    validator = YangValidator(meta_model_module)
    ok, errors, _warnings = validator.validate({"data-model": dm})
    assert ok, errors


def test_default_on_entity_field_composite_definition_rejected(meta_model_module):
    """``default`` on a definition reference fails when the definition is composite."""
    dm = _base_data_model()["data-model"]
    ent = dm["entities"][0]
    ent["field_definitions"] = [
        {
            "name": "addr_block",
            "description": "Reusable address composite.",
            "type": {
                "composite": [
                    {
                        "name": "city",
                        "description": "City.",
                        "type": {"primitive": "string"},
                    }
                ]
            },
        }
    ]
    ent["fields"].append(
        {
            "name": "addr",
            "description": "Invalid: default at reference site for composite definition.",
            "type": {"definition": "addr_block"},
            "default": "n/a",
        }
    )
    validator = YangValidator(meta_model_module)
    ok, errors, _warnings = validator.validate({"data-model": dm})
    assert not ok
    assert any("open primitive" in e.lower() or "closed enum" in e.lower() for e in errors)


def test_default_on_field_definition_valid_for_enum_reuse(meta_model_module):
    """``default`` on the reusable ``field_definitions`` entry validates for enum reuse."""
    dm = _base_data_model()["data-model"]
    dm["consolidated"] = False
    ent = dm["entities"][0]
    ent["field_definitions"] = [
        {
            "name": "priority_level",
            "description": "Shared priority enum with default.",
            "type": {"enum": ["low", "medium", "high"]},
            "default": "medium",
        }
    ]
    ent["fields"].append(
        {
            "name": "priority",
            "description": "Reference only; inherits default from definition.",
            "type": {"definition": "priority_level"},
        }
    )
    validator = YangValidator(meta_model_module)
    ok, errors, _warnings = validator.validate({"data-model": dm})
    assert ok, errors


def test_default_on_composite_subfield_valid(meta_model_module):
    """default is allowed on composite subcomponents (no required leaf there)."""
    dm = _base_data_model()["data-model"]
    ent = dm["entities"][0]
    ent["fields"] = [
        ent["fields"][0],
        {
            "name": "comp",
            "description": "Composite with default subfield.",
            "type": {
                "composite": [
                    {
                        "name": "sub",
                        "description": "Sub with default.",
                        "type": {"primitive": "number"},
                        "default": 1.5,
                    }
                ]
            },
        },
    ]
    ent["primary_key"] = "pk"
    validator = YangValidator(meta_model_module)
    ok, errors, _warnings = validator.validate({"data-model": dm})
    assert ok, errors
