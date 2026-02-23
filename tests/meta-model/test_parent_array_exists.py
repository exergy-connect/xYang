"""
Test for parent array existence constraint.

Must statement: deref(deref(../child_fk)/../foreignKey/entity)/../fields[name = current()]
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


def test_parent_array_exists_valid(meta_model):
    """Test that parent_array existing in parent entity passes validation."""
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
    assert is_valid, f"parent_array existing in parent entity should pass. Errors: {errors}"


def test_parent_array_exists_invalid(meta_model):
    """Test that parent_array not existing in parent entity fails validation."""
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
                            "foreignKeys": [{"entity": "parent", "field": "id"}]
                        }
                    ],
                    "parents": [
                        {
                            "child_fk": "parent_id",
                            "parent_array": "nonexistent"
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "parent_array not existing in parent entity should fail"
    assert any("parent array field must exist" in str(err).lower() for err in errors), \
        f"Should have parent array existence error. Errors: {errors}"
