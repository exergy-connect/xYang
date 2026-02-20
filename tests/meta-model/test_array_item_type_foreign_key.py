"""
Test for array item_type foreignKey constraints.

Must statements:
1. deref(../entity)/../fields[name = current()]
2. deref(../entity)/../primary_key[. = current()]
Location: entities/fields/item_type/foreignKey/field
"""
import pytest
from xYang import YangValidator, parse_yang_file
from pathlib import Path


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_array_item_type_foreign_key_valid(meta_model):
    """Test that array item_type foreignKey with valid field and primary key passes."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "parent",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"}
                    ]
                },
                {
                    "name": "child",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "parents",
                            "type": "array",
                            "item_type": {
                                "foreignKey": {
                                    "entity": "parent",
                                    "field": "id"
                                }
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Array item_type foreignKey with valid reference should pass. Errors: {errors}"


def test_array_item_type_foreign_key_invalid_field_missing(meta_model):
    """Test that array item_type foreignKey with non-existent field fails."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "parent",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"}
                    ]
                },
                {
                    "name": "child",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "parents",
                            "type": "array",
                            "item_type": {
                                "foreignKey": {
                                    "entity": "parent",
                                    "field": "nonexistent"
                                }
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Array item_type foreignKey with non-existent field should fail"
    assert any("foreign key field must exist" in str(err).lower() for err in errors), \
        f"Should have foreign key field existence error. Errors: {errors}"


def test_array_item_type_foreign_key_invalid_not_primary_key(meta_model):
    """Test that array item_type foreignKey not referencing primary key fails."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "parent",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "name", "type": "string"}
                    ]
                },
                {
                    "name": "child",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "parents",
                            "type": "array",
                            "item_type": {
                                "foreignKey": {
                                    "entity": "parent",
                                    "field": "name"
                                }
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Array item_type foreignKey not referencing primary key should fail"
    assert any("primary key" in str(err).lower() for err in errors), \
        f"Should have primary key reference error. Errors: {errors}"
