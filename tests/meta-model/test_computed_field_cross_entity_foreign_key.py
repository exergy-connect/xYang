"""
Cross-entity computed field: optional entity leaf on computed/fields entries;
foreignKeys under type on the scalar FK field.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.meta_model_data import dm, ent, f_computed, fp
from xyang import YangValidator, parse_yang_file


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_computed_field_cross_entity_foreign_key_valid(meta_model):
    """Cross-entity computed field with FK on current entity passes."""
    validator = YangValidator(meta_model)
    data = dm(
        entities=[
            ent(
                "entity1",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    fp("value", "integer", description="Value."),
                ],
            ),
            ent(
                "entity2",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    fp("entity1_id", "integer", foreignKeys=[{"entity": "entity1"}], description="FK to entity1."),
                    f_computed(
                        "computed_value",
                        "integer",
                        "add",
                        [{"field": "entity1_id"}, {"field": "value", "entity": "entity1"}],
                    ),
                ],
            ),
        ],
    )
    is_valid, errors, _warnings = validator.validate(data)
    assert is_valid, f"Cross-entity computed field with foreign key should pass. Errors: {errors}"


def test_computed_field_cross_entity_foreign_key_invalid_no_foreign_key(meta_model):
    """Cross-entity computed without FK to target entity fails when consolidated."""
    validator = YangValidator(meta_model)
    data = dm(
        consolidated=True,
        entities=[
            ent(
                "entity1",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    fp("value", "integer", description="Value."),
                ],
            ),
            ent(
                "entity2",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    fp("entity1_id", "integer", description="Scalar without FK to entity1."),
                    {
                        "name": "computed_value",
                        "description": "Computed without FK.",
                        "type": {"primitive": "integer"},
                        "computed": {
                            "operation": "add",
                            "fields": [
                                {"field": "entity1_id"},
                                {"field": "value", "entity": "entity1"},
                            ],
                        },
                    },
                ],
            ),
        ],
    )
    is_valid, errors, _warnings = validator.validate(data)
    assert not is_valid, "Cross-entity computed field without foreign key should fail"
    assert any("foreign key" in str(err).lower() for err in errors), (
        f"Should have foreign key requirement error. Errors: {errors}"
    )
