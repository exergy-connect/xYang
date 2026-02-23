"""Tests for must constraints on lists containing leafref types.

This test validates that must constraints work correctly when applied to
list statements that contain leafref leaf types. The must constraint should
be evaluated for each list item, with current() referring to the list item.
"""

import sys
from pathlib import Path

# Add src directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from xYang import parse_yang_file, YangValidator, parse_yang_string


def test_must_on_list_with_leafref_valid():
    """Test that must constraint on a list with leafref works correctly when valid.
    
    This test uses a simple model where a list contains leafref types,
    and the list has a must constraint that validates the leafref values.
    """
    yang_model = """module test-must-leafref-list {
  namespace "urn:test:must-leafref-list";
  prefix "tml";
  yang-version 1.1;

  container data {
    list items {
      key id;
      leaf id {
        type string;
      }
      leaf name {
        type string;
      }
      
      must "name = /data/items[id = current()/id]/name" {
        error-message "Item name must match its own name";
        description "This constraint should always pass for valid data";
      }
    }
    
    list references {
      key ref_id;
      leaf ref_id {
        type leafref {
          path "/data/items/id";
          require-instance true;
        }
      }
      leaf ref_name {
        type leafref {
          path "/data/items[name = current()/../ref_id]/name";
          require-instance true;
        }
      }
      
      must "ref_name = /data/items[id = current()/ref_id]/name" {
        error-message "Referenced name must match the referenced item's name";
        description "Validates that ref_name matches the name of the item referenced by ref_id";
      }
    }
  }
}
"""
    
    module = parse_yang_string(yang_model)
    validator = YangValidator(module)
    
    # Valid data: ref_name matches the name of the item referenced by ref_id
    data = {
        "data": {
            "items": [
                {"id": "item1", "name": "Item One"},
                {"id": "item2", "name": "Item Two"}
            ],
            "references": [
                {"ref_id": "item1", "ref_name": "Item One"},
                {"ref_id": "item2", "ref_name": "Item Two"}
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Valid data should pass. Errors: {errors}"
    assert len(errors) == 0, f"Should have no errors. Errors: {errors}"


def test_must_on_list_with_leafref_invalid():
    """Test that must constraint on a list with leafref fails when invalid.
    
    This test validates that must constraints on lists with leafref correctly
    fail when the constraint condition is not met.
    """
    yang_model = """module test-must-leafref-list {
  namespace "urn:test:must-leafref-list";
  prefix "tml";
  yang-version 1.1;

  container data {
    list items {
      key id;
      leaf id {
        type string;
      }
      leaf name {
        type string;
      }
    }
    
    list references {
      key ref_id;
      leaf ref_id {
        type leafref {
          path "/data/items/id";
          require-instance true;
        }
      }
      leaf ref_name {
        type leafref {
          path "/data/items/name";
          require-instance true;
        }
      }
      
      must "ref_name = /data/items[id = current()/ref_id]/name" {
        error-message "Referenced name must match the referenced item's name";
        description "Validates that ref_name matches the name of the item referenced by ref_id";
      }
    }
  }
}
"""
    
    module = parse_yang_string(yang_model)
    validator = YangValidator(module)
    
    # Invalid data: ref_name does not match the name of the item referenced by ref_id
    data = {
        "data": {
            "items": [
                {"id": "item1", "name": "Item One"},
                {"id": "item2", "name": "Item Two"}
            ],
            "references": [
                {"ref_id": "item1", "ref_name": "Item Two"}  # Wrong name for item1
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Invalid data should fail validation"
    assert len(errors) > 0, "Should have errors for invalid constraint"
    assert any("Referenced name must match" in err for err in errors), \
        f"Error should mention the constraint. Errors: {errors}"


def test_must_on_foreignkeys_list_valid():
    """Test must constraint on foreignKeys list (from meta-model) with valid data.
    
    This test validates that must constraints on the foreignKeys list work correctly
    when the foreign key correctly references the primary key.
    """
    yang_file = Path(__file__).parent.parent / "examples" / "meta-model.yang"
    module = parse_yang_file(str(yang_file))
    validator = YangValidator(module)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "consolidated": True,
            "entities": [
                {
                    "name": "parent",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "name", "type": "string"}
                    ]
                },
                {
                    "name": "child",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "parent_id",
                            "type": "integer",
                            "foreignKeys": [
                                {
                                    "entity": "parent"  # field omitted, defaults to primary key
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Valid foreign key reference should pass. Errors: {errors}"


def test_must_on_foreignkeys_list_invalid():
    """Test must constraint on foreignKeys list (from meta-model) with invalid data.
    
    This test validates that must constraints on the foreignKeys list correctly
    fail when the foreign key references a non-primary key field.
    """
    yang_file = Path(__file__).parent.parent / "examples" / "meta-model.yang"
    module = parse_yang_file(str(yang_file))
    validator = YangValidator(module)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "consolidated": True,
            "entities": [
                {
                    "name": "parent",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "name", "type": "string"}
                    ]
                },
                {
                    "name": "child",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "parent_name",
                            "type": "string",
                            "foreignKeys": [
                                {
                                    "entity": "parent",
                                    "field": "name"  # Invalid: references non-primary key
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Foreign key referencing non-primary key should fail"
    assert any("primary key" in err.lower() for err in errors), \
        f"Error should mention primary key. Errors: {errors}"


def test_must_on_list_with_leafref_current_context():
    """Test that current() in must constraint on list refers to the list item.
    
    This test validates that when a must constraint is evaluated on a list item,
    current() correctly refers to the list item context, allowing access to
    sibling leafref values within the same list item.
    """
    yang_model = """module test-must-leafref-current {
  namespace "urn:test:must-leafref-current";
  prefix "tmc";
  yang-version 1.1;

  container data {
    list source {
      key id;
      leaf id {
        type string;
      }
      leaf value {
        type string;
      }
    }
    
    list target {
      key target_id;
      leaf target_id {
        type leafref {
          path "/data/source/id";
          require-instance true;
        }
      }
      leaf source_value {
        type leafref {
          path "/data/source/value";
          require-instance true;
        }
      }
      
      must "source_value = /data/source[id = current()/target_id]/value" {
        error-message "source_value must match the value of the source referenced by target_id";
        description "Validates that source_value matches the value of the source item referenced by target_id. current() should refer to the target list item.";
      }
    }
  }
}
"""
    
    module = parse_yang_string(yang_model)
    validator = YangValidator(module)
    
    # Valid data: source_value matches the value of the source referenced by target_id
    data = {
        "data": {
            "source": [
                {"id": "s1", "value": "value1"},
                {"id": "s2", "value": "value2"}
            ],
            "target": [
                {"target_id": "s1", "source_value": "value1"},
                {"target_id": "s2", "source_value": "value2"}
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Valid data should pass. Errors: {errors}"
    
    # Invalid data: source_value does not match
    invalid_data = {
        "data": {
            "source": [
                {"id": "s1", "value": "value1"},
                {"id": "s2", "value": "value2"}
            ],
            "target": [
                {"target_id": "s1", "source_value": "value2"}  # Wrong value
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(invalid_data)
    assert not is_valid, "Invalid data should fail"
    assert any("source_value must match" in err for err in errors), \
        f"Error should mention the constraint. Errors: {errors}"
