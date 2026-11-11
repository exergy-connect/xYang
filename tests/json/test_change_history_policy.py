"""YANG vs .yang.json AST parity for change-history-policy typedef.

Validation of the uint32 | '*' union lives in
``tests/cases/types/typedef-union-star``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xyang import parse_yang_file
from xyang.json import parse_json_schema

from tests.json.test_meta_model_ast_identical import normalize_module


_DATA_DIR = Path(__file__).resolve().parent / "data" / "change_history_policy"
YANG_FILE = _DATA_DIR / "change_history_policy.yang"
YANG_JSON_FILE = _DATA_DIR / "change_history_policy.yang.json"


@pytest.fixture(scope="module")
def module_from_yang():
    assert YANG_FILE.exists(), f"Missing {YANG_FILE}"
    return parse_yang_file(str(YANG_FILE))


@pytest.fixture(scope="module")
def module_from_yang_json():
    assert YANG_JSON_FILE.exists(), f"Missing {YANG_JSON_FILE}"
    return parse_json_schema(YANG_JSON_FILE)


def test_change_history_policy_yang_and_json_produce_identical_ast(module_from_yang, module_from_yang_json):
    """Both parsers must produce an identical normalized AST for the change-history-policy typedef model."""
    norm_yang = normalize_module(module_from_yang)
    norm_json = normalize_module(module_from_yang_json)
    assert norm_yang == norm_json, (
        f"YANG and .yang.json ASTs differ.\nYANG: {norm_yang}\nJSON: {norm_json}"
    )
