"""Test enum value validation.

This test validates that invalid enum values are caught during validation.
"""

import sys
from pathlib import Path

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
                "primary_key": ["id"],
                "fields": [
                    {"name": "id", "type": "integer"},
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
    
    assert not is_valid, "Should fail validation for invalid enum value"
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
                "primary_key": ["id"],
                "fields": [
                    {"name": "id", "type": "integer"},
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
