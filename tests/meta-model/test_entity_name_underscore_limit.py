"""
Test for entity name underscore limit constraint.

Must statement: string-length(.) - string-length(translate(., '_', '')) <= ../../max_name_underscores
Location: entities/name

Note: The path ../../max_name_underscores goes up 2 levels from entities/name to data-model.
"""
import pytest
from pathlib import Path

from xyang import YangValidator, parse_yang_file


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_entity_name_underscore_limit_valid(meta_model):
    """Test that entity names within underscore limit pass validation."""
    validator = YangValidator(meta_model)
    
    # Valid: entity_name has 1 underscore (within default limit of 2)
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity_name",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Valid entity name should pass. Errors: {errors}"


def test_entity_name_underscore_limit_valid_at_limit(meta_model):
    """Test that entity names at the underscore limit pass validation."""
    validator = YangValidator(meta_model)
    
    # Valid: entity_field_name has 2 underscores (at default limit of 2)
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity_field_name",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Entity name at limit should pass. Errors: {errors}"


def test_entity_name_underscore_limit_valid_custom_limit(meta_model):
    """Test that entity names respect custom max_name_underscores."""
    validator = YangValidator(meta_model)
    
    # Valid: with max_name_underscores=3, entity_field_name_test has 3 underscores (at limit)
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "max_name_underscores": 3,
            "entities": [
                {
                    "name": "entity_field_name_test",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Entity name within custom limit should pass. Errors: {errors}"


def test_entity_name_underscore_limit_invalid_exceeds_default(meta_model):
    """Test that entity names exceeding default underscore limit fail validation."""
    validator = YangValidator(meta_model)
    
    # Invalid: entity_field_name_test has 3 underscores (exceeds default limit of 2)
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity_field_name_test",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Entity name exceeding default limit should fail"
    assert any("underscore limit" in str(err).lower() for err in errors), \
        f"Should have underscore limit error. Errors: {errors}"


def test_entity_name_underscore_limit_invalid_exceeds_custom(meta_model):
    """Test that entity names exceeding custom max_name_underscores fail validation."""
    validator = YangValidator(meta_model)
    
    # Invalid: with max_name_underscores=2, entity_field_name_test has 3 underscores (exceeds limit)
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity_field_name_test",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Entity name exceeding custom limit should fail"
    assert any("underscore limit" in str(err).lower() for err in errors), \
        f"Should have underscore limit error. Errors: {errors}"
