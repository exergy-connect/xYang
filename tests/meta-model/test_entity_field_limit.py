"""
Test for entity field limit constraint.

Must statement: bool(../allow_unlimited_fields) = true() or count(fields[type != 'array']) <= 7
Location: entities
"""
import pytest
from xYang import YangValidator, parse_yang_file
from pathlib import Path


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_entity_field_limit_valid_within_limit(meta_model):
    """Test that entity with 7 or fewer non-array fields passes validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "field1", "type": "string"},
                        {"name": "field2", "type": "string"},
                        {"name": "field3", "type": "string"},
                        {"name": "field4", "type": "string"},
                        {"name": "field5", "type": "string"},
                        {"name": "field6", "type": "string"}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Entity with 7 non-array fields should pass. Errors: {errors}"


def test_entity_field_limit_valid_array_fields_excluded(meta_model):
    """Test that array fields are excluded from the count."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "field1", "type": "string"},
                        {"name": "field2", "type": "string"},
                        {"name": "field3", "type": "string"},
                        {"name": "field4", "type": "string"},
                        {"name": "field5", "type": "string"},
                        {"name": "field6", "type": "string"},
                        {"name": "children", "type": "array", "item_type": {"entity": "child"}}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Entity with 7 non-array fields plus array field should pass (array excluded). Errors: {errors}"


def test_entity_field_limit_valid_allow_unlimited_true(meta_model):
    """Test that entity with allow_unlimited_fields=true can exceed limit."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "allow_unlimited_fields": True,
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "field1", "type": "string"},
                        {"name": "field2", "type": "string"},
                        {"name": "field3", "type": "string"},
                        {"name": "field4", "type": "string"},
                        {"name": "field5", "type": "string"},
                        {"name": "field6", "type": "string"},
                        {"name": "field7", "type": "string"},
                        {"name": "field8", "type": "string"},
                        {"name": "field9", "type": "string"}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Entity with allow_unlimited_fields=true should pass. Errors: {errors}"


def test_entity_field_limit_invalid_exceeds_limit(meta_model):
    """Test that entity with more than 7 non-array fields fails validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "field1", "type": "string"},
                        {"name": "field2", "type": "string"},
                        {"name": "field3", "type": "string"},
                        {"name": "field4", "type": "string"},
                        {"name": "field5", "type": "string"},
                        {"name": "field6", "type": "string"},
                        {"name": "field7", "type": "string"},
                        {"name": "field8", "type": "string"}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Entity with more than 7 non-array fields should fail"
    assert any("7 non-array fields" in str(err) or "field limit" in str(err).lower() for err in errors), \
        f"Should have field limit error. Errors: {errors}"


def test_entity_field_limit_invalid_exceeds_limit_with_arrays(meta_model):
    """Test that array fields don't count but non-array fields still must be <= 7."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "field1", "type": "string"},
                        {"name": "field2", "type": "string"},
                        {"name": "field3", "type": "string"},
                        {"name": "field4", "type": "string"},
                        {"name": "field5", "type": "string"},
                        {"name": "field6", "type": "string"},
                        {"name": "field7", "type": "string"},
                        {"name": "field8", "type": "string"},
                        {"name": "children", "type": "array", "item_type": {"entity": "child"}}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Entity with 8 non-array fields should fail even with array fields"
    assert any("7 non-array fields" in str(err) or "field limit" in str(err).lower() for err in errors), \
        f"Should have field limit error. Errors: {errors}"
