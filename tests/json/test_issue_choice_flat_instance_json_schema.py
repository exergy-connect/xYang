"""
Regression: JSON Schema instance shape matches YANG data for ``choice``.

A ``choice`` (and a ``case``) are not data nodes; case leaves appear on the parent
container. The generator hoists ``oneOf`` / ``not`` onto that container so generic
``jsonschema`` validation accepts the same payloads as ``YangValidator``.
"""

from __future__ import annotations

from pathlib import Path

import jsonschema
import pytest

from xyang import YangValidator, parse_yang_file
from xyang.json import generate_json_schema

_DATA_DIR = Path(__file__).resolve().parent / "data" / "choice_cases"
YANG_FILE = _DATA_DIR / "choice_cases.yang"


@pytest.fixture(scope="module")
def choice_module():
    assert YANG_FILE.exists(), f"Missing {YANG_FILE}"
    return parse_yang_file(str(YANG_FILE))


@pytest.fixture(scope="module")
def choice_schema(choice_module):
    return generate_json_schema(choice_module)


def test_yang_validator_accepts_flat_mandatory_choice_instance(choice_module):
    data = {"data-model": {"req_choice_container": {"primitive": "string"}}}
    ok, errors, _ = YangValidator(choice_module).validate(data)
    assert ok, errors


def test_json_schema_accepts_flat_mandatory_choice_instance(choice_schema):
    instance = {"data-model": {"req_choice_container": {"primitive": "string"}}}
    jsonschema.validate(instance, choice_schema)


def test_yang_validator_accepts_nested_item_type_pattern(choice_module):
    data = {
        "data-model": {
            "item_type_container": {"item_type": {"primitive": "string"}},
        }
    }
    ok, errors, _ = YangValidator(choice_module).validate(data)
    assert ok, errors


def test_json_schema_accepts_nested_item_type_flat_inner(choice_schema):
    instance = {
        "data-model": {
            "item_type_container": {"item_type": {"primitive": "string"}},
        }
    }
    jsonschema.validate(instance, choice_schema)
