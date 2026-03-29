"""
Test for array type with entity element (type.array.entity).

foreignKeys belong under type on scalar fields, not inside the array branch.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.meta_model_data import dm, ent, f_array_entity, fp
from xyang import YangValidator, parse_yang_file


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_array_item_type_foreign_key_valid(meta_model):
    """Array field with type.array.entity passes."""
    validator = YangValidator(meta_model)
    data = dm(
        entities=[
            ent("parent", "id", [fp("id", "integer", description="PK.")]),
            ent(
                "child",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    f_array_entity("parents", "parent", description="Parent refs."),
                ],
            ),
        ],
    )
    is_valid, errors, _warnings = validator.validate(data)
    assert is_valid, f"Array with entity element type should pass. Errors: {errors}"


def test_array_item_type_foreign_key_invalid(meta_model):
    """foreignKeys inside type.array is an unknown field (not part of array inner choice)."""
    validator = YangValidator(meta_model)
    data = dm(
        entities=[
            ent("parent", "id", [fp("id", "integer", description="PK.")]),
            ent(
                "child",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    {
                        "name": "parents",
                        "description": "Invalid nested FK.",
                        "type": {
                            "array": {
                                "entity": "parent",
                                "foreignKeys": [{"entity": "parent"}],
                            }
                        },
                    },
                ],
            ),
        ],
    )
    is_valid, errors, _warnings = validator.validate(data)
    assert not is_valid, "foreignKeys inside array container should be rejected"
    assert any("foreignKeys" in error or "Unknown field" in error for error in errors), (
        f"Expected unknown foreignKeys under array. Errors: {errors}"
    )
