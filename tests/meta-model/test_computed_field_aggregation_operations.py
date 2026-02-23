"""
Test for computed field aggregation operations field count constraint.

Must statement: (operation != 'min' and operation != 'max') or count(fields) >= 2
Location: entities/fields/computed
"""
import pytest
from xYang import YangValidator, parse_yang_file
from pathlib import Path


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_computed_field_aggregation_operations_valid_minimum(meta_model):
    """Test that aggregation operations with exactly 2 fields pass validation."""
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
                            "name": "minimum",
                            "type": "integer",
                            "computed": {
                                "operation": "min",
                                "fields": [
                                    {"field": "field1"},
                                    {"field": "field2"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Aggregation operation with exactly 2 fields should pass. Errors: {errors}"


def test_computed_field_aggregation_operations_valid_multiple(meta_model):
    """Test that aggregation operations with more than 2 fields pass validation."""
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
                        {"name": "field3", "type": "integer"},
                        {
                            "name": "maximum",
                            "type": "integer",
                            "computed": {
                                "operation": "max",
                                "fields": [
                                    {"field": "field1"},
                                    {"field": "field2"},
                                    {"field": "field3"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Aggregation operation with multiple fields should pass. Errors: {errors}"


def test_computed_field_aggregation_operations_invalid_too_few(meta_model):
    """Test that aggregation operations with less than 2 fields fail validation."""
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
                        {"name": "field1", "type": "integer"},
                        {
                            "name": "minimum",
                            "type": "integer",
                            "computed": {
                                "operation": "min",
                                "fields": [
                                    {"field": "field1"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Aggregation operation with less than 2 fields should fail"
    assert any("at least 2 fields" in str(err).lower() or "aggregation operations" in str(err).lower() for err in errors), \
        f"Should have aggregation operation field count error. Errors: {errors}"
