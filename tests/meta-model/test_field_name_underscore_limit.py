"""
Test for field name underscore limit constraint.

Must statement: string-length(.) - string-length(translate(., '_', '')) <= ../../../../max_name_underscores
Location: entities/fields/name

Note: The path ../../../../max_name_underscores goes up 4 levels from entities[0]/fields[0]/name to data-model.
This is because from a list item context, we need to go: name -> fields[0] -> fields -> entities[0] -> entities -> data-model.
"""
import pytest
from xYang import YangValidator, parse_yang_file
from pathlib import Path


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_field_name_underscore_limit_valid(meta_model):
    """Test that field names within underscore limit pass validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "field_name",
                    "fields": [
                        {"name": "field_name", "type": "string", "primaryKey": True}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Valid field name should pass. Errors: {errors}"


def test_field_name_underscore_limit_valid_at_limit(meta_model):
    """Test that field names at the underscore limit pass validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "field_name_test",
                    "fields": [
                        {"name": "field_name_test", "type": "string", "primaryKey": True}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Field name at limit should pass. Errors: {errors}"


def test_field_name_underscore_limit_invalid_exceeds_default(meta_model):
    """Test that field names exceeding default underscore limit fail validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "consolidated": True,
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "field_name_test_value_exceed",
                    "fields": [
                        {"name": "field_name_test_value_exceed", "type": "string", "primaryKey": True}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Field name exceeding default limit should fail"
    assert any("underscore limit" in str(err).lower() for err in errors), \
        f"Should have underscore limit error. Errors: {errors}"
