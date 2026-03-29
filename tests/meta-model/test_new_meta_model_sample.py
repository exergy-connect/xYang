"""Validate tests/data/new_meta_model_sample.yaml against examples/meta-model.yang."""

from __future__ import annotations

from pathlib import Path

import pytest

from xyang import YangValidator, parse_yang_file

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
META_MODEL_YANG = REPO_ROOT / "examples" / "meta-model.yang"
SAMPLE_YAML = REPO_ROOT / "tests" / "data" / "new_meta_model_sample.yaml"

# Every enum in typedef primitive-type-name (examples/meta-model.yang), as used under type.primitive.
_PRIMITIVE_TYPE_NAME_ENUMS = frozenset(
    {
        "string",
        "integer",
        "number",
        "boolean",
        "array",
        "datetime",
        "date",
        "duration_in_days",
        "qualified_string",
        "qualified_integer",
        "qualified_number",
    }
)

# Field names in new_meta_model_sample.yaml that exercise each generic-field type branch.
_TYPE_SHAPE_FIELD_NAMES = frozenset(
    {
        "pk",
        "via_definition",
        "arr_items_primitive",
        "arr_items_composite",
        "top_composite",
    }
)


@pytest.fixture
def meta_model_module():
    assert META_MODEL_YANG.is_file(), f"Missing {META_MODEL_YANG}"
    return parse_yang_file(str(META_MODEL_YANG))


def _load_sample_data_model() -> dict:
    yaml = pytest.importorskip("yaml", reason="pip install -e '.[dev]' (PyYAML)")
    assert SAMPLE_YAML.is_file(), f"Missing {SAMPLE_YAML}"
    raw = SAMPLE_YAML.read_text(encoding="utf-8")
    tree = yaml.safe_load(raw)
    assert isinstance(tree, dict), "Root of sample YAML must be a mapping"
    return {"data-model": tree}


def test_new_meta_model_sample_yaml_validates(meta_model_module):
    """Full sample YAML conforms to examples/meta-model.yang."""
    data = _load_sample_data_model()
    validator = YangValidator(meta_model_module)
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Validation errors: {errors}; warnings: {warnings}"


def test_new_meta_model_sample_covers_all_primitive_enums_and_type_shapes(meta_model_module):
    """Each primitive-type-name value and each generic-field type branch appears and validates."""
    data = _load_sample_data_model()
    validator = YangValidator(meta_model_module)
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Validation errors: {errors}; warnings: {warnings}"

    entities = data["data-model"]["entities"]
    demo = next(e for e in entities if e["name"] == "demo")
    fields = demo["fields"]
    by_name = {f["name"]: f for f in fields}
    names = frozenset(by_name)

    for enum in _PRIMITIVE_TYPE_NAME_ENUMS:
        fname = f"prim_{enum}"
        assert fname in names, f"Sample missing field for primitive enum {enum!r}"
        prim = by_name[fname]["type"]["primitive"]
        assert prim == enum, f"Field {fname}: expected primitive {enum!r}, got {prim!r}"

    for required in _TYPE_SHAPE_FIELD_NAMES:
        assert required in names, f"Sample missing type-shape field {required!r}"

    assert by_name["via_definition"]["type"]["definition"] == "reusable_string"
    assert by_name["arr_items_primitive"]["type"]["array"]["primitive"] == "integer"
    assert len(by_name["arr_items_composite"]["type"]["array"]["composite"]) >= 1
    assert len(by_name["top_composite"]["type"]["composite"]) >= 1


