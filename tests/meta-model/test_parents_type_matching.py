"""
Test for parents type matching constraint.

Must statement: deref(current())/../type = deref(deref(current())/../foreignKey/entity)/../fields[name = deref(current())/../foreignKey/field]/type
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


def test_parents_type_matching_valid(meta_model):
    """Test that parents with matching types pass validation."""
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
    assert is_valid, f"Parents with matching types should pass. Errors: {errors}"


def test_parents_type_matching_invalid(meta_model):
    """Test that parents with non-matching types fail validation."""
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
                        {"name": "id", "type": "string"},
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
    assert not is_valid, "Parents with non-matching types should fail"
    assert any("type must match" in str(err).lower() or "type" in str(err).lower() for err in errors), \
        f"Should have type matching error. Errors: {errors}"
