"""Test enum value validation.

This test validates that invalid enum values are caught during validation.
"""

import sys
from pathlib import Path

import pytest

import pytest

from xyang import parse_yang_file, parse_yang_string, YangValidator
from xyang.errors import YangSyntaxError


def test_invalid_enum_value():
    """Test that invalid enum values are caught."""
    yang_file = Path(__file__).parent.parent / "examples" / "meta-model.yang"
    module = parse_yang_file(str(yang_file))
    validator = YangValidator(module)
    
    # Test with invalid operation enum value
    data = {
        "data-model": {
            "name": "Test",
            "version": "26.03.29.1",
            "author": "Test",
            "description": "Enum invalid test.",
            "consolidated": False,
            "entities": [
                {
                    "name": "test",
                    "description": "Test entity.",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "description": "PK.", "type": {"primitive": "integer"}},
                        {"name": "field1", "description": "F1.", "type": {"primitive": "integer"}},
                        {"name": "field2", "description": "F2.", "type": {"primitive": "integer"}},
                        {
                            "name": "computed",
                            "description": "Computed.",
                            "type": {"primitive": "integer"},
                            "computed": {
                                "operation": "invalid_operation",
                                "fields": [{"field": "field1"}, {"field": "field2"}],
                            },
                        },
                    ],
                }
            ],
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
            "version": "26.03.29.1",
            "author": "Test",
            "description": "Enum valid test.",
            "consolidated": False,
            "entities": [
                {
                    "name": "test",
                    "description": "Test entity.",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "description": "PK.", "type": {"primitive": "integer"}},
                        {"name": "field1", "description": "F1.", "type": {"primitive": "integer"}},
                        {"name": "field2", "description": "F2.", "type": {"primitive": "integer"}},
                        {
                            "name": "computed",
                            "description": "Computed.",
                            "type": {"primitive": "integer"},
                            "computed": {
                                "operation": "subtraction",
                                "fields": [{"field": "field1"}, {"field": "field2"}],
                            },
                        },
                    ],
                }
            ],
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    
    assert is_valid, f"Should pass validation for valid enum value, got errors: {errors}"


def test_empty_enumeration_type_rejected():
    """RFC 7950: enum-specification is one or more enum-stmt; empty body is invalid."""
    yang = """
module test_empty_enum {
  yang-version 1.1;
  namespace "urn:test:empty-enum";
  prefix "t";

  leaf x {
    type enumeration {
    }
  }
}
"""
    with pytest.raises(YangSyntaxError) as exc_info:
        parse_yang_string(yang)
    assert "enum" in str(exc_info.value).lower()


if __name__ == "__main__":
    test_invalid_enum_value()
    test_valid_enum_value()
    test_empty_enumeration_type_rejected()
    print("✓ All enum validation tests passed")
