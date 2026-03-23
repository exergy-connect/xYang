"""
Meta-model must expressions: one positive and one negative test per must.

Each must statement in examples/meta-model.yang is covered by a test_*_valid
and test_*_invalid test. Tests use minimal data so the targeted must is the
one that passes or fails.
"""
from __future__ import annotations

import pytest
from pathlib import Path

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
# must "count(../entities[count(fields[type != 'array']) > 7]) > 0"


def test_allow_unlimited_fields_valid(meta_model):
    """allow_unlimited_fields present only when at least one entity has >7 non-array fields."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "allow_unlimited_fields": None,
            "entities": [
                {
                    "name": "big",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        *[{"name": f"f{i}", "type": "string"} for i in range(8)],
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_allow_unlimited_fields_invalid(meta_model):
    """allow_unlimited_fields present but no entity has >7 non-array fields."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "allow_unlimited_fields": None,
            "entities": [
                {
                    "name": "small",
                    "primary_key": "id",
                    "fields": [{"name": "id", "type": "integer"}, {"name": "a", "type": "string"}],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("allow_unlimited_fields" in str(e) for e in errors)


# ---- entities (list) ----
# must "../allow_unlimited_fields or count(fields[type != 'array']) <= 7" (when consolidated=false)


def test_entity_field_limit_valid(meta_model):
    """Entity with <=7 non-array fields passes (no allow_unlimited_fields)."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [{"name": "id", "type": "integer"}, {"name": "x", "type": "string"}],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_entity_field_limit_invalid(meta_model):
    """Entity with >7 non-array fields fails without allow_unlimited_fields."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        *[{"name": f"f{i}", "type": "string"} for i in range(8)],
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("7" in str(e) or "field" in str(e).lower() for e in errors)


# ---- entities/name ----
# must "string-length(.) - string-length(translate(., '_', '')) <= number(/data-model/max_name_underscores)"


def test_entity_name_underscore_valid(meta_model):
    """Entity name within underscore limit passes."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [{"name": "entity_a", "primary_key": "id", "fields": [{"name": "id", "type": "integer"}]}],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_entity_name_underscore_invalid(meta_model):
    """Entity name exceeding underscore limit fails."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {"name": "a_b_c_d", "primary_key": "id", "fields": [{"name": "id", "type": "integer"}]}
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("underscore" in str(e).lower() or "name" in str(e).lower() for e in errors)


# ---- entities/primary_key ----
# must "../fields[name = current()]"


def test_primary_key_reference_valid(meta_model):
    """primary_key referencing existing field passes."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {"name": "e", "primary_key": "id", "fields": [{"name": "id", "type": "integer"}]}
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_primary_key_reference_invalid(meta_model):
    """primary_key referencing non-existent field fails."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "missing",
                    "fields": [{"name": "id", "type": "integer"}],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("primary_key" in str(e) or "field" in str(e).lower() for e in errors)


# ---- entities/fields/minDate ----
# must "../type = 'date' or ../type = 'datetime'"; must "not(../maxDate) or . <= ../maxDate"


def test_mindate_type_valid(meta_model):
    """minDate on date type passes."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "d", "type": "date", "minDate": "2020-01-01"},
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_mindate_type_invalid(meta_model):
    """minDate on non-date type fails."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "t", "type": "string", "minDate": "2020-01-01"},
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("minDate" in str(e) or "date" in str(e).lower() for e in errors)


# ---- entities/fields/maxDate ----
# must "../type = 'date' or ../type = 'datetime'"; must "not(../minDate) or . >= ../minDate"


def test_maxdate_type_valid(meta_model):
    """maxDate on date type passes."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "d", "type": "date", "maxDate": "2020-12-31"},
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_maxdate_ordering_invalid(meta_model):
    """maxDate < minDate fails."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "d",
                            "type": "date",
                            "minDate": "2020-12-31",
                            "maxDate": "2020-01-01",
                        },
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("maxDate" in str(e) or "minDate" in str(e) for e in errors)


# ---- entities/fields/foreignKeys (list) ----
# must "../type = /data-model/entities[...]/primary_key]/type"


def test_foreign_key_type_match_valid(meta_model):
    """FK field type matches referenced entity primary key type."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {"name": "parent", "primary_key": "id", "fields": [{"name": "id", "type": "integer"}]},
                {
                    "name": "child",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "parent_id", "type": "integer", "foreignKeys": [{"entity": "parent"}]},
                    ],
                },
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_foreign_key_type_match_invalid(meta_model):
    """FK field type different from referenced PK type fails (consolidated so must is enforced)."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "consolidated": True,
            "entities": [
                {"name": "parent", "primary_key": "id", "fields": [{"name": "id", "type": "integer"}]},
                {
                    "name": "child",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "parent_id", "type": "string", "foreignKeys": [{"entity": "parent"}]},
                    ],
                },
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("primary key" in str(e).lower() or "type" in str(e).lower() for e in errors)


