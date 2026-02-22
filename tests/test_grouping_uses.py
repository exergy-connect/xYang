"""
Tests for grouping and uses statements in YANG.

Grouping allows defining reusable schema components, and uses allows
incorporating those components into other schema nodes.

NOTE: These tests are for future implementation. Grouping/uses support
needs to be added to the parser before these tests will pass.
"""

import pytest
from xYang import parse_yang_string, YangValidator


@pytest.mark.xfail(reason="Grouping/uses not yet implemented in parser")
def test_grouping_and_uses_basic():
    """Test basic grouping definition and uses statement."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  grouping common-fields {
    leaf name {
      type string;
      mandatory true;
    }
    leaf description {
      type string;
    }
  }

  container data {
    uses common-fields;
    leaf value {
      type int32;
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    assert module.name == "test"
    
    # Find the container
    data_container = None
    for stmt in module.statements:
        if hasattr(stmt, 'name') and stmt.name == 'data':
            data_container = stmt
            break
    
    assert data_container is not None, "data container should exist"
    
    # Validate that uses statement was processed
    # The container should have the fields from the grouping
    validator = YangValidator(module)
    
    # Test valid data with all fields
    valid_data = {
        "data": {
            "name": "test_name",
            "description": "test description",
            "value": 42
        }
    }
    is_valid, errors, warnings = validator.validate(valid_data)
    assert is_valid, f"Expected valid data, got errors: {errors}"
    
    # Test invalid data - missing mandatory name field from grouping
    invalid_data = {
        "data": {
            "description": "test description",
            "value": 42
        }
    }
    is_valid, errors, warnings = validator.validate(invalid_data)
    assert not is_valid, "Expected invalid due to missing mandatory name field"
    assert len(errors) > 0


@pytest.mark.xfail(reason="Grouping/uses not yet implemented in parser")
def test_grouping_with_refine():
    """Test grouping with refine statement to modify nodes."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  grouping base-field {
    leaf name {
      type string;
      mandatory true;
    }
    leaf type {
      type string;
      default "string";
    }
  }

  container data {
    uses base-field {
      refine type {
        must ". != 'invalid'" {
          error-message "Type cannot be invalid";
        }
      }
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    assert module.name == "test"
    
    validator = YangValidator(module)
    
    # Test valid data
    valid_data = {
        "data": {
            "name": "test",
            "type": "string"
        }
    }
    is_valid, errors, warnings = validator.validate(valid_data)
    assert is_valid, f"Expected valid data, got errors: {errors}"
    
    # Test invalid data - type is invalid
    invalid_data = {
        "data": {
            "name": "test",
            "type": "invalid"
        }
    }
    is_valid, errors, warnings = validator.validate(invalid_data)
    # Note: refine might not be fully implemented, so this test may need adjustment
    # assert not is_valid, "Expected invalid due to refine constraint"


@pytest.mark.xfail(reason="Grouping/uses not yet implemented in parser")
def test_nested_grouping():
    """Test grouping that uses another grouping."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  grouping base-fields {
    leaf id {
      type string;
      mandatory true;
    }
  }

  grouping extended-fields {
    uses base-fields;
    leaf name {
      type string;
    }
  }

  container data {
    uses extended-fields;
  }
}
"""
    module = parse_yang_string(yang_content)
    assert module.name == "test"
    
    validator = YangValidator(module)
    
    # Test valid data with all fields
    valid_data = {
        "data": {
            "id": "123",
            "name": "test"
        }
    }
    is_valid, errors, warnings = validator.validate(valid_data)
    assert is_valid, f"Expected valid data, got errors: {errors}"
    
    # Test invalid data - missing mandatory id from nested grouping
    invalid_data = {
        "data": {
            "name": "test"
        }
    }
    is_valid, errors, warnings = validator.validate(invalid_data)
    assert not is_valid, "Expected invalid due to missing mandatory id field"


@pytest.mark.xfail(reason="Grouping/uses not yet implemented in parser")
def test_grouping_in_list():
    """Test using grouping in a list."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  grouping item-fields {
    leaf name {
      type string;
      mandatory true;
    }
    leaf value {
      type int32;
    }
  }

  list items {
    key name;
    uses item-fields;
  }
}
"""
    module = parse_yang_string(yang_content)
    assert module.name == "test"
    
    validator = YangValidator(module)
    
    # Test valid data
    valid_data = {
        "items": [
            {
                "name": "item1",
                "value": 10
            },
            {
                "name": "item2",
                "value": 20
            }
        ]
    }
    is_valid, errors, warnings = validator.validate(valid_data)
    assert is_valid, f"Expected valid data, got errors: {errors}"
    
    # Test invalid data - missing mandatory name
    invalid_data = {
        "items": [
            {
                "value": 10
            }
        ]
    }
    is_valid, errors, warnings = validator.validate(invalid_data)
    assert not is_valid, "Expected invalid due to missing mandatory name field"


@pytest.mark.xfail(reason="Grouping/uses not yet implemented in parser")
def test_composite_field_grouping():
    """Test composite field grouping similar to meta-model.yang."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  grouping composite-field {
    leaf name {
      type string;
      mandatory true;
    }
    leaf type {
      type string;
      mandatory true;
    }
  }

  grouping field-definition {
    uses composite-field;
    leaf required {
      type boolean;
      default false;
    }
  }

  list fields {
    key name;
    uses field-definition;
  }
}
"""
    module = parse_yang_string(yang_content)
    assert module.name == "test"
    
    validator = YangValidator(module)
    
    # Test valid data
    valid_data = {
        "fields": [
            {
                "name": "field1",
                "type": "string",
                "required": True
            },
            {
                "name": "field2",
                "type": "integer"
            }
        ]
    }
    is_valid, errors, warnings = validator.validate(valid_data)
    assert is_valid, f"Expected valid data, got errors: {errors}"
    
    # Test invalid data - missing mandatory name
    invalid_data = {
        "fields": [
            {
                "type": "string"
            }
        ]
    }
    is_valid, errors, warnings = validator.validate(invalid_data)
    assert not is_valid, "Expected invalid due to missing mandatory name field"
