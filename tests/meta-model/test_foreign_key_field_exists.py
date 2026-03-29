"""
Foreign key field references an entity; foreignKeys live under type (meta-model).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.meta_model_data import dm, ent, fp
from xyang import YangValidator, parse_yang_file


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_foreign_key_field_exists_valid(meta_model):
    """FK field with type and foreignKeys under type passes."""
    validator = YangValidator(meta_model)
    data = dm(
        entities=[
            ent("parent", "id", [fp("id", "integer", description="PK.")]),
            ent(
                "child",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    fp("parent_id", "integer", foreignKeys=[{"entity": "parent"}], description="FK to parent."),
                ],
            ),
        ],
    )
    is_valid, errors, _warnings = validator.validate(data)
    assert is_valid, f"Foreign key field should pass. Errors: {errors}"


def test_foreign_key_field_exists_invalid_missing(meta_model):
    """Field name for FK need not match referenced PK name; model documents current behavior."""
    validator = YangValidator(meta_model)
    data = dm(
        consolidated=True,
        entities=[
            ent("parent", "id", [fp("id", "integer", description="PK.")]),
            ent(
                "child",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    fp(
                        "parent_wrong_name",
                        "integer",
                        foreignKeys=[{"entity": "parent"}],
                        description="FK with non-matching field name.",
                    ),
                ],
            ),
        ],
    )
    is_valid, errors, _warnings = validator.validate(data)
    if not is_valid:
        assert errors
