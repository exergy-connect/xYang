"""
Test minimal YANG model with parent relationship constraints.

This test demonstrates the must expressions that were failing and are now working:
1. Entity existence check (FIXED - using path expression)
2. Field existence check (FIXED - using path expression)
3. Primary key existence check (FIXED - using path expression)
4. FK references PK check (FIXED - using path expression)
5. Type matching check (WORKING - using nested deref)
6. Parent array existence check (WORKING - using nested deref)
7. Parent array type check (WORKING - using nested deref)
"""
import pytest
from xYang import YangValidator, parse_yang_file
from pathlib import Path


@pytest.fixture
def minimal_model():
    """Load the minimal test YANG module."""
    yang_path = Path(__file__).parent.parent / "examples" / "minimal-parents-test.yang"
    return parse_yang_file(str(yang_path))


def test_valid_parent_relationship(minimal_model):
    """Test that valid parent relationships pass all constraints."""
    validator = YangValidator(minimal_model)
    
    data = {
        "data-model": {
            "consolidated": True,
            "entities": [
                {
                    "name": "parent",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "string"},
                        {"name": "children", "type": "array"}
                    ]
                },
                {
                    "name": "child",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "string"},
                        {
                            "name": "parent_id",
                            "type": "string",
                            "foreignKey": {
                                "entity": "parent",
                                "field": "id"
                            }
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
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Valid parent relationship should pass. Errors: {errors}"


def test_invalid_entity_reference(minimal_model):
    """Test that invalid entity reference fails (Test 1)."""
    validator = YangValidator(minimal_model)
    
    data = {
        "data-model": {
            "consolidated": True,
            "entities": [
                {
                    "name": "child",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "string"},
                        {
                            "name": "parent_id",
                            "type": "string",
                            "foreignKey": {
                                "entity": "nonexistent",
                                "field": "id"
                            }
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
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Invalid entity reference should fail"
    assert any("entity must exist" in str(err).lower() for err in errors), \
        f"Should have entity existence error. Errors: {errors}"


def test_invalid_field_reference(minimal_model):
    """Test that invalid field reference fails (Test 2)."""
    validator = YangValidator(minimal_model)
    
    data = {
        "data-model": {
            "consolidated": True,
            "entities": [
                {
                    "name": "parent",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "string"}
                    ]
                },
                {
                    "name": "child",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "string"},
                        {
                            "name": "parent_id",
                            "type": "string",
                            "foreignKey": {
                                "entity": "parent",
                                "field": "nonexistent"
                            }
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
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Invalid field reference should fail"
    assert any("field must exist" in str(err).lower() for err in errors), \
        f"Should have field existence error. Errors: {errors}"


def test_invalid_type_mismatch(minimal_model):
    """Test that type mismatch fails (Test 5)."""
    validator = YangValidator(minimal_model)
    
    data = {
        "data-model": {
            "consolidated": True,
            "entities": [
                {
                    "name": "parent",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "children", "type": "array"}
                    ]
                },
                {
                    "name": "child",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "string"},
                        {
                            "name": "parent_id",
                            "type": "string",  # Mismatch: string vs integer
                            "foreignKey": {
                                "entity": "parent",
                                "field": "id"
                            }
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
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Type mismatch should fail"
    assert any("type must match" in str(err).lower() for err in errors), \
        f"Should have type matching error. Errors: {errors}"


def test_invalid_array_type(minimal_model):
    """Test that non-array parent_array fails (Test 7)."""
    validator = YangValidator(minimal_model)
    
    data = {
        "data-model": {
            "consolidated": True,
            "entities": [
                {
                    "name": "parent",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "string"},
                        {"name": "name", "type": "string"}  # Not an array
                    ]
                },
                {
                    "name": "child",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "string"},
                        {
                            "name": "parent_id",
                            "type": "string",
                            "foreignKey": {
                                "entity": "parent",
                                "field": "id"
                            }
                        }
                    ],
                    "parents": [
                        {
                            "child_fk": "parent_id",
                            "parent_array": "name"  # Not an array type
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Non-array parent_array should fail"
    assert any("array" in str(err).lower() and "type" in str(err).lower() for err in errors), \
        f"Should have array type error. Errors: {errors}"


def test_consolidated_false_skips_validation(minimal_model):
    """Test that consolidated=false skips Phase 2 validation."""
    validator = YangValidator(minimal_model)
    
    data = {
        "data-model": {
            "consolidated": False,  # Phase 1 - should skip cross-entity checks
            "entities": [
                {
                    "name": "child",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "string"},
                        {
                            "name": "parent_id",
                            "type": "string",
                            "foreignKey": {
                                "entity": "nonexistent",  # Would fail in Phase 2
                                "field": "id"
                            }
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
    }
    
    is_valid, errors, warnings = validator.validate(data)
    # Should pass because consolidated=false skips Phase 2 validation
    assert is_valid, \
        f"Phase 1 (consolidated=false) should skip cross-entity validation. Errors: {errors}"
