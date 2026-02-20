"""
Test for foreign key field existence constraint.

Must statement: deref(../entity)/../fields[name = current()]
Location: entities/fields/foreignKey/field
"""
import pytest
from xYang import YangValidator, parse_yang_file
from pathlib import Path


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_foreign_key_field_exists_valid(meta_model):
    """Test that foreign key field existing in referenced entity passes validation."""
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
                            "name": "parent_id",
                            "type": "integer",
                            "foreignKey": {
                                "entity": "parent",
                                "field": "id"
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Foreign key field existing in referenced entity should pass. Errors: {errors}"


def test_foreign_key_field_exists_invalid_missing(meta_model):
    """Test that foreign key field not existing in referenced entity fails validation."""
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
                            "name": "parent_id",
                            "type": "integer",
                            "foreignKey": {
                                "entity": "parent",
                                "field": "nonexistent"
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Foreign key field not existing in referenced entity should fail"
    assert any("foreign key field must exist" in str(err).lower() for err in errors), \
        f"Should have foreign key field existence error. Errors: {errors}"
