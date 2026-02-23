"""
Test for parent array type constraint.

Must statement: /data-model/consolidated = false() or deref(deref(../child_fk)/../foreignKey/entity)/../fields[name = current()]/type = 'array'
Location: entities/parents/parent_array
"""
import pytest
from xYang import YangValidator, parse_yang_file
from pathlib import Path


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_parent_array_type_valid(meta_model):
    """Test that parent_array referencing array type field passes validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "consolidated": True,
            "entities": [
                {
                    "name": "parent",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "children", "type": "array", "item_type": {"entity": "child"}}
                    ]
                },
                {
                    "name": "child",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "parent_id",
                            "type": "integer",
                            "foreignKeys": [{"entity": "parent"}]
                        }
                    ],
                    "parents": [
                        {
                            "child_fk": "parent_id",
                            "parent_array": "children"
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"parent_array referencing array type should pass. Errors: {errors}"


def test_parent_array_type_invalid(meta_model):
    """Test that parent_array referencing non-array type field fails validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "consolidated": True,
            "entities": [
                {
                    "name": "parent",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "name", "type": "string"}
                    ]
                },
                {
                    "name": "child",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "parent_id",
                            "type": "integer",
                            "foreignKeys": [{"entity": "parent"}]
                        }
                    ],
                    "parents": [
                        {
                            "child_fk": "parent_id",
                            "parent_array": "name"
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "parent_array referencing non-array type should fail"
    assert any("array" in str(err).lower() and "type" in str(err).lower() for err in errors), \
        f"Should have array type error. Errors: {errors}"


def test_parent_array_type_consolidated_false_no_parent(meta_model):
    """Test that parent_array type validation is skipped when consolidated=false, even if parent entity is missing.
    
    The must constraint uses OR: /data-model/consolidated = false() or <deref check>
    When consolidated=false, the first part is true, so the OR should short-circuit
    and NOT evaluate the second part (deref), avoiding leafref errors.
    """
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "consolidated": False,
            "entities": [
                {
                    "name": "child",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "parent_id",
                            "type": "integer",
                            "foreignKeys": [{"entity": "parent"}]
                        }
                    ],
                    "parents": [
                        {
                            "child_fk": "parent_id",
                            "parent_array": "children"
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    # When consolidated=false, the OR should short-circuit and not evaluate deref()
    # This means NO errors should occur, including no leafref errors from deref()
    assert is_valid, \
        f"Validation should pass in Phase 1 (consolidated=false) without evaluating deref(). The OR should short-circuit. Errors: {errors}"
    assert len(errors) == 0, \
        f"No errors should occur when consolidated=false because the OR should short-circuit. Errors: {errors}"
