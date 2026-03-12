"""
JSON schema tests for YANG choice: generated schema shape and validation.

Covers both mandatory choice (oneOf with required) and optional choice
(not { required: all_keys }). Asserts the generator emits no x-yang on the
choice node and validates payloads against the YANG module.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xyang import YangValidator, parse_yang_file
from xyang.json import generate_json_schema

_DATA_DIR = Path(__file__).resolve().parent / "data" / "choice_cases"
YANG_FILE = _DATA_DIR / "choice_cases.yang"


def _minimal_data_model(
    req_choice_container: dict | None = None,
    opt_choice_container: dict | None = None,
) -> dict:
    """Build data-model payload. Choice case leaves are direct under the container (no choice key)."""
    data: dict = {"data-model": {}}
    if req_choice_container is not None:
        data["data-model"]["req_choice_container"] = req_choice_container
    if opt_choice_container is not None:
        data["data-model"]["opt_choice_container"] = opt_choice_container
    return data


# ---- Mandatory choice: exactly one of primitive | entity (leaves under container) ----
DATA_MANDATORY_PRIMITIVE = _minimal_data_model(req_choice_container={"primitive": "string"})
DATA_MANDATORY_ENTITY = _minimal_data_model(req_choice_container={"entity": "e1"})
DATA_MANDATORY_EMPTY = _minimal_data_model(req_choice_container={})
DATA_MANDATORY_BOTH = _minimal_data_model(
    req_choice_container={"primitive": "string", "entity": "e1"}
)

# ---- Optional choice: zero or one of a | b ----
DATA_OPTIONAL_EMPTY = _minimal_data_model(opt_choice_container={})
DATA_OPTIONAL_A = _minimal_data_model(opt_choice_container={"a": "x"})
DATA_OPTIONAL_B = _minimal_data_model(opt_choice_container={"b": "y"})
DATA_OPTIONAL_BOTH = _minimal_data_model(opt_choice_container={"a": "x", "b": "y"})


@pytest.fixture
def module_from_yang():
    """Load choice-cases model from .yang."""
    assert YANG_FILE.exists(), f"Missing {YANG_FILE}"
    return parse_yang_file(str(YANG_FILE))


@pytest.fixture
def generated_schema(module_from_yang):
    """Generate JSON schema from the YANG module."""
    return generate_json_schema(module_from_yang)


def _get_choice_schemas(schema: dict) -> tuple[dict, dict]:
    """Return (req_choice_schema, opt_choice_schema) from generated root."""
    dm = schema.get("properties", {}).get("data-model", {})
    props = dm.get("properties", {})
    req_container = props.get("req_choice_container", {})
    opt_container = props.get("opt_choice_container", {})
    req_choice = req_container.get("properties", {}).get("req_choice", {})
    opt_choice = opt_container.get("properties", {}).get("opt_choice", {})
    return req_choice, opt_choice


# ---- Generated schema structure (no x-yang on choice; oneOf / not) ----
def test_choice_mandatory_schema_has_one_of_and_no_xyang(generated_schema):
    """Mandatory choice is emitted with oneOf and without x-yang."""
    req, _ = _get_choice_schemas(generated_schema)
    assert "oneOf" in req, "Mandatory choice must have oneOf"
    assert [{"required": ["primitive"]}, {"required": ["entity"]}] == req["oneOf"]
    assert "x-yang" not in req, "Choice node must not have x-yang"


def test_choice_optional_schema_has_not_and_no_xyang(generated_schema):
    """Optional choice is emitted with not.required and without x-yang."""
    _, opt = _get_choice_schemas(generated_schema)
    assert "not" in opt, "Optional choice must have not"
    assert opt["not"] == {"required": ["a", "b"]}
    assert "x-yang" not in opt, "Choice node must not have x-yang"


# ---- Validation: mandatory choice ----
def test_mandatory_choice_primitive_valid(module_from_yang):
    """Mandatory choice with only primitive is valid."""
    valid, errors, _ = YangValidator(module_from_yang).validate(DATA_MANDATORY_PRIMITIVE)
    assert valid, f"Expected valid. Errors: {errors}"


def test_mandatory_choice_entity_valid(module_from_yang):
    """Mandatory choice with only entity is valid."""
    valid, errors, _ = YangValidator(module_from_yang).validate(DATA_MANDATORY_ENTITY)
    assert valid, f"Expected valid. Errors: {errors}"


def test_mandatory_choice_empty_invalid(module_from_yang):
    """Mandatory choice with empty object is invalid."""
    valid, errors, _ = YangValidator(module_from_yang).validate(DATA_MANDATORY_EMPTY)
    assert not valid, "Expected invalid when no case selected"
    assert len(errors) > 0


def test_mandatory_choice_both_invalid(module_from_yang):
    """Mandatory choice with both primitive and entity is invalid."""
    valid, errors, _ = YangValidator(module_from_yang).validate(DATA_MANDATORY_BOTH)
    assert not valid, "Expected invalid when both cases present"
    assert len(errors) > 0


# ---- Validation: optional choice ----
def test_optional_choice_empty_valid(module_from_yang):
    """Optional choice with empty object is valid."""
    valid, errors, _ = YangValidator(module_from_yang).validate(DATA_OPTIONAL_EMPTY)
    assert valid, f"Expected valid. Errors: {errors}"


def test_optional_choice_a_valid(module_from_yang):
    """Optional choice with only a is valid."""
    valid, errors, _ = YangValidator(module_from_yang).validate(DATA_OPTIONAL_A)
    assert valid, f"Expected valid. Errors: {errors}"


def test_optional_choice_b_valid(module_from_yang):
    """Optional choice with only b is valid."""
    valid, errors, _ = YangValidator(module_from_yang).validate(DATA_OPTIONAL_B)
    assert valid, f"Expected valid. Errors: {errors}"


def test_optional_choice_both_invalid(module_from_yang):
    """Optional choice with both a and b is invalid (not required forbids both)."""
    valid, errors, _ = YangValidator(module_from_yang).validate(DATA_OPTIONAL_BOTH)
    assert not valid, "Expected invalid when both cases present"
    assert len(errors) > 0
