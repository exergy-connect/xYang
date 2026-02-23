"""
Minimal test demonstrating the current() context issue in absolute path predicates.

The problem: When current() appears inside a predicate within an absolute path
expression like /data-model/entities[name = deref(current())/../foreignKey/entity],
the XPath evaluator may reset the context before entering the predicate, causing
current() to not refer to the original context node (the child_fk leaf).

Expected behavior:
- current() should refer to the child_fk leaf node (the context when must began)
- deref(current()) should resolve to the field name leaf node
- deref(current())/../foreignKey/entity should return the entity name string
- The predicate [name = "entity_name"] should match the entity

Actual behavior:
- current() context is lost/reset in absolute path predicates
- This causes the path expression approach to fail for entity lookups

Solution:
- Use nested deref() which preserves context through relative path navigation
"""
import pytest
from xYang import YangValidator, parse_yang_string


def _generate_yang_model(must_condition: str) -> str:
    """Generate minimal YANG model with parameterized must condition.
    
    Args:
        must_condition: The must constraint expression to use in the child_fk leaf
        
    Returns:
        YANG model string with the specified must condition
    """
    return f"""module minimal-test {{
  namespace "urn:test:minimal";
  prefix "mt";
  yang-version 1.1;

  container data-model {{
    leaf consolidated {{
      type boolean;
      default false;
    }}

    list entities {{
      key name;
      leaf name {{
        type string;
      }}

      list fields {{
        key name;
        leaf name {{
          type string;
        }}
        leaf type {{
          type string;
        }}
        container foreignKey {{
          presence "Foreign key is defined";
          leaf entity {{
            type leafref {{
              path "/data-model/entities/name";
              require-instance true;
            }}
            mandatory true;
          }}
          leaf field {{
            type leafref {{
              path "/data-model/entities/fields/name";
              require-instance true;
            }}
          }}
        }}
      }}

      list parents {{
        key child_fk;
        leaf child_fk {{
          type leafref {{
            path "../../fields/name";
            require-instance true;
          }}
          mandatory true;

          must "{must_condition}" {{
            error-message "Child foreign key field type must match parent primary key field type";
          }}
        }}
      }}
    }}
  }}
}}
"""


@pytest.fixture
def test_data():
    """Shared test data for both working and failing pattern tests."""
    return {
        "data-model": {
            "consolidated": True,
            "entities": [
                {
                    "name": "parent",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "string"}
                    ]
                },
                {
                    "name": "child",
                    "fields": [
                        {
                            "name": "parent_id",
                            "type": "string",
                            "foreignKey": {
                                "entity": "parent"
                            }
                        }
                    ],
                    "parents": [
                        {
                            "child_fk": "parent_id"
                        }
                    ]
                }
            ]
        }
    }


@pytest.fixture
def working_model():
    """Generate and parse YANG model with WORKING expression (nested deref)."""
    # WORKING: Type matching check using nested deref
    # If field is not present, default to primary_key
    must_condition = (
        "/data-model/consolidated = false() or " +
        "(deref(current())/../type = deref(deref(current())/../foreignKey/entity)/../fields[name = deref(current())/../foreignKey/field]/type or " +
        "(count(deref(current())/../foreignKey/field) = 0 and " +
        "deref(current())/../type = deref(deref(current())/../foreignKey/entity)/../fields[name = deref(deref(current())/../foreignKey/entity)/../primary_key]/type))"
    )
    yang_content = _generate_yang_model(must_condition)
    return parse_yang_string(yang_content)


@pytest.fixture
def failing_model():
    """Generate and parse YANG model with FAILING expression (absolute path with predicate)."""
    # FAILING: Type matching check using absolute path with predicate
    # If field is not present, default to primary_key
    must_condition = (
        "/data-model/consolidated = false() or " +
        "(deref(current())/../type = /data-model/entities[name = deref(current())/../foreignKey/entity]/fields[name = deref(current())/../foreignKey/field]/type or " +
        "(count(deref(current())/../foreignKey/field) = 0 and " +
        "deref(current())/../type = /data-model/entities[name = deref(current())/../foreignKey/entity]/fields[name = /data-model/entities[name = deref(current())/../foreignKey/entity]/primary_key]/type))"
    )
    yang_content = _generate_yang_model(must_condition)
    return parse_yang_string(yang_content)


def test_working_pattern_with_nested_deref(working_model, test_data):
    """Test that nested deref() pattern works correctly (preserves context)."""
    validator = YangValidator(working_model)
    is_valid, errors, warnings = validator.validate(test_data)
    
    print("\n=== WORKING Pattern: Nested deref() ===")
    print("Pattern: deref(deref(current())/../foreignKey/entity)/../fields[...]/type")
    print("  - current() = child_fk leaf (context preserved)")
    print("  - deref(current()) = field name leaf")
    print("  - deref(...)/../foreignKey/entity = entity leafref")
    print("  - deref(entity_leafref) = entity name leaf")
    print("  - Context preserved through relative path navigation")
    
    assert is_valid, f"Working pattern should pass. Errors: {errors}"
    print(f"\n✓ Validation PASSED - nested deref() pattern works correctly")


def test_failing_pattern_with_absolute_path(failing_model, test_data):
    """Test that absolute path with predicate should work but fails due to current() context lost.
    
    This test will FAIL (the test itself fails) because validation fails,
    demonstrating that the absolute path expression doesn't work correctly.
    """
    validator = YangValidator(failing_model)
    is_valid, errors, warnings = validator.validate(test_data)
    
    print("\n=== FAILING Pattern: Absolute path with predicate ===")
    print("Pattern: /data-model/entities[name = deref(current())/../foreignKey/entity]/fields[...]/type")
    print("  - The predicate [name = deref(current())/../foreignKey/entity] should:")
    print("    1. current() = child_fk leaf (context when must began)")
    print("    2. deref(current()) = field name leaf ('parent_id')")
    print("    3. deref(current())/../foreignKey/entity = entity name string ('parent')")
    print("    4. Predicate becomes [name = 'parent'] which should match")
    print("  - BUT: Absolute path /data-model/entities resets context to root")
    print("  - Predicate [name = ...] evaluated in new context")
    print("  - current() may not refer to original child_fk leaf")
    print("  - This causes deref(current()) to fail or return wrong value")
    
    print(f"\nValidation result: {'PASS' if is_valid else 'FAIL'}")
    if errors:
        print(f"\nError encountered (demonstrating the issue):")
        for err in errors:
            print(f"  - {err}")
    
    # Both tests assert the same thing: validation should pass
    # This test will fail because validation fails, demonstrating the bug
    assert is_valid, f"Failing pattern should pass but doesn't due to current() context issue. Errors: {errors}"
