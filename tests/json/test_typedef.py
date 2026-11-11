"""
Standalone test for typedef handling: YANG vs .yang.json.

Uses a minimal model with a single version-string typedef. Asserts that both
parsers produce an identical AST and that both can validate the same data
document (valid and invalid) with the same result.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xyang import YangValidator, parse_yang_file
from xyang.json import parse_json_schema

from tests.json.test_meta_model_ast_identical import normalize_module


_DATA_DIR = Path(__file__).resolve().parent / "data" / "version_typedef"
YANG_FILE = _DATA_DIR / "version_typedef.yang"
YANG_JSON_FILE = _DATA_DIR / "version_typedef.yang.json"


# Valid document: version matches pattern YY.MM.DD.N
DATA_VALID = {
    "data-model": {
        "version": "25.03.11.1",
    },
}

# Invalid document: version does not match pattern
DATA_INVALID = {
    "data-model": {
        "version": "invalid",
    },
}


@pytest.fixture
def module_from_yang():
    """Load version-typedef model from .yang."""
    assert YANG_FILE.exists(), f"Missing {YANG_FILE}"
    return parse_yang_file(str(YANG_FILE))


@pytest.fixture
def module_from_yang_json():
    """Load version-typedef model from .yang.json."""
    assert YANG_JSON_FILE.exists(), f"Missing {YANG_JSON_FILE}"
    return parse_json_schema(YANG_JSON_FILE)


def test_typedef_yang_and_json_produce_identical_ast(module_from_yang, module_from_yang_json):
    """Both parsers must produce an identical normalized AST for the version-string typedef model."""
    norm_yang = normalize_module(module_from_yang)
    norm_json = normalize_module(module_from_yang_json)
    assert norm_yang == norm_json, (
        f"YANG and .yang.json ASTs differ.\nYANG: {norm_yang}\nJSON: {norm_json}"
    )


def test_typedef_validate_valid_document(module_from_yang, module_from_yang_json):
    """Both parsers must accept the same valid data document."""
    validator_yang = YangValidator(module_from_yang)
    validator_json = YangValidator(module_from_yang_json)
    valid_yang, errors_yang, _ = validator_yang.validate(DATA_VALID)
    valid_json, errors_json, _ = validator_json.validate(DATA_VALID)
    assert valid_yang == valid_json, "YANG and JSON validation result must agree"
    assert valid_yang, f"Expected valid data to pass. YANG errors: {errors_yang}"
    assert valid_json, f"Expected valid data to pass. JSON errors: {errors_json}"


def test_typedef_validate_invalid_document(module_from_yang, module_from_yang_json):
    """Both parsers must reject the same invalid data document."""
    validator_yang = YangValidator(module_from_yang)
    validator_json = YangValidator(module_from_yang_json)
    valid_yang, errors_yang, _ = validator_yang.validate(DATA_INVALID)
    valid_json, errors_json, _ = validator_json.validate(DATA_INVALID)
    assert valid_yang == valid_json, "YANG and JSON validation result must agree"
    assert not valid_yang, f"Expected invalid data to fail. YANG: {valid_yang}"
    assert not valid_json, f"Expected invalid data to fail. JSON: {valid_json}"
    assert len(errors_yang) > 0, "Expected at least one YANG validation error"
    assert len(errors_json) > 0, "Expected at least one JSON validation error"
