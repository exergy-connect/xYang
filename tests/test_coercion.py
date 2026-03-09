"""
Tests for type-aware coercion in XPath comparisons.

- Numeric: string digits are coerced in comparisons (e.g. current() > 0).
- Boolean: current() returns raw data; string 'true'/'false' are not coerced
  to boolean in must, and bool(non-empty string) is true. Data is not modified.
"""

import pytest
from xyang import parse_yang_string, YangValidator


def test_boolean_coercion_string_true():
    """Test that string 'true' is coerced during XPath comparison."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    leaf enabled {
      type boolean;
      must "current() = true()";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    data = {"data": {"enabled": "true"}}
    is_valid, errors, warnings = validator.validate(data)
    
    # Data remains as string (coercion happens inline during comparison)
    assert isinstance(data["data"]["enabled"], str)
    assert data["data"]["enabled"] == "true"
    # But validation passes because coercion happens in comparison
    assert is_valid


def test_boolean_coercion_string_false():
    """Test that string 'false' in must: current() is raw value; != false() holds (string vs bool), so valid."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    leaf enabled {
      type boolean;
      must "current() != false()";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    data = {"data": {"enabled": "false"}}
    is_valid, errors, warnings = validator.validate(data)
    
    # Data remains as string
    assert isinstance(data["data"]["enabled"], str)
    assert data["data"]["enabled"] == "false"
    # current() returns string "false"; string != false() so must holds, validation passes
    assert is_valid


def test_boolean_coercion_with_bool_function():
    """Test bool(current()) in must: non-empty string is truthy, so both 'true' and 'false' pass."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    leaf enabled {
      type boolean;
      must "bool(current()) = true()";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    # String "true": bool("true") is truthy, must passes
    data1 = {"data": {"enabled": "true"}}
    is_valid1, errors1, warnings1 = validator.validate(data1)
    assert is_valid1, f"Expected valid, got errors: {errors1}"
    
    # String "false": bool("false") is truthy (non-empty string), must passes
    data2 = {"data": {"enabled": "false"}}
    is_valid2, errors2, warnings2 = validator.validate(data2)
    assert is_valid2, f"Expected valid (non-empty string is truthy), got errors: {errors2}"


def test_int32_coercion_string_digits():
    """Test that string digits are coerced during XPath comparison."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    leaf count {
      type int32;
      must "current() > 0";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    data = {"data": {"count": "123"}}
    is_valid, errors, warnings = validator.validate(data)
    
    # Data remains as string (coercion happens inline during comparison)
    assert isinstance(data["data"]["count"], str)
    assert data["data"]["count"] == "123"
    # But validation passes because coercion happens in comparison
    assert is_valid


def test_int32_coercion_negative_string():
    """Test that negative string numbers are coerced during XPath comparison."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    leaf count {
      type int32;
      must "current() > 0";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    data = {"data": {"count": "-5"}}
    is_valid, errors, warnings = validator.validate(data)
    
    # Data remains as string (coercion happens inline during comparison)
    assert isinstance(data["data"]["count"], str)
    assert data["data"]["count"] == "-5"
    # Validation fails because -5 <= 0 after coercion
    assert not is_valid


def test_int32_coercion_with_must_constraint():
    """Test that coerced int32 values work correctly in must constraints."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    leaf count {
      type int32;
      must "current() > 0";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    # Positive string should be coerced and pass
    data1 = {"data": {"count": "123"}}
    is_valid1, errors1, warnings1 = validator.validate(data1)
    assert is_valid1, f"Expected valid, got errors: {errors1}"
    
    # Negative string should be coerced and fail
    data2 = {"data": {"count": "-5"}}
    is_valid2, errors2, warnings2 = validator.validate(data2)
    assert not is_valid2, "Expected invalid (-5 <= 0)"


def test_boolean_already_typed():
    """Test that already-typed boolean values work correctly."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    leaf enabled {
      type boolean;
      must "current() = true()";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    data = {"data": {"enabled": True}}
    original_value = data["data"]["enabled"]
    is_valid, errors, warnings = validator.validate(data)
    
    assert is_valid
    # Value should remain unchanged (same object)
    assert data["data"]["enabled"] is original_value


def test_int32_already_typed():
    """Test that already-typed integer values work correctly."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    leaf count {
      type int32;
      must "current() > 0";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    data = {"data": {"count": 42}}
    original_value = data["data"]["count"]
    is_valid, errors, warnings = validator.validate(data)
    
    assert is_valid
    # Value should remain unchanged
    assert data["data"]["count"] == original_value


def test_leaf_list_boolean_coercion():
    """Test leaf-list must: current() is the whole list; non-empty list is truthy, so must passes."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    leaf-list flags {
      type boolean;
      must "current() = true()";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    data = {"data": {"flags": ["true", "false", "true"]}}
    is_valid, errors, warnings = validator.validate(data)
    
    # Data remains as strings
    assert all(isinstance(flag, str) for flag in data["data"]["flags"])
    assert data["data"]["flags"] == ["true", "false", "true"]
    # current() is the whole list; comparison with true() yields valid in this implementation
    assert is_valid


def test_leaf_list_int32_coercion():
    """Test that leaf-list int32 values are coerced during XPath comparison."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    leaf-list counts {
      type int32;
      must "current() > 0";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    data = {"data": {"counts": ["1", "2", "3"]}}
    is_valid, errors, warnings = validator.validate(data)
    
    # Data remains as strings (coercion happens inline during comparison)
    assert all(isinstance(count, str) for count in data["data"]["counts"])
    assert data["data"]["counts"] == ["1", "2", "3"]
    # But validation passes because coercion happens in comparison
    assert is_valid


def test_nested_container_coercion():
    """Test that coercion works in nested containers during XPath comparison."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    container inner {
      leaf enabled {
        type boolean;
        must "current() = true()";
      }
      leaf count {
        type int32;
        must "current() > 0";
      }
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    data = {
        "data": {
            "inner": {
                "enabled": "true",
                "count": "42"
            }
        }
    }
    is_valid, errors, warnings = validator.validate(data)
    
    # Data remains as strings (coercion happens inline during comparison)
    assert isinstance(data["data"]["inner"]["enabled"], str)
    assert data["data"]["inner"]["enabled"] == "true"
    assert isinstance(data["data"]["inner"]["count"], str)
    assert data["data"]["inner"]["count"] == "42"
    # But validation passes because coercion happens in comparison
    assert is_valid


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
