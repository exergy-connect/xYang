"""
Test for computed field reference existence constraint.

Must statement: (not(../entity) and count(../../../../../fields[name = current()]) = 1) or (../entity and count(deref(../entity)/../fields[name = current()]) = 1)
Location: entities/fields/computed/fields/field
"""
import pytest
from xYang import YangValidator, parse_yang_file
from pathlib import Path


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_computed_field_reference_valid_same_entity(meta_model):
    """Test that computed field reference in same entity passes validation."""
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
                        {"name": "field1", "type": "integer"},
                        {"name": "field2", "type": "integer"},
                        {
                            "name": "sum",
                            "type": "integer",
                            "computed": {
                                "operation": "add",
                                "fields": [{"field": "field1"}, {"field": "field2"}]
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Computed field reference in same entity should pass. Errors: {errors}"


def test_computed_field_reference_valid_cross_entity(meta_model):
    """Test that computed field reference in different entity with foreign key passes."""
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
                        {"name": "value", "type": "integer"}
                    ]
                },
                {
                    "name": "entity2",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "entity1_id",
                            "type": "integer",
                            "foreignKeys": [{"entity": "entity1"}]
                        },
                        {
                            "name": "computed_value",
                            "type": "integer",
                            "computed": {
                                "operation": "add",
                                "fields": [
                                    {"field": "entity1_id"},
                                    {"entity": "entity1", "field": "value"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Computed field reference in different entity should pass. Errors: {errors}"


def test_computed_field_reference_invalid_same_entity_missing(meta_model):
    """Test that computed field reference to non-existent field in same entity fails."""
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
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "sum",
                            "type": "integer",
                            "computed": {
                                "operation": "add",
                                "fields": [{"field": "field1"}, {"field": "field2"}]
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Computed field reference to non-existent field should fail"
    assert any("computed field reference must exist" in str(err).lower() for err in errors), \
        f"Should have computed field reference error. Errors: {errors}"


def test_computed_field_reference_invalid_cross_entity_missing(meta_model):
    """Test that computed field reference to non-existent field in different entity fails."""
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
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"}
                    ]
                },
                {
                    "name": "entity2",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "entity1_id",
                            "type": "integer",
                            "foreignKeys": [{"entity": "entity1"}]
                        },
                        {
                            "name": "computed_value",
                            "type": "integer",
                            "computed": {
                                "operation": "add",
                                "fields": [
                                    {"field": "entity1_id"},
                                    {"entity": "entity1", "field": "value"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Computed field reference to non-existent field in different entity should fail"
    assert any("computed field reference must exist" in str(err).lower() for err in errors), \
        f"Should have computed field reference error. Errors: {errors}"
