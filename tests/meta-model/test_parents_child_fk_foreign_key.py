"""
Test for parents child_fk foreignKey definition constraint.

Must statement: deref(current())/../foreignKey
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


def test_parents_child_fk_foreign_key_valid(meta_model):
    """Test that parents child_fk with foreignKey definition passes validation."""
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
    assert is_valid, f"Parents child_fk with foreignKey should pass. Errors: {errors}"


def test_parents_child_fk_foreign_key_invalid_missing(meta_model):
    """Test that parents child_fk without foreignKey definition fails validation."""
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
                            "type": "integer"
                            # Missing foreignKey
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
    assert not is_valid, "Parents child_fk without foreignKey should fail"
    assert any("foreign key" in str(err).lower() and "definition" in str(err).lower() for err in errors), \
        f"Should have foreignKey definition error. Errors: {errors}"
