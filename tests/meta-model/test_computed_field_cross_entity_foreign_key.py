"""
Test for cross-entity computed field foreign key requirement constraint.

Must statement: count(../../../../../fields[foreignKey/entity = current()]) = 1
Location: entities/fields/computed/fields/entity
"""
import pytest
from xYang import YangValidator, parse_yang_file
from pathlib import Path


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_computed_field_cross_entity_foreign_key_valid(meta_model):
    """Test that cross-entity computed field with foreign key passes validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "value", "type": "integer"}
                    ]
                },
                {
                    "name": "entity2",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "entity1_id",
                            "type": "integer",
                            "foreignKey": {
                                "entity": "entity1",
                                "field": "id"
                            }
                        },
                        {
                            "name": "computed_value",
                            "type": "integer",
                            "computed": {
                                "operation": "add",
                                "fields": [
                                    {"field": "id"},
                                    {
                                        "field": "value",
                                        "entity": "entity1"
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Cross-entity computed field with foreign key should pass. Errors: {errors}"


def test_computed_field_cross_entity_foreign_key_invalid_no_foreign_key(meta_model):
    """Test that cross-entity computed field without foreign key fails validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "value", "type": "integer"}
                    ]
                },
                {
                    "name": "entity2",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "computed_value",
                            "type": "integer",
                            "computed": {
                                "operation": "add",
                                "fields": [
                                    {"field": "id"},
                                    {
                                        "field": "value",
                                        "entity": "entity1"
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Cross-entity computed field without foreign key should fail"
    assert any("foreign key" in str(err).lower() and "computed" in str(err).lower() for err in errors), \
        f"Should have foreign key requirement error. Errors: {errors}"