# ---- computed: count(fields) >= 2 (container must; list also has min-elements 2) ----


def test_computed_binary_two_fields_valid(meta_model):
    """Binary operation (add/subtraction) with exactly 2 fields passes."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "a", "type": "integer"},
                        {"name": "b", "type": "integer"},
                        {
                            "name": "sum",
                            "type": "integer",
                            "computed": {"operation": "add", "fields": [{"field": "a"}, {"field": "b"}]},
                        },
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_computed_binary_two_fields_invalid(meta_model):
    """Binary operation with != 2 fields fails."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "a", "type": "integer"},
                        {
                            "name": "bad",
                            "type": "integer",
                            "computed": {"operation": "add", "fields": [{"field": "a"}]},
                        },
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("2" in str(e) or "field" in str(e).lower() for e in errors)


def test_computed_aggregation_min_two_fields_valid(meta_model):
    """Aggregation (min/max/average) with >=2 fields passes."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "x", "type": "integer"},
                        {"name": "y", "type": "integer"},
                        {
                            "name": "m",
                            "type": "integer",
                            "computed": {"operation": "min", "fields": [{"field": "x"}, {"field": "y"}]},
                        },
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_computed_aggregation_min_two_fields_invalid(meta_model):
    """Aggregation with single field fails."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "x", "type": "integer"},
                        {
                            "name": "m",
                            "type": "integer",
                            "computed": {"operation": "min", "fields": [{"field": "x"}]},
                        },
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("2" in str(e) or "field" in str(e).lower() for e in errors)


# ---- computed/fields/field: reference must exist (when consolidated) ----
# must " consolidated = false() or ((not(../entity) and count(../../../../../../fields[name=current()])=1) or ...)"


def test_computed_reference_exists_valid(meta_model):
    """Computed field referencing existing fields passes when consolidated."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "consolidated": True,
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "a", "type": "integer"},
                        {"name": "b", "type": "integer"},
                        {
                            "name": "sum",
                            "type": "integer",
                            "computed": {"operation": "add", "fields": [{"field": "a"}, {"field": "b"}]},
                        },
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_computed_reference_missing_invalid(meta_model):
    """Computed field referencing non-existent field fails when consolidated."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "consolidated": True,
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "a", "type": "integer"},
                        {
                            "name": "bad",
                            "type": "integer",
                            "computed": {
                                "operation": "subtraction",
                                "fields": [{"field": "a"}, {"field": "nonexistent_field"}],
                            },
                        },
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("Computed field reference" in str(e) or "must exist" in str(e) for e in errors)


# ---- computed/fields/entity: cross-entity requires FK (when consolidated) ----
# must " consolidated = false() or count(../../../../../../fields[foreignKeys/entity = current()]) = 1"


