"""
Basic tests for xYang library (using xyang package).
"""

import pytest

from xyang import parse_yang_string, YangValidator, TypeSystem, TypeConstraint


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


def test_parse_block_comments():
    """Block comments /* ... */ are stripped; /* inside strings is preserved."""
    yang_content = """
module test {
  /* single-line block comment */
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  /*
   * multi-line
   * block comment
   */
  container data {
    leaf name {
      type string;
      description "path /* not a comment */ here";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    assert module.name == "test"
    assert module.yang_version == "1.1"
    # Description string must still contain the literal /* ... */ (not stripped as comment)
    data = module.find_statement("data")
    assert data is not None
    name_leaf = data.find_statement("name")
    assert name_leaf is not None
    assert name_leaf.description and "/* not a comment */" in name_leaf.description


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


def test_parse_ordered_by_accepted_on_list_and_leaf_list():
    """ordered-by user|system is parsed and ignored (no ordering semantics in xYang)."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    list items {
      key "name";
      ordered-by user;
      leaf name {
        type string;
      }
    }
    leaf-list tags {
      type string;
      ordered-by system;
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    data = module.find_statement("data")
    assert data is not None
    assert data.find_statement("items") is not None
    assert data.find_statement("tags") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
