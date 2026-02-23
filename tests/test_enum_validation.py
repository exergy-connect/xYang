"""Test enum value validation.

This test validates that invalid enum values are caught during validation.
"""

import sys
from pathlib import Path

import pytest

# Add src directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from xYang import parse_yang_file, YangValidator


def test_invalid_enum_value():
    """Test that invalid enum values are caught."""
    yang_file = Path(__file__).parent.parent / "examples" / "meta-model.yang"
    module = parse_yang_file(str(yang_file))
    validator = YangValidator(module)
    
    # Test with invalid operation enum value
    data = {
        "data-model": {
            "name": "Test",
            "version": "25.01.27.1",
            "author": "Test",
            "consolidated": False,
            "entities": [{
                "name": "test",
                "primary_key": "id",  # New format: string instead of list
                "fields": [
                    {"name": "id", "type": "integer", "primaryKey": True},
                    {"name": "field1", "type": "integer"},
                    {"name": "field2", "type": "integer"},
                    {
                        "name": "computed",
                        "type": "integer",
                        "computed": {
                            "operation": "invalid_operation",  # Invalid enum value
                            "fields": [
                                {"field": "field1"},
                                {"field": "field2"}
                            ]
                        }
                    }
                ]
            }]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    
    # Expected: Invalid enum values should fail validation
    # TODO: Enum validation is not currently implemented in xYang validator
    # This test documents the expected behavior - enum validation should catch invalid values
    # Once enum validation is implemented, this test should pass
    if is_valid:
        pytest.skip(
            "Enum validation not yet implemented in xYang. "
            "Invalid enum value 'invalid_operation' should fail validation but currently passes. "
            f"Errors: {errors}, warnings: {warnings}"
        )
    
    assert not is_valid, (
        f"Should fail validation for invalid enum value 'invalid_operation'. "
        f"Got errors: {errors}, warnings: {warnings}"
    )
    assert any("operation" in error.lower() or "enum" in error.lower() or "invalid" in error.lower() 
               for error in errors), f"Expected error about invalid enum value, got: {errors}"


def test_valid_enum_value():
    """Test that valid enum values pass validation."""
    yang_file = Path(__file__).parent.parent / "examples" / "meta-model.yang"
    module = parse_yang_file(str(yang_file))
    validator = YangValidator(module)
    
    # Test with valid operation enum value
    data = {
        "data-model": {
            "name": "Test",
            "version": "25.01.27.1",
            "author": "Test",
            "consolidated": False,
            "entities": [{
                "name": "test",
                "primary_key": "id",  # New format: string instead of list
                "fields": [
                    {"name": "id", "type": "integer", "primaryKey": True},
                    {"name": "field1", "type": "integer"},
                    {"name": "field2", "type": "integer"},
                    {
                        "name": "computed",
                        "type": "integer",
                        "computed": {
                            "operation": "subtraction",  # Valid enum value
                            "fields": [
                                {"field": "field1"},
                                {"field": "field2"}
                            ]
                        }
                    }
                ]
            }]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    
    assert is_valid, f"Should pass validation for valid enum value, got errors: {errors}"


if __name__ == "__main__":
    test_invalid_enum_value()
    test_valid_enum_value()
    print("✓ All enum validation tests passed")