def test_computed_cross_entity_fk_valid(meta_model):
    """Cross-entity computed with FK in current entity passes when consolidated=True (price_per_sqft-style: division, same-entity + cross-entity)."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "consolidated": True,
            "entities": [
                {
                    "name": "property_detail",
                    "primary_key": "mls_number",
                    "fields": [
                        {"name": "mls_number", "type": "integer"},
                        {"name": "sqft", "type": "integer"},
                    ],
                },
                {
                    "name": "property_economics",
                    "primary_key": "mls_number",
                    "fields": [
                        {"name": "mls_number", "type": "integer", "foreignKeys": [{"entity": "property_detail"}]},
                        {"name": "price", "type": "integer"},
                        {
                            "name": "price_per_sqft",
                            "type": "number",
                            "computed": {
                                "operation": "division",
                                "fields": [
                                    {"field": "price"},
                                    {"field": "sqft", "entity": "property_detail"},
                                ],
                            },
                        },
                    ],
                },
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_computed_cross_entity_no_fk_invalid(meta_model):
    """Cross-entity computed without FK in current entity fails when consolidated."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "consolidated": True,
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "id",
                    "fields": [{"name": "id", "type": "integer"}, {"name": "field1", "type": "integer"}],
                },
                {
                    "name": "entity2",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "invalid_computed",
                            "type": "integer",
                            "computed": {
                                "operation": "subtraction",
                                "fields": [
                                    {"field": "field1", "entity": "entity1"},
                                    {"field": "id"},
                                ],
                            },
                        },
                    ],
                },
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("foreign key" in str(e).lower() or "Cross-entity" in str(e) for e in errors)


# ---- entities/fields (field name in grouping) ----
# must "string-length(.) - ... <= number(/data-model/max_name_underscores)" on field name


def test_field_name_underscore_valid(meta_model):
    """Field name within underscore limit passes."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [{"name": "id", "type": "integer"}, {"name": "field_a", "type": "string"}],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_field_name_underscore_invalid(meta_model):
    """Field name exceeding underscore limit fails."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "a_b_c_d", "type": "string"},
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("underscore" in str(e).lower() for e in errors)


# ---- entities/fields/required ----
# must "not(../default) or . = false()"


def test_required_no_default_valid(meta_model):
    """required=true with no default passes."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "x", "type": "string", "required": True},
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_required_with_default_invalid(meta_model):
    """required=true with default fails."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "x", "type": "string", "required": True, "default": "v"},
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("required" in str(e).lower() or "default" in str(e).lower() for e in errors)


# ---- entities/fields/composite (subcomponent type) ----
# must ". != 'composite'" (no nested composites)


def test_composite_subcomponent_type_valid(meta_model):
    """Composite subcomponent with non-composite type passes."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "pk",
                    "fields": [
                        {
                            "name": "pk",
                            "type": "composite",
                            "composite": [
                                {"name": "a", "type": "integer"},
                                {"name": "b", "type": "string"},
                            ],
                        }
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_composite_subcomponent_type_invalid(meta_model):
    """Composite subcomponent with type composite (nested) fails."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "entities": [
                {
                    "name": "e",
                    "primary_key": "pk",
                    "fields": [
                        {
                            "name": "pk",
                            "type": "composite",
                            "composite": [
                                {"name": "a", "type": "integer"},
                                {"name": "nested", "type": "composite", "composite": [{"name": "x", "type": "string"}]},
                            ],
                        }
                    ],
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("composite" in str(e).lower() for e in errors)


# ---- entities/c and entities/m (change id) ----
# must "/data-model/consolidated = false() or /data-model/changes[id = current()]"
# Only enforced when consolidated=true; we test with consolidated=true and valid change id vs invalid.


def test_change_id_valid(meta_model):
    """Entity c/m referencing existing change id passes when consolidated."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "consolidated": True,
            "changes": [{"id": 1, "timestamp": "2025-01-01T00:00:00Z"}],
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [{"name": "id", "type": "integer"}],
                    "c": 1,
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert valid, errors


def test_change_id_invalid(meta_model):
    """Entity c referencing non-existent change id fails when consolidated."""
    data = {
        "data-model": {
            "name": "M",
            "version": "25.03.11.1",
            "author": "A",
            "consolidated": True,
            "changes": [{"id": 1, "timestamp": "2025-01-01T00:00:00Z"}],
            "entities": [
                {
                    "name": "e",
                    "primary_key": "id",
                    "fields": [{"name": "id", "type": "integer"}],
                    "c": 99,
                }
            ],
        }
    }
    valid, errors = _validate(meta_model, data)
    assert not valid
    assert any("change" in str(e).lower() or "c " in str(e) for e in errors)
