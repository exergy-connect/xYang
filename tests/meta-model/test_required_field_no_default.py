"""
Test for required field cannot have default constraint.

Must statement: not(../default) or . = false()
Location: entities/fields/required
"""
import pytest
from xYang import YangValidator, parse_yang_file
from pathlib import Path


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_required_field_no_default_valid_not_required(meta_model):
    """Test that non-required field with default passes validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "name",
                            "type": "string",
                            "required": False,
                            "default": "default_name"
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Non-required field with default should pass. Errors: {errors}"


def test_required_field_no_default_valid_required_no_default(meta_model):
    """Test that required field without default passes validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "name",
                            "type": "string",
                            "required": True
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Required field without default should pass. Errors: {errors}"


def test_required_field_no_default_invalid_required_with_default(meta_model):
    """Test that required field with default fails validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "name",
                            "type": "string",
                            "required": True,
                            "default": "default_name"
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Required field with default should fail"
    assert any("required" in str(err).lower() and "default" in str(err).lower() for err in errors), \
        f"Should have required/default conflict error. Errors: {errors}"
