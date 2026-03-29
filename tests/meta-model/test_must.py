"""
Meta-model must expressions: one positive and one negative test per must.

Each must statement in examples/meta-model.yang is covered by a test_*_valid
and test_*_invalid test. Tests use minimal data so the targeted must is the
one that passes or fails.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.meta_model_data import dm, ent, f_composite, f_computed, fp, subf
from xyang import YangValidator, parse_yang_file


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def _validate(meta_model, data: dict) -> tuple[bool, list]:
    validator = YangValidator(meta_model)
    is_valid, errors, _ = validator.validate(data)
    return is_valid, errors


# ---- data-model/allow_unlimited_fields ----


def test_allow_unlimited_fields_valid(meta_model):
    """allow_unlimited_fields present only when at least one entity has >7 non-array fields."""
    data = dm(
        allow_unlimited_fields=None,
        entities=[
            ent(
                "big",
                "id",
                [fp("id", "integer", description="PK.")] + [fp(f"f{i}", "string", description=f"F{i}.") for i in range(8)],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_allow_unlimited_fields_invalid(meta_model):
    """allow_unlimited_fields present but no entity has >7 non-array fields."""
    data = dm(
        allow_unlimited_fields=None,
        entities=[
            ent(
                "small",
                "id",
                [fp("id", "integer", description="PK."), fp("a", "string", description="A.")],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("allow_unlimited_fields" in str(e) for e in errors)


def test_entity_field_limit_valid(meta_model):
    """Entity with <=7 non-array fields passes (no allow_unlimited_fields)."""
    data = dm(
        entities=[
            ent("e", "id", [fp("id", "integer", description="PK."), fp("x", "string", description="X.")]),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_entity_field_limit_invalid(meta_model):
    """Entity with >7 non-array fields fails without allow_unlimited_fields."""
    data = dm(
        entities=[
            ent(
                "e",
                "id",
                [fp("id", "integer", description="PK.")]
                + [fp(f"f{i}", "string", description=f"F{i}.") for i in range(8)],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("7" in str(e) or "field" in str(e).lower() for e in errors)


def test_entity_name_underscore_valid(meta_model):
    """Entity name within underscore limit passes."""
    data = dm(
        entities=[ent("entity_a", "id", [fp("id", "integer", description="PK.")])],
    )
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_entity_name_underscore_invalid(meta_model):
    """Entity name exceeding underscore limit fails."""
    data = dm(
        entities=[ent("a_b_c_d", "id", [fp("id", "integer", description="PK.")])],
    )
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("underscore" in str(e).lower() or "name" in str(e).lower() for e in errors)


def test_primary_key_reference_valid(meta_model):
    """primary_key referencing existing field passes."""
    data = dm(entities=[ent("e", "id", [fp("id", "integer", description="PK.")])])
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_primary_key_reference_invalid(meta_model):
    """primary_key referencing non-existent field fails."""
    data = dm(
        entities=[ent("e", "missing", [fp("id", "integer", description="PK.")])],
    )
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("primary_key" in str(e) or "field" in str(e).lower() for e in errors)


def test_mindate_type_valid(meta_model):
    """minDate on date type passes."""
    data = dm(
        entities=[
            ent(
                "e",
                "id",
                [fp("id", "integer", description="PK."), fp("d", "date", minDate="2020-01-01", description="D.")],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_mindate_type_invalid(meta_model):
    """minDate on non-date type fails."""
    data = dm(
        entities=[
            ent(
                "e",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    fp("t", "string", minDate="2020-01-01", description="T."),
                ],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("minDate" in str(e) or "date" in str(e).lower() for e in errors)


def test_maxdate_type_valid(meta_model):
    """maxDate on date type passes."""
    data = dm(
        entities=[
            ent(
                "e",
                "id",
                [fp("id", "integer", description="PK."), fp("d", "date", maxDate="2020-12-31", description="D.")],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_maxdate_ordering_invalid(meta_model):
    """maxDate < minDate fails."""
    data = dm(
        entities=[
            ent(
                "e",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    fp("d", "date", minDate="2020-12-31", maxDate="2020-01-01", description="D."),
                ],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("maxDate" in str(e) or "minDate" in str(e) for e in errors)


def test_foreign_key_type_match_valid(meta_model):
    """FK field type matches referenced entity primary key type."""
    data = dm(
        entities=[
            ent("parent", "id", [fp("id", "integer", description="PK.")]),
            ent(
                "child",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    fp(
                        "parent_id",
                        "integer",
                        foreignKeys=[{"entity": "parent"}],
                        description="FK to parent.",
                    ),
                ],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_foreign_key_unknown_entity_invalid(meta_model):
    """foreignKeys entity leafref must reference an existing entity name."""
    data = dm(
        entities=[
            ent("child", "id", [fp("id", "integer", description="PK.")]),
            ent(
                "other",
                "oid",
                [
                    fp("oid", "integer", description="PK."),
                    fp(
                        "bad_fk",
                        "integer",
                        foreignKeys=[{"entity": "no_such_entity"}],
                        description="Broken FK target.",
                    ),
                ],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert errors


def test_computed_binary_two_fields_valid(meta_model):
    """Binary operation (add/subtraction) with exactly 2 fields passes."""
    data = dm(
        entities=[
            ent(
                "e",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    fp("a", "integer", description="A."),
                    fp("b", "integer", description="B."),
                    f_computed("sum", "integer", "add", [{"field": "a"}, {"field": "b"}]),
                ],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_computed_binary_two_fields_invalid(meta_model):
    """Binary operation with != 2 fields fails."""
    data = dm(
        entities=[
            ent(
                "e",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    fp("a", "integer", description="A."),
                    f_computed("bad", "integer", "add", [{"field": "a"}]),
                ],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("2" in str(e) or "field" in str(e).lower() for e in errors)


def test_computed_aggregation_min_two_fields_valid(meta_model):
    """Aggregation (min/max/average) with >=2 fields passes."""
    data = dm(
        entities=[
            ent(
                "e",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    fp("x", "integer", description="X."),
                    fp("y", "integer", description="Y."),
                    f_computed("m", "integer", "min", [{"field": "x"}, {"field": "y"}]),
                ],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_computed_aggregation_min_two_fields_invalid(meta_model):
    """Aggregation with single field fails."""
    data = dm(
        entities=[
            ent(
                "e",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    fp("x", "integer", description="X."),
                    f_computed("m", "integer", "min", [{"field": "x"}]),
                ],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("2" in str(e) or "field" in str(e).lower() for e in errors)


def test_computed_reference_exists_valid(meta_model):
    """Computed field referencing existing fields passes when consolidated."""
    data = dm(
        consolidated=True,
        entities=[
            ent(
                "e",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    fp("a", "integer", description="A."),
                    fp("b", "integer", description="B."),
                    f_computed("sum", "integer", "add", [{"field": "a"}, {"field": "b"}]),
                ],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_computed_reference_missing_invalid(meta_model):
    """Computed field referencing non-existent field fails when consolidated."""
    data = dm(
        consolidated=True,
        entities=[
            ent(
                "e",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    fp("a", "integer", description="A."),
                    {
                        "name": "bad",
                        "description": "Bad computed.",
                        "type": {"primitive": "integer"},
                        "computed": {
                            "operation": "subtraction",
                            "fields": [{"field": "a"}, {"field": "nonexistent_field"}],
                        },
                    },
                ],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("Computed field reference" in str(e) or "must exist" in str(e) for e in errors)


def test_computed_cross_entity_fk_valid(meta_model):
    """Cross-entity computed with FK in current entity passes when consolidated=True."""
    data = dm(
        consolidated=True,
        entities=[
            ent(
                "property_detail",
                "mls_number",
                [
                    fp("mls_number", "integer", description="MLS."),
                    fp("sqft", "integer", description="Sqft."),
                ],
            ),
            ent(
                "property_economics",
                "mls_number",
                [
                    fp(
                        "mls_number",
                        "integer",
                        foreignKeys=[{"entity": "property_detail"}],
                        description="FK MLS.",
                    ),
                    fp("price", "integer", description="Price."),
                    {
                        "name": "price_per_sqft",
                        "description": "Price per sqft.",
                        "type": {"primitive": "number"},
                        "computed": {
                            "operation": "division",
                            "fields": [
                                {"field": "price"},
                                {"field": "sqft", "entity": "property_detail"},
                            ],
                        },
                    },
                ],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_computed_cross_entity_no_fk_invalid(meta_model):
    """Cross-entity computed without FK in current entity fails when consolidated."""
    data = dm(
        consolidated=True,
        entities=[
            ent(
                "entity1",
                "id",
                [fp("id", "integer", description="PK."), fp("field1", "integer", description="F1.")],
            ),
            ent(
                "entity2",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    {
                        "name": "invalid_computed",
                        "description": "Invalid cross-entity.",
                        "type": {"primitive": "integer"},
                        "computed": {
                            "operation": "subtraction",
                            "fields": [{"field": "field1", "entity": "entity1"}, {"field": "id"}],
                        },
                    },
                ],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("foreign key" in str(e).lower() or "Cross-entity" in str(e) for e in errors)


def test_required_no_default_valid(meta_model):
    """required=true with no default passes."""
    data = dm(
        entities=[
            ent(
                "e",
                "id",
                [fp("id", "integer", description="PK."), fp("x", "string", required=True, description="X.")],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_required_with_default_invalid(meta_model):
    """required=true with default fails."""
    data = dm(
        entities=[
            ent(
                "e",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    fp("x", "string", required=True, default="v", description="X."),
                ],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("required" in str(e).lower() or "default" in str(e).lower() for e in errors)


def test_composite_subcomponent_type_valid(meta_model):
    """Composite subcomponent with non-composite type passes."""
    data = dm(
        entities=[
            ent(
                "e",
                "pk",
                [f_composite("pk", [subf("a", "integer"), subf("b", "string")], description="Composite PK.")],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_composite_subcomponent_type_invalid(meta_model):
    """Composite subcomponent with type composite (nested) fails."""
    nested = {
        "name": "nested",
        "description": "Nested composite.",
        "type": {"composite": [subf("x", "string")]},
    }
    data = dm(
        entities=[
            ent(
                "e",
                "pk",
                [f_composite("pk", [subf("a", "integer"), nested], description="Composite PK.")],
            ),
        ],
    )
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("composite" in str(e).lower() for e in errors)


def test_change_id_valid(meta_model):
    """Entity c/m referencing existing change id passes when consolidated."""
    data = dm(
        consolidated=True,
        changes=[{"id": 1, "timestamp": "2025-01-01T00:00:00Z"}],
        entities=[ent("e", "id", [fp("id", "integer", description="PK.")], c=1)],
    )
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_change_id_invalid(meta_model):
    """Entity c referencing non-existent change id fails when consolidated."""
    data = dm(
        consolidated=True,
        changes=[{"id": 1, "timestamp": "2025-01-01T00:00:00Z"}],
        entities=[ent("e", "id", [fp("id", "integer", description="PK.")], c=99)],
    )
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("change" in str(e).lower() or "c " in str(e) for e in errors)
