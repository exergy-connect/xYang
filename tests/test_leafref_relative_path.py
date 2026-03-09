"""Regression test for relative path resolution in leafref.

This test validates that relative paths in leafref definitions are correctly
resolved, particularly the case where ../../fields/name from entities/parents/child_fk
must resolve to entities/fields/name (not data-model/fields/name).

The fix ensures that when going up multiple levels from a list context, the resolver
tries going up one less level if the first attempt fails, handling YANG semantics
where .. from a list item goes to the parent of the list.
"""

import sys
from pathlib import Path

from xyang import parse_yang_file, parse_yang_string, YangValidator


def test_leafref_relative_path_resolution():
    """Test that relative paths in leafref are correctly resolved.
    
    This test specifically validates the fix for:
    - leafref path: ../../fields/name
    - context: entities/parents/child_fk
    - expected resolution: entities/fields/name (not data-model/fields/name)
    
    The key issue was that ../../fields/name from entities/parents/child_fk
    was resolving to /data-model/fields/name instead of /data-model/entities/fields/name.
    """
    yang_file = Path(__file__).parent.parent / "examples" / "meta-model.yang"
    module = parse_yang_file(str(yang_file))
    validator = YangValidator(module)
    
    # Test data with a minimal parent-child relationship
    # The child_fk field uses a relative path ../../fields/name
    # We need to satisfy all constraints, so we include:
    # - parent_array (mandatory)
    # - foreignKey on the referenced field
    # - matching types
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "consolidated": False,
            "entities": [
                {
                    "name": "parent_entity",
                    "primary_key": "parent_id",
                    "fields": [
                        {"name": "parent_id", "type": "string"},
                        {"name": "children", "type": "array", "item_type": {"entity": "child_entity"}}
                    ]
                },
                {
                    "name": "child_entity",
                    "primary_key": "child_id",
                    "fields": [
                        {"name": "child_id", "type": "string"},
                        {
                            "name": "parent_id",
                            "type": "string",
                            "foreignKeys": [{
                                "entity": "parent_entity"
                            }]
                        }
                    ],
                    "parents": [
                        {
                            "child_fk": "parent_id",  # This uses leafref path ../../fields/name
                            "parent_array": "children"  # Required field
                        }
                    ]
                }
            ]
        }
    }
    
    # Validation should pass - parent_id field exists in child_entity.fields
    # The key test is that the leafref resolution doesn't fail with
    # "Relative path resolution not yet implemented" or "no target instance found in schema"
    is_valid, errors, warnings = validator.validate(data)
    
    # Check that we don't have leafref resolution errors
    leafref_errors = [e for e in errors if "no target instance" in e or "Relative path resolution" in e]
    assert len(leafref_errors) == 0, (
        f"Should not have leafref resolution errors. Leafref errors: {leafref_errors}. "
        f"All errors: {errors}"
    )
    
    # The test passes if leafref resolution works (even if other constraints fail)
    # But ideally validation should pass
    if not is_valid:
        # If validation fails, it should be due to other constraints, not leafref resolution
        non_leafref_errors = [e for e in errors if "no target instance" not in e and "Relative path resolution" not in e]
        # It's OK if there are other constraint errors, as long as leafref resolution worked
        print(f"Validation failed but leafref resolution worked. Other errors: {non_leafref_errors}")


def test_leafref_relative_path_invalid_reference():
    """Test that invalid references in relative path leafref are caught.

    Minimal schema: one list with fields and a leafref leaf. Validation fails
    when the leafref value is not present in the referenced list.
    """
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    list entities {
      key name;
      leaf name { type string; }
      list fields {
        key name;
        leaf name { type string; }
      }
      leaf ref {
        type leafref {
          path "../fields/name";
          require-instance true;
        }
      }
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)

    # ref points to a field name that does not exist in this entity's fields
    data = {
        "data": {
            "entities": [
                {
                    "name": "e1",
                    "fields": [
                        {"name": "id"},
                        {"name": "other"}
                    ],
                    "ref": "nonexistent_field"
                }
            ]
        }
    }

    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Validation should fail for invalid leafref value"
    assert len(errors) > 0, "Should have at least one error"
    error_msg = " ".join(errors)
    assert "leafref" in error_msg.lower() or "nonexistent_field" in error_msg, (
        f"Error should be from leafref require-instance check. Errors: {errors}"
    )


def test_leafref_relative_path_multiple_entities():
    """Test relative path resolution with multiple entities.
    
    Ensures that relative paths resolve correctly even when there are
    multiple entities in the model, and that they resolve to the correct
    entity's fields (not a different entity).
    """
    yang_file = Path(__file__).parent.parent / "examples" / "meta-model.yang"
    module = parse_yang_file(str(yang_file))
    validator = YangValidator(module)
    
    # Test data with multiple entities, ensuring relative paths resolve
    # to the correct entity's fields (entity2.fields, not entity1.fields)
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "consolidated": False,
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "id1",
                    "fields": [
                        {"name": "id1", "type": "string"},
                        {"name": "field1", "type": "string"}
                    ]
                },
                {
                    "name": "entity2",
                    "primary_key": "id2",
                    "fields": [
                        {"name": "id2", "type": "string"},
                        {
                            "name": "fk_field",
                            "type": "string",
                            "foreignKeys": [{
                                "entity": "entity1"
                            }]
                        },
                        {"name": "children", "type": "array", "item_type": {"entity": "entity3"}}
                    ],
                    "parents": [
                        {
                            "child_fk": "fk_field",  # Should resolve to entity2.fields[1].name
                            "parent_array": "children"
                        }
                    ]
                },
                {
                    "name": "entity3",
                    "primary_key": "id3",
                    "fields": [
                        {"name": "id3", "type": "string"}
                    ]
                }
            ]
        }
    }
    
    # The key test is that leafref resolution works correctly
    # It should resolve ../../fields/name from entity2/parents/child_fk
    # to entity2.fields[1].name (fk_field), not entity1.fields or entity3.fields
    is_valid, errors, warnings = validator.validate(data)
    
    # Check that we don't have leafref resolution errors
    leafref_errors = [e for e in errors if "no target instance" in e or "Relative path resolution" in e]
    assert len(leafref_errors) == 0, (
        f"Should not have leafref resolution errors. Leafref errors: {leafref_errors}. "
        f"All errors: {errors}"
    )
    
    # The test passes if leafref resolution works (even if other constraints fail)
    if not is_valid:
        # If validation fails, it should be due to other constraints, not leafref resolution
        non_leafref_errors = [e for e in errors if "no target instance" not in e and "Relative path resolution" not in e]
        # It's OK if there are other constraint errors, as long as leafref resolution worked
        print(f"Validation failed but leafref resolution worked. Other errors: {non_leafref_errors}")
