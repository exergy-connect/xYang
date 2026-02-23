#!/usr/bin/env python3
"""
Libyang test for parents child_fk foreignKey definition constraint.

This test validates the constraint: deref(current())/../foreignKey
Location: entities/parents/child_fk

This is a libyang version of test_parents_child_fk_foreign_key_valid
to compare behavior between our XPath evaluator and libyang's implementation.
"""

import json
import sys
from pathlib import Path

try:
    import libyang
except ImportError:
    print("ERROR: libyang-python not installed. Install with: pip install libyang")
    sys.exit(1)


def test_constraint(ctx: libyang.Context, test_name: str, data: dict, should_fail: bool = False) -> bool:
    """Test a constraint with given data."""
    wrapped = {"meta-model:data-model": data}
    data_json = json.dumps(wrapped)
    
    try:
        tree = ctx.parse_data_mem(data_json, fmt="json", strict=True)
        tree.validate()
        tree.free()
        
        if should_fail:
            print(f"  ✗ {test_name}: Expected validation failure but passed")
            return False
        else:
            print(f"  ✓ {test_name}: Passed")
            return True
    except libyang.LibyangError as e:
        if should_fail:
            print(f"  ✓ {test_name}: Correctly failed")
            print(f"      Error: {str(e)[:150]}")
            return True
        else:
            print(f"  ✗ {test_name}: Unexpected failure")
            print(f"      Error: {str(e)[:150]}")
            return False
    except Exception as e:
        print(f"  ✗ {test_name}: Error - {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Test parents child_fk foreignKey constraint with libyang."""
    print("=== Testing Parents child_fk foreignKey Constraint with libyang ===\n")
    
    # Create context and load schema
    ctx = libyang.Context()
    yang_dir = Path(__file__).parent.parent.parent
    yang_file = yang_dir / "examples" / "meta-model.yang"
    
    if not yang_file.exists():
        print(f"ERROR: YANG file not found: {yang_file}")
        return 1
    
    try:
        with open(yang_file, 'r') as f:
            mod = ctx.parse_module_file(f, fmt="yang")
        print(f"✓ Loaded {yang_file.name}\n")
    except Exception as e:
        print(f"ERROR: Failed to load YANG file: {e}")
        return 1
    
    all_passed = True
    
    # Test 1: Valid - child_fk with foreignKey definition
    print("Test 1: Valid - child_fk with foreignKey definition")
    test1_data = {
        "name": "Test Model",
        "version": "25.01.27.1",
        "author": "Test",
        "max_name_underscores": 2,
        "entities": [
            {
                "name": "parent",
                "primary_key": "id",
                "fields": [
                    {"name": "id", "type": "integer", "primaryKey": True},
                    {
                        "name": "children",
                        "type": "array",
                        "item_type": {"entity": "child"}
                    }
                ]
            },
            {
                "name": "child",
                "primary_key": "id",
                "fields": [
                    {"name": "id", "type": "integer", "primaryKey": True},
                    {
                        "name": "parent_id",
                        "type": "integer",
                        "foreignKeys": [{
                            "entity": "parent"
                        }]
                ],
                "parents": [
                    {
                        "child_fk": "parent_id",
                        "parent_array": "children"
                    }
                ]
            }
        ]
    }
    all_passed &= test_constraint(ctx, "Valid - child_fk with foreignKey", test1_data, should_fail=False)
    
    # Test 2: Invalid - child_fk without foreignKey definition
    print("\nTest 2: Invalid - child_fk without foreignKey definition")
    test2_data = {
        "name": "Test Model",
        "version": "25.01.27.1",
        "author": "Test",
        "max_name_underscores": 2,
        "entities": [
            {
                "name": "parent",
                "primary_key": "id",
                "fields": [
                    {"name": "id", "type": "integer", "primaryKey": True},
                    {
                        "name": "children",
                        "type": "array",
                        "item_type": {"entity": "child"}
                    }
                ]
            },
            {
                "name": "child",
                "primary_key": "id",
                "fields": [
                    {"name": "id", "type": "integer", "primaryKey": True},
                    {
                        "name": "parent_id",
                        "type": "integer"
                        # Missing foreignKey
                    }
                ],
                "parents": [
                    {
                        "child_fk": "parent_id",
                        "parent_array": "children"
                    }
                ]
            }
        ]
    }
    all_passed &= test_constraint(ctx, "Invalid - missing foreignKey", test2_data, should_fail=True)
    
    ctx.destroy()
    
    if all_passed:
        print("\n=== All libyang constraint tests passed ===")
        return 0
    else:
        print("\n=== Some libyang constraint tests failed ===")
        return 1


if __name__ == "__main__":
    sys.exit(main())
