"""
Test for parents foreign key referencing primary key constraint.

Must statement: deref(deref(current())/../foreignKey/entity)/../primary_key[. = deref(current())/../foreignKey/field]
Location: entities/parents/child_fk
"""
import pytest
from xYang import YangValidator, parse_yang_file
from pathlib import Path


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_parents_foreign_key_references_primary_key_valid(meta_model):
    """Test that parents foreign key referencing primary key passes validation."""
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
                        {
                            "name": "children",
                            "type": "array",
                            "item_type": {"entity": "child"}
                        }
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
    assert is_valid, f"Parents foreign key referencing primary key should pass. Errors: {errors}"


def test_parents_foreign_key_references_primary_key_invalid(meta_model):
    """Test that parents foreign key not referencing primary key fails validation."""
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
                        {"name": "name", "type": "string"},
                        {
                            "name": "children",
                            "type": "array",
                            "item_type": {"entity": "child"}
                        }
                    ]
                },
                {
                    "name": "child",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "parent_name",
                            "type": "string",
                            "foreignKey": {
                                "entity": "parent",
                                "field": "name"
                            }
                        }
                    ],
                    "parents": [
                        {
                            "child_fk": "parent_name",
                            "parent_array": "children"
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Parents foreign key not referencing primary key should fail"
    assert any("primary key" in str(err).lower() for err in errors), \
        f"Should have primary key reference error. Errors: {errors}"
