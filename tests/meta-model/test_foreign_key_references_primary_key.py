"""
Test for foreign key referencing primary key constraint.

Must statement: deref(../entity)/../primary_key[. = current()]
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


def test_foreign_key_references_primary_key_valid(meta_model):
    """Test that foreign key referencing primary key passes validation."""
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
                        {"name": "id", "type": "integer", "primaryKey": True}
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
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Foreign key referencing primary key should pass. Errors: {errors}"


def test_foreign_key_references_primary_key_valid_composite(meta_model):
    """Test that foreign key referencing composite primary key passes."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "parent",
                    "primary_key": "composite_key",
                    "fields": [
                        {
                            "name": "composite_key",
                            "type": "composite",
                            "primaryKey": True,
                            "composite": [
                                {"name": "id", "type": "integer"}
                            ]
                        }
                    ]
                },
                {
                    "name": "child",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer", "primaryKey": True},
                        {
                            "name": "parent_key",
                            "type": "composite",
                            "foreignKeys": [{"entity": "parent", "field": "composite_key"}],
                            "composite": [
                                {"name": "id", "type": "integer"}
                            ]
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Foreign key referencing composite primary key should pass. Errors: {errors}"


def test_foreign_key_references_primary_key_invalid_not_primary_key(meta_model):
    """Test that foreign key not referencing primary key fails validation."""
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
                        {"name": "id", "type": "integer", "primaryKey": True},
                        {"name": "name", "type": "string"}
                    ]
                },
                {
                    "name": "child",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer", "primaryKey": True},
                        {
                            "name": "parent_name",
                            "type": "string",
                            "foreignKeys": [{"entity": "parent", "field": "name"}]
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Foreign key not referencing primary key should fail"
    assert any("primary key" in str(err).lower() for err in errors), \
        f"Should have primary key reference error. Errors: {errors}"
