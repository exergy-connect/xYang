"""
Test for parents field name matching.

Note: The field name matching constraint was removed as it was too restrictive.
child_fk field name doesn't need to match parent's primary key name - it just
needs to reference a field with a foreignKey definition pointing to the parent's primary key.
"""
import pytest
from xYang import YangValidator, parse_yang_file
from pathlib import Path


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_parents_field_name_matching_valid_self_referential(meta_model):
    """Test that self-referential parents (same entity) pass validation regardless of field name."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer", "primaryKey": True},
                        {
                            "name": "parent_id",
                            "type": "integer",
                            "foreignKeys": [{"entity": "entity1", "field": "id"}]
                        },
                        {
                            "name": "children",
                            "type": "array",
                            "item_type": {"entity": "entity1"}
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
    assert is_valid, f"Self-referential parents should pass. Errors: {errors}"


def test_parents_field_name_matching_valid_cross_entity_matching(meta_model):
    """Test that cross-entity parents with matching field name pass validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "parent",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer", "primaryKey": True},
                        {"name": "children", "type": "array", "item_type": {"entity": "child"}}
                    ]
                },
                {
                    "name": "child",
                    "primary_key": "id",
                    "fields": [
                        {
                            "name": "id",
                            "type": "integer",
                            "foreignKeys": [{"entity": "parent", "field": "id"}],
                            "primaryKey": True
                        }
                    ],
                    "parents": [
                        {
                            "child_fk": "id",
                            "parent_array": "children"
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Cross-entity parents with matching field name should pass. Errors: {errors}"


def test_parents_field_name_matching_valid_cross_entity_not_matching(meta_model):
    """Test that cross-entity parents with non-matching field name pass validation.
    
    Note: Field name matching constraint was removed as it was too restrictive.
    child_fk field name doesn't need to match parent's primary key name - it just
    needs to reference a field with a foreignKey definition pointing to the parent's primary key.
    """
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "parent",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer", "primaryKey": True},
                        {"name": "children", "type": "array", "item_type": {"entity": "child"}}
                    ]
                },
                {
                    "name": "child",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer", "primaryKey": True},
                        {
                            "name": "parent_id",
                            "type": "integer",
                            "foreignKeys": [{"entity": "parent", "field": "id"}]
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
    assert is_valid, f"Cross-entity parents with non-matching field name should pass (field name matching constraint was removed). Errors: {errors}"
