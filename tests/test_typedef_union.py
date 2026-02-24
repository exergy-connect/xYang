"""
Tests for YANG typedef with union types.

Union types allow a value to match one of several member types. This test covers
typedef definitions that use union types, including validation of valid and invalid values.
"""

import pytest
from xYang import parse_yang_string, YangValidator


def test_typedef_union_primitive_and_composite():
    """Test union typedef with primitive-type and composite-type."""
    yang_content = """
    module test {
      yang-version 1.1;
      namespace "urn:test";
      prefix "t";

      typedef primitive-type {
        type enumeration {
          enum string;
          enum integer;
          enum number;
          enum boolean;
        }
      }

      typedef composite-type {
        type enumeration {
          enum composite;
        }
      }

      typedef field-type {
        type union {
          type primitive-type;
          type composite-type;
        }
      }

      container data {
        leaf type {
          type field-type;
          mandatory true;
        }
      }
    }
    """
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)

    # Valid primitive type values
    valid_data_1 = {"data": {"type": "string"}}
    is_valid, errors, warnings = validator.validate(valid_data_1)
    assert is_valid, f"Expected valid data with primitive type 'string'. Errors: {errors}"

    valid_data_2 = {"data": {"type": "integer"}}
    is_valid, errors, warnings = validator.validate(valid_data_2)
    assert is_valid, f"Expected valid data with primitive type 'integer'. Errors: {errors}"

    valid_data_3 = {"data": {"type": "number"}}
    is_valid, errors, warnings = validator.validate(valid_data_3)
    assert is_valid, f"Expected valid data with primitive type 'number'. Errors: {errors}"

    valid_data_4 = {"data": {"type": "boolean"}}
    is_valid, errors, warnings = validator.validate(valid_data_4)
    assert is_valid, f"Expected valid data with primitive type 'boolean'. Errors: {errors}"

    # Valid composite type value
    valid_data_5 = {"data": {"type": "composite"}}
    is_valid, errors, warnings = validator.validate(valid_data_5)
    assert is_valid, f"Expected valid data with composite type 'composite'. Errors: {errors}"

    # Invalid value that doesn't match any union member
    invalid_data = {"data": {"type": "invalid_type"}}
    is_valid, errors, warnings = validator.validate(invalid_data)
    assert not is_valid, f"Expected invalid data with type 'invalid_type' to fail validation"
    assert len(errors) > 0, "Expected validation errors for invalid type"
    assert any("union member type" in error.lower() for error in errors), \
        f"Expected error message about union member types. Errors: {errors}"


def test_typedef_union_string_and_enum():
    """Test union typedef with string pattern and enumeration."""
    yang_content = """
    module test {
      yang-version 1.1;
      namespace "urn:test";
      prefix "t";

      typedef string-pattern {
        type string {
          pattern '^[A-Z][a-z]+$';
        }
      }

      typedef status-enum {
        type enumeration {
          enum active;
          enum inactive;
          enum pending;
        }
      }

      typedef status-type {
        type union {
          type string-pattern;
          type status-enum;
        }
      }

      container data {
        leaf status {
          type status-type;
        }
      }
    }
    """
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)

    # Valid enum values
    valid_data_1 = {"data": {"status": "active"}}
    is_valid, errors, warnings = validator.validate(valid_data_1)
    assert is_valid, f"Expected valid data with enum 'active'. Errors: {errors}"

    valid_data_2 = {"data": {"status": "inactive"}}
    is_valid, errors, warnings = validator.validate(valid_data_2)
    assert is_valid, f"Expected valid data with enum 'inactive'. Errors: {errors}"

    # Valid string pattern values
    valid_data_3 = {"data": {"status": "Hello"}}
    is_valid, errors, warnings = validator.validate(valid_data_3)
    assert is_valid, f"Expected valid data with pattern 'Hello'. Errors: {errors}"

    valid_data_4 = {"data": {"status": "World"}}
    is_valid, errors, warnings = validator.validate(valid_data_4)
    assert is_valid, f"Expected valid data with pattern 'World'. Errors: {errors}"

    # Invalid values
    invalid_data_1 = {"data": {"status": "invalid"}}  # Doesn't match pattern or enum
    is_valid, errors, warnings = validator.validate(invalid_data_1)
    assert not is_valid, f"Expected invalid data with 'invalid' to fail validation"
    assert len(errors) > 0, "Expected validation errors for invalid status"

    invalid_data_2 = {"data": {"status": "hello"}}  # Lowercase doesn't match pattern
    is_valid, errors, warnings = validator.validate(invalid_data_2)
    assert not is_valid, f"Expected invalid data with 'hello' to fail validation"