@pytest.mark.parametrize(
    "fragment",
    [
        pytest.param(
            {
                "name": "p",
                "version": "26.03.29.1",
                "author": "t",
                "description": "Minimal primitive branch.",
                "consolidated": True,
                "entities": [
                    {
                        "name": "e",
                        "description": "Entity e.",
                        "primary_key": "id",
                        "fields": [
                            {"name": "id", "description": "PK.", "type": {"primitive": "string"}},
                        ],
                    }
                ],
            },
            id="primitive",
        ),
        pytest.param(
            {
                "name": "p",
                "version": "26.03.29.1",
                "author": "t",
                "description": "Definition ref branch.",
                "consolidated": True,
                "entities": [
                    {
                        "name": "e",
                        "description": "Entity e.",
                        "primary_key": "id",
                        "field_definitions": [
                            {"name": "d", "description": "Reusable int.", "type": {"primitive": "integer"}},
                        ],
                        "fields": [
                            {"name": "id", "description": "PK.", "type": {"primitive": "string"}},
                            {"name": "r", "description": "Via definition.", "type": {"definition": "d"}},
                        ],
                    }
                ],
            },
            id="definition_ref",
        ),
        pytest.param(
            {
                "name": "p",
                "version": "26.03.29.1",
                "author": "t",
                "description": "Array of primitives.",
                "consolidated": True,
                "entities": [
                    {
                        "name": "e",
                        "description": "Entity e.",
                        "primary_key": "id",
                        "fields": [
                            {"name": "id", "description": "PK.", "type": {"primitive": "string"}},
                            {
                                "name": "a",
                                "description": "Number array.",
                                "type": {"array": {"primitive": "number"}},
                            },
                        ],
                    }
                ],
            },
            id="array_primitive_element",
        ),
        pytest.param(
            {
                "name": "p",
                "version": "26.03.29.1",
                "author": "t",
                "description": "Array of composite.",
                "consolidated": True,
                "entities": [
                    {
                        "name": "e",
                        "description": "Entity e.",
                        "primary_key": "id",
                        "fields": [
                            {"name": "id", "description": "PK.", "type": {"primitive": "string"}},
                            {
                                "name": "a",
                                "description": "Composite array.",
                                "type": {
                                    "array": {
                                        "composite": [
                                            {
                                                "name": "x",
                                                "description": "Sub x.",
                                                "type": {"primitive": "boolean"},
                                            },
                                        ]
                                    }
                                },
                            },
                        ],
                    }
                ],
            },
            id="array_composite_element",
        ),
        pytest.param(
            {
                "name": "p",
                "version": "26.03.29.1",
                "author": "t",
                "description": "Top composite.",
                "consolidated": True,
                "entities": [
                    {
                        "name": "e",
                        "description": "Entity e.",
                        "primary_key": "id",
                        "fields": [
                            {"name": "id", "description": "PK.", "type": {"primitive": "string"}},
                            {
                                "name": "c",
                                "description": "Composite field.",
                                "type": {
                                    "composite": [
                                        {"name": "u", "description": "U.", "type": {"primitive": "date"}},
                                        {"name": "v", "description": "V.", "type": {"primitive": "datetime"}},
                                    ]
                                },
                            },
                        ],
                    }
                ],
            },
            id="top_level_composite",
        ),
    ],
)
def test_generic_field_type_branch_minimal_valid(meta_model_module, fragment: dict):
    """Each top-level generic-field type choice branch validates in isolation."""
    data = {"data-model": fragment}
    validator = YangValidator(meta_model_module)
    is_valid, errors, _warnings = validator.validate(data)
    assert is_valid, errors


def test_field_definition_definition_ref_rejected(meta_model_module):
    """field_definitions list must not use type.definition (refine must on generic-field)."""
    data = {
        "data-model": {
            "name": "Bad",
            "version": "26.03.29.1",
            "author": "t",
            "description": "Nested definition ref (invalid).",
            "consolidated": False,
            "entities": [
                {
                    "name": "e",
                    "description": "Entity e.",
                    "primary_key": "id",
                    "field_definitions": [
                        {"name": "base", "description": "Base.", "type": {"primitive": "string"}},
                        {
                            "name": "nested_ref",
                            "description": "Invalid chained def.",
                            "type": {"definition": "base"},
                        },
                    ],
                    "fields": [{"name": "id", "description": "PK.", "type": {"primitive": "string"}}],
                }
            ],
        }
    }
    validator = YangValidator(meta_model_module)
    is_valid, errors, _warnings = validator.validate(data)
    assert not is_valid
    assert any("field_definition cannot reference another" in str(e) for e in errors)


def test_new_meta_model_parent_array_must_rejects_non_array_target(meta_model_module):
    """parent_array must requires a direct type/array on the referenced field (consolidated=true)."""
    data = {
        "data-model": {
            "name": "t",
            "version": "26.03.29.1",
            "author": "t",
            "description": "parent_array negative test.",
            "consolidated": True,
            "entities": [
                {
                    "name": "company",
                    "brief": "c",
                    "description": "Company.",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "description": "PK.", "type": {"primitive": "string"}},
                        {
                            "name": "departments",
                            "description": "Not an entity array.",
                            "type": {"array": {"primitive": "string"}},
                        },
                    ],
                },
                {
                    "name": "department",
                    "brief": "d",
                    "description": "Department.",
                    "primary_key": "did",
                    "fields": [
                        {"name": "did", "description": "PK.", "type": {"primitive": "string"}},
                        {
                            "name": "company_id",
                            "description": "Broken parent_array target.",
                            "type": {
                                "primitive": "string",
                                "foreignKeys": [{"entity": "company", "parent_array": "id"}],
                            },
                        },
                    ],
                },
            ],
        }
    }
    validator = YangValidator(meta_model_module)
    is_valid, errors, _warnings = validator.validate(data)
    assert not is_valid
    assert any("parent_array must name" in str(e) for e in errors)
