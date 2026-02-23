"""
Test for parents foreign key field existence constraint.

Must statement: /data-model/entities[name = deref(current())/../foreignKey/entity]/fields[name = deref(current())/../foreignKey/field]
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


def test_parents_foreign_key_field_exists_valid(meta_model):
    """Test that parents foreign key field existing in parent entity passes validation."""
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
    assert is_valid, f"Parents foreign key field existing should pass. Errors: {errors}"


def test_parents_foreign_key_field_exists_invalid(meta_model):
    """Test that parents foreign key field with mismatched type fails validation.
    
    Since foreign keys always reference the primary key, validation should fail
    if the field type doesn't match the parent's primary key type.
    """
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
                            "type": "string",  # Type mismatch: parent primary key is integer
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
    assert not is_valid, "Parents foreign key field with mismatched type should fail"
    assert any("type" in str(err).lower() or "primary key" in str(err).lower() for err in errors), \
        f"Error should mention type or primary key. Errors: {errors}"
