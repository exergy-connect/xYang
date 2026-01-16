"""
Basic tests for xYang library.
"""

import pytest
from xYang import parse_yang_string, YangValidator, TypeSystem
from xYang.types import TypeConstraint


def test_parse_simple_module():
    """Test parsing a simple YANG module."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf name {
      type string;
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    assert module.name == "test"
    assert module.yang_version == "1.1"
    assert module.namespace == "urn:test"
    assert module.prefix == "t"


def test_parse_typedef():
    """Test parsing typedef."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  typedef entity-name {
    type string {
      length "1..64";
      pattern '[a-z_][a-z0-9_]*';
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    assert "entity-name" in module.typedefs
    typedef = module.typedefs["entity-name"]
    assert typedef.type is not None
    assert typedef.type.name == "string"


def test_type_validation():
    """Test type validation."""
    type_system = TypeSystem()

    # Test string validation
    is_valid, error = type_system.validate("test", "string")
    assert is_valid

    # Test int32 validation
    is_valid, error = type_system.validate(42, "int32")
    assert is_valid

    is_valid, error = type_system.validate(9999999999, "int32")
    assert not is_valid  # Out of range

    # Test uint8 validation
    is_valid, error = type_system.validate(255, "uint8")
    assert is_valid

    is_valid, error = type_system.validate(256, "uint8")
    assert not is_valid  # Out of range

    # Test boolean validation
    is_valid, error = type_system.validate(True, "boolean")
    assert is_valid

    is_valid, error = type_system.validate("true", "boolean")
    assert is_valid


def test_type_constraints():
    """Test type constraints."""
    type_system = TypeSystem()

    # Test pattern constraint
    constraint = TypeConstraint(pattern=r'[a-z_][a-z0-9_]*')
    is_valid, error = type_system.validate("valid_name", "string", constraint)
    assert is_valid

    is_valid, error = type_system.validate("InvalidName", "string", constraint)
    assert not is_valid

    # Test length constraint
    constraint = TypeConstraint(length="1..10")
    is_valid, error = type_system.validate("short", "string", constraint)
    assert is_valid

    is_valid, error = type_system.validate("this is too long", "string", constraint)
    assert not is_valid


def test_validate_simple_data():
    """Test data validation."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf name {
      type string;
      mandatory true;
    }
    leaf count {
      type uint8;
      default 0;
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)

    # Valid data
    valid_data = {
        "data": {
            "name": "test"
        }
    }
    is_valid, errors, warnings = validator.validate(valid_data)
    assert is_valid

    # Invalid data (missing mandatory)
    invalid_data = {
        "data": {
            "count": 5
        }
    }
    is_valid, errors, warnings = validator.validate(invalid_data)
    assert not is_valid
    assert len(errors) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