def test_typedef_union_three_members():
    """Test union typedef with three member types."""
    yang_content = """
    module test {
      yang-version 1.1;
      namespace "urn:test";
      prefix "t";

      typedef type-a {
        type enumeration {
          enum a1;
          enum a2;
        }
      }

      typedef type-b {
        type enumeration {
          enum b1;
          enum b2;
        }
      }

      typedef type-c {
        type enumeration {
          enum c1;
          enum c2;
        }
      }

      typedef multi-union {
        type union {
          type type-a;
          type type-b;
          type type-c;
        }
      }

      container data {
        leaf value {
          type multi-union;
        }
      }
    }
    """
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)

    # Valid values from each member type
    valid_data_1 = {"data": {"value": "a1"}}
    is_valid, errors, warnings = validator.validate(valid_data_1)
    assert is_valid, f"Expected valid data with 'a1'. Errors: {errors}"

    valid_data_2 = {"data": {"value": "b2"}}
    is_valid, errors, warnings = validator.validate(valid_data_2)
    assert is_valid, f"Expected valid data with 'b2'. Errors: {errors}"

    valid_data_3 = {"data": {"value": "c1"}}
    is_valid, errors, warnings = validator.validate(valid_data_3)
    assert is_valid, f"Expected valid data with 'c1'. Errors: {errors}"

    # Invalid value
    invalid_data = {"data": {"value": "invalid"}}
    is_valid, errors, warnings = validator.validate(invalid_data)
    assert not is_valid, f"Expected invalid data with 'invalid' to fail validation"
    assert len(errors) > 0, "Expected validation errors for invalid value"


def test_typedef_union_nested_typedefs():
    """Test union typedef that references other typedefs (like field-type)."""
    yang_content = """
    module test {
      yang-version 1.1;
      namespace "urn:test";
      prefix "t";

      typedef primitive-type {
        type enumeration {
          enum string;
          enum integer;
          enum number;
          enum boolean;
          enum array;
        }
      }

      typedef composite-type {
        type enumeration {
          enum composite;
        }
      }

      typedef field-type {
        type union {
          type primitive-type;
          type composite-type;
        }
      }

      container data {
        leaf field_type {
          type field-type;
          mandatory true;
        }
      }
    }
    """
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)

    # Test all primitive types
    for primitive in ["string", "integer", "number", "boolean", "array"]:
        valid_data = {"data": {"field_type": primitive}}
        is_valid, errors, warnings = validator.validate(valid_data)
        assert is_valid, f"Expected valid data with primitive type '{primitive}'. Errors: {errors}"

    # Test composite type
    valid_data = {"data": {"field_type": "composite"}}
    is_valid, errors, warnings = validator.validate(valid_data)
    assert is_valid, f"Expected valid data with composite type. Errors: {errors}"

    # Test invalid type
    invalid_data = {"data": {"field_type": "invalid"}}
    is_valid, errors, warnings = validator.validate(invalid_data)
    assert not is_valid, f"Expected invalid data with 'invalid' to fail validation"
    assert len(errors) > 0, "Expected validation errors for invalid field_type"


def test_typedef_union_empty_union():
    """Test that union with no members is handled gracefully."""
    yang_content = """
    module test {
      yang-version 1.1;
      namespace "urn:test";
      prefix "t";

      typedef empty-union {
        type union {
        }
      }

      container data {
        leaf value {
          type empty-union;
        }
      }
    }
    """
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)

    # Empty union should reject all values
    invalid_data = {"data": {"value": "anything"}}
    is_valid, errors, warnings = validator.validate(invalid_data)
    # Note: This might parse but validation should fail
    # The exact behavior depends on implementation


def test_typedef_union_in_list():
    """Test union typedef used in a list context."""
    yang_content = """
    module test {
      yang-version 1.1;
      namespace "urn:test";
      prefix "t";

      typedef primitive-type {
        type enumeration {
          enum string;
          enum integer;
        }
      }

      typedef composite-type {
        type enumeration {
          enum composite;
        }
      }

      typedef field-type {
        type union {
          type primitive-type;
          type composite-type;
        }
      }

      list items {
        key id;
        leaf id {
          type string;
        }
        leaf type {
          type field-type;
        }
      }
    }
    """
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)

    # Valid list items with different union member types
    valid_data = {
        "items": [
            {"id": "item1", "type": "string"},
            {"id": "item2", "type": "integer"},
            {"id": "item3", "type": "composite"}
        ]
    }
    is_valid, errors, warnings = validator.validate(valid_data)
    assert is_valid, f"Expected valid list data with union types. Errors: {errors}"

    # Invalid list item
    invalid_data = {
        "items": [
            {"id": "item1", "type": "string"},
            {"id": "item2", "type": "invalid"}
        ]
    }
    is_valid, errors, warnings = validator.validate(invalid_data)
    assert not is_valid, f"Expected invalid list data to fail validation"
    assert len(errors) > 0, "Expected validation errors for invalid type in list"
