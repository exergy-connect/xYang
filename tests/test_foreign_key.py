"""
Minimal test for foreign key validation issues in YANG must statements.

This test reproduces the foreign key validation errors seen in the consolidator,
specifically around:
- deref() path resolution
- Foreign key field existence validation
- Primary key reference validation
"""

import pytest
from xYang import parse_yang_string, YangValidator


def test_foreign_key_field_exists():
    """
    Test foreign key field must exist in referenced entity's fields.
    
    This test reproduces the foreign key validation issue where valid data
    fails validation because deref() path resolution doesn't correctly
    navigate to the referenced entity's fields.
    
    The issue: deref(../entity) should resolve to the entity node, then
    ../fields/field[name = current()] should navigate to that entity's fields,
    but the path resolution is not working correctly.
    """
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data-model {
    container entities {
      list entity {
        key "name";
        leaf name {
          type string;
        }
        container fields {
          list field {
            key "name";
            leaf name {
              type string;
            }
          }
        }
        leaf-list primary_key {
          type string;
        }
      }
    }
    container foreign-keys {
      list foreign-key {
        key "name";
        leaf name {
          type string;
        }
        leaf entity {
          type leafref {
            path "/data-model/entities/entity/name";
            require-instance true;
          }
          mandatory true;
        }
        leaf field {
          type leafref {
            path "/data-model/entities/entity/fields/field/name";
            require-instance true;
          }
          mandatory true;
          // Validate field exists in the specific entity
          must "deref(../entity)/../fields/field[name = current()]" {
            error-message "Foreign key field must exist in the referenced entity's fields";
          }
          // Validate field is in primary_key
          must "deref(../entity)/../primary_key[. = current()]" {
            error-message "Foreign key field must reference one of the parent entity's primary key fields";
          }
        }
      }
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)

    # Valid data: foreign key field exists in referenced entity and is a primary key
    valid_data = {
        "data-model": {
            "entities": {
                "entity": [
                    {
                        "name": "parent",
                        "fields": {
                            "field": [
                                {"name": "id"},
                                {"name": "name"}
                            ]
                        },
                        "primary_key": ["id"]
                    }
                ]
            },
            "foreign-keys": {
                "foreign-key": [
                    {
                        "name": "fk1",
                        "entity": "parent",
                        "field": "id"  # Valid: exists in fields and is in primary_key
                    }
                ]
            }
        }
    }
    is_valid, errors, warnings = validator.validate(valid_data)
    if not is_valid:
        print(f"Validation errors: {errors}")
        print(f"Warnings: {warnings}")
        print(f"Data structure: {valid_data}")
    # This test should pass once deref() path resolution is fixed
    # Expected: is_valid=True
    assert is_valid, f"Valid data should pass validation. Errors: {errors}"

    # Invalid data: foreign key field doesn't exist in referenced entity
    invalid_data1 = {
        "data-model": {
            "entities": {
                "entity": [
                    {
                        "name": "parent",
                        "fields": {
                            "field": [
                                {"name": "id"}
                            ]
                        },
                        "primary_key": ["id"]
                    }
                ]
            },
            "foreign-keys": {
                "foreign-key": [
                    {
                        "name": "fk1",
                        "entity": "parent",
                        "field": "nonexistent"  # Invalid: doesn't exist in fields
                    }
                ]
            }
        }
    }
    is_valid, errors, warnings = validator.validate(invalid_data1)
    assert not is_valid, "Invalid data (field doesn't exist) should fail validation"
    assert any("Foreign key field must exist" in str(e) for e in errors), \
        f"Should have foreign key field existence error. Errors: {errors}"

    # Invalid data: foreign key field exists but is not in primary_key
    invalid_data2 = {
        "data-model": {
            "entities": {
                "entity": [
                    {
                        "name": "parent",
                        "fields": {
                            "field": [
                                {"name": "id"},
                                {"name": "name"}
                            ]
                        },
                        "primary_key": ["id"]
                    }
                ]
            },
            "foreign-keys": {
                "foreign-key": [
                    {
                        "name": "fk1",
                        "entity": "parent",
                        "field": "name"  # Invalid: exists but not in primary_key
                    }
                ]
            }
        }
    }
    is_valid, errors, warnings = validator.validate(invalid_data2)
    assert not is_valid, "Invalid data (field not in primary_key) should fail validation"
    assert any("Foreign key field must reference one of the parent entity's primary key fields" in str(e) 
               for e in errors), \
        f"Should have primary key reference error. Errors: {errors}"


def test_foreign_key_with_missing_entity():
    """Test foreign key validation when referenced entity is missing."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data-model {
    container entities {
      list entity {
        key "name";
        leaf name {
          type string;
        }
        container fields {
          list field {
            key "name";
            leaf name {
              type string;
            }
          }
        }
        leaf-list primary_key {
          type string;
        }
      }
    }
    container foreign-keys {
      list foreign-key {
        key "name";
        leaf name {
          type string;
        }
        leaf entity {
          type leafref {
            path "/data-model/entities/entity/name";
            require-instance true;
          }
          mandatory true;
        }
        leaf field {
          type leafref {
            path "/data-model/entities/entity/fields/field/name";
            require-instance true;
          }
          mandatory true;
          must "deref(../entity)/../fields/field[name = current()]" {
            error-message "Foreign key field must exist in the referenced entity's fields";
          }
        }
      }
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)

    # Data with foreign key referencing non-existent entity
    invalid_data = {
        "data-model": {
            "entities": {
                "entity": [
                    {
                        "name": "parent",
                        "fields": {
                            "field": [
                                {"name": "id"}
                            ]
                        },
                        "primary_key": ["id"]
                    }
                ]
            },
            "foreign-keys": {
                "foreign-key": [
                    {
                        "name": "fk1",
                        "entity": "nonexistent",  # Entity doesn't exist
                        "field": "id"
                    }
                ]
            }
        }
    }
    is_valid, errors, warnings = validator.validate(invalid_data)
    # This should either fail validation or handle gracefully
    # The deref() should return None/empty for non-existent entity
    print(f"Validation result: is_valid={is_valid}, errors={errors}, warnings={warnings}")


def test_foreign_key_with_optional_field():
    """Test foreign key validation with optional field (should be lenient)."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data-model {
    container entities {
      list entity {
        key "name";
        leaf name {
          type string;
        }
        container fields {
          list field {
            key "name";
            leaf name {
              type string;
            }
          }
        }
        leaf-list primary_key {
          type string;
        }
      }
    }
    container foreign-keys {
      list foreign-key {
        key "name";
        leaf name {
          type string;
        }
        leaf entity {
          type leafref {
            path "/data-model/entities/entity/name";
            require-instance true;
          }
          mandatory false;  // Optional
        }
        leaf field {
          type leafref {
            path "/data-model/entities/entity/fields/field/name";
            require-instance true;
          }
          mandatory false;  // Optional
          must "deref(../entity)/../fields/field[name = current()]" {
            error-message "Foreign key field must exist in the referenced entity's fields";
          }
        }
      }
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)

    # Data with missing optional foreign key fields
    data_missing_optional = {
        "data-model": {
            "entities": {
                "entity": [
                    {
                        "name": "parent",
                        "fields": {
                            "field": [
                                {"name": "id"}
                            ]
                        },
                        "primary_key": ["id"]
                    }
                ]
            },
            "foreign-keys": {
                "foreign-key": [
                    {
                        "name": "fk1"
                        # entity and field are optional, so missing them should be OK
                    }
                ]
            }
        }
    }
    is_valid, errors, warnings = validator.validate(data_missing_optional)
    # Optional fields should not trigger must validation when missing
    print(f"Optional field test: is_valid={is_valid}, errors={errors}, warnings={warnings}")
    # This should pass validation since the fields are optional
    assert is_valid or not any("Foreign key field must exist" in str(e) for e in errors), \
        f"Optional fields should not trigger must validation. Errors: {errors}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
