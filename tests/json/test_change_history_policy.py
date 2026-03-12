"""
Standalone test for change-history-policy typedef: union of int32 (0..max) and string '*'.

Uses a minimal model with only this typedef. Asserts that both parsers produce
an identical AST and that both validate the same data documents (valid and invalid) alike.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xyang import YangValidator, parse_yang_file
from xyang.json import parse_json_schema

from tests.json.test_meta_model_ast_identical import normalize_module


_DATA_DIR = Path(__file__).resolve().parent / "data" / "change_history_policy"
YANG_FILE = _DATA_DIR / "change_history_policy.yang"
YANG_JSON_FILE = _DATA_DIR / "change_history_policy.yang.json"


# Valid: integer >= 0
DATA_VALID_INT = {
    "data-model": {
        "change_history_policy": 3,
    },
}

# Valid: string '*' (infinite history)
DATA_VALID_STAR = {
    "data-model": {
        "change_history_policy": "*",
    },
}

# Invalid: negative integer
DATA_INVALID_NEGATIVE = {
    "data-model": {
        "change_history_policy": -1,
    },
}

# Invalid: string that is not '*'
DATA_INVALID_STRING = {
    "data-model": {
        "change_history_policy": "unlimited",
    },
}


@pytest.fixture
def module_from_yang():
    """Load change-history-policy model from .yang."""
    assert YANG_FILE.exists(), f"Missing {YANG_FILE}"
    return parse_yang_file(str(YANG_FILE))


@pytest.fixture
def module_from_yang_json():
    """Load change-history-policy model from .yang.json."""
    assert YANG_JSON_FILE.exists(), f"Missing {YANG_JSON_FILE}"
    return parse_json_schema(YANG_JSON_FILE)


def test_change_history_policy_yang_and_json_produce_identical_ast(module_from_yang, module_from_yang_json):
    """Both parsers must produce an identical normalized AST for the change-history-policy typedef model."""
    norm_yang = normalize_module(module_from_yang)
    norm_json = normalize_module(module_from_yang_json)
    assert norm_yang == norm_json, (
        f"YANG and .yang.json ASTs differ.\nYANG: {norm_yang}\nJSON: {norm_json}"
    )


def test_change_history_policy_validate_valid_integer(module_from_yang, module_from_yang_json):
    """Both parsers must accept a valid integer value (e.g. 3)."""
    for mod in (module_from_yang, module_from_yang_json):
        valid, errors, _ = YangValidator(mod).validate(DATA_VALID_INT)
        assert valid, f"Expected valid (integer). Errors: {errors}"


def test_change_history_policy_validate_valid_star(module_from_yang, module_from_yang_json):
    """Both parsers must accept the string '*' (infinite history)."""
    for mod in (module_from_yang, module_from_yang_json):
        valid, errors, _ = YangValidator(mod).validate(DATA_VALID_STAR)
        assert valid, f"Expected valid ('*'). Errors: {errors}"


def test_change_history_policy_validate_invalid_negative(module_from_yang, module_from_yang_json):
    """Both parsers must reject a negative integer."""
    valid_yang, errors_yang, _ = YangValidator(module_from_yang).validate(DATA_INVALID_NEGATIVE)
    valid_json, errors_json, _ = YangValidator(module_from_yang_json).validate(DATA_INVALID_NEGATIVE)
    assert valid_yang == valid_json, "YANG and JSON validation result must agree"
    assert not valid_yang, f"Expected invalid (negative). YANG errors: {errors_yang}"
    assert not valid_json, f"Expected invalid (negative). JSON errors: {errors_json}"
    assert len(errors_yang) > 0 and len(errors_json) > 0


def test_change_history_policy_validate_invalid_string(module_from_yang, module_from_yang_json):
    """Both parsers must reject a string that is not '*'."""
    valid_yang, errors_yang, _ = YangValidator(module_from_yang).validate(DATA_INVALID_STRING)
    valid_json, errors_json, _ = YangValidator(module_from_yang_json).validate(DATA_INVALID_STRING)
    assert valid_yang == valid_json, "YANG and JSON validation result must agree"
    assert not valid_yang, f"Expected invalid (wrong string). YANG errors: {errors_yang}"
    assert not valid_json, f"Expected invalid (wrong string). JSON errors: {errors_json}"
    assert len(errors_yang) > 0 and len(errors_json) > 0
