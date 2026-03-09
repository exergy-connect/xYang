"""
Tests for current() scoping in leaf-list must constraints.

Resolution 3: must on a leaf-list must evaluate per-element with current() 
bound to each value. This is distinct from must on a leaf (evaluated once) 
or on a list (evaluated once per list entry with context node being the entry).
"""

import pytest
from xyang import parse_yang_string, YangValidator


def test_leaf_list_current_single_constraint():
    """Test that current() is bound to each value in a leaf-list."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    leaf-list values {
      type int32;
      must "current() > 0";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    # Test 1: All valid values should pass
    data1 = {
        "data": {
            "values": [1, 5, 10, 50, 99]
        }
    }
    is_valid1, errors1, warnings1 = validator.validate(data1)
    assert is_valid1, f"Expected valid, got errors: {errors1}"
    assert len(errors1) == 0
    
    # Test 2: One invalid value (negative) should fail
    data2 = {
        "data": {
            "values": [1, 5, -1, 50, 99]  # -1 fails current() > 0
        }
    }
    is_valid2, errors2, warnings2 = validator.validate(data2)
    assert not is_valid2, "Expected invalid due to negative value"
    assert len(errors2) > 0
    # Error should reference the specific index
    assert any("values[2]" in str(e) or "values" in str(e) for e in errors2)
    
    # Test 3: Zero should fail
    data3 = {
        "data": {
            "values": [1, 5, 0, 50, 99]  # 0 fails current() > 0
        }
    }
    is_valid3, errors3, warnings3 = validator.validate(data3)
    assert not is_valid3, "Expected invalid due to zero value"
    assert len(errors3) > 0


def test_leaf_list_current_multiple_constraints():
    """Test that multiple must constraints work correctly with current() per-element."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    leaf-list scores {
      type int32;
      must "current() >= 0";
      must "current() <= 100";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    # Test 1: All valid scores should pass
    data1 = {
        "data": {
            "scores": [85, 90, 95, 100, 0]
        }
    }
    is_valid1, errors1, warnings1 = validator.validate(data1)
    assert is_valid1, f"Expected valid, got errors: {errors1}"
    assert len(errors1) == 0
    
    # Test 2: One score too low should fail
    data2 = {
        "data": {
            "scores": [85, -5, 95]  # -5 fails current() >= 0
        }
    }
    is_valid2, errors2, warnings2 = validator.validate(data2)
    assert not is_valid2, "Expected invalid due to negative score"
    assert len(errors2) > 0
    
    # Test 3: One score too high should fail
    data3 = {
        "data": {
            "scores": [85, 150, 95]  # 150 fails current() <= 100
        }
    }
    is_valid3, errors3, warnings3 = validator.validate(data3)
    assert not is_valid3, "Expected invalid due to score > 100"
    assert len(errors3) > 0


def test_leaf_list_current_with_relative_paths():
    """Test that current() works correctly with relative paths in leaf-list constraints."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    leaf min_value {
      type int32;
    }
    leaf-list values {
      type int32;
      must "current() >= ../min_value";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    # Test 1: All values >= min_value should pass
    data1 = {
        "data": {
            "min_value": 10,
            "values": [10, 15, 20, 25]
        }
    }
    is_valid1, errors1, warnings1 = validator.validate(data1)
    assert is_valid1, f"Expected valid, got errors: {errors1}"
    assert len(errors1) == 0
    
    # Test 2: One value < min_value should fail
    data2 = {
        "data": {
            "min_value": 10,
            "values": [10, 5, 20, 25]  # 5 fails current() >= ../min_value
        }
    }
    is_valid2, errors2, warnings2 = validator.validate(data2)
    assert not is_valid2, "Expected invalid due to value < min_value"
    assert len(errors2) > 0


def test_leaf_list_current_empty_list():
    """Test that empty leaf-list doesn't cause errors."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    leaf-list values {
      type int32;
      must "current() > 0";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    # Empty list should be valid (no values to validate)
    data = {
        "data": {
            "values": []
        }
    }
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Empty leaf-list should be valid, got errors: {errors}"
    assert len(errors) == 0


def test_leaf_list_current_single_value():
    """Test that current() works correctly with a single value in leaf-list."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    leaf-list values {
      type int32;
      must "current() > 0";
      must "current() < 100";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    # Test 1: Single valid value should pass
    data1 = {
        "data": {
            "values": [50]
        }
    }
    is_valid1, errors1, warnings1 = validator.validate(data1)
    assert is_valid1, f"Expected valid, got errors: {errors1}"
    assert len(errors1) == 0
    
    # Test 2: Single invalid value should fail
    data2 = {
        "data": {
            "values": [-1]  # Fails current() > 0
        }
    }
    is_valid2, errors2, warnings2 = validator.validate(data2)
    assert not is_valid2, "Expected invalid due to negative value"
    assert len(errors2) > 0


def test_leaf_list_current_vs_leaf_comparison():
    """Test that leaf-list current() scoping is distinct from leaf current() scoping."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  
  container data {
    leaf single_value {
      type int32;
      must "current() > 0";
    }
    leaf-list multiple_values {
      type int32;
      must "current() > 0";
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    
    # Test: Leaf evaluates once, leaf-list evaluates per-element
    data = {
        "data": {
            "single_value": 5,  # Valid, evaluated once
            "multiple_values": [1, -1, 3]  # -1 fails, evaluated per-element
        }
    }
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Expected invalid due to -1 in leaf-list"
    assert len(errors) > 0
    # Error should be about the leaf-list, not the leaf
    assert any("multiple_values" in str(e) for e in errors)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
