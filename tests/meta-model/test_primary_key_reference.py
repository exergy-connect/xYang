"""
Test for primary key reference constraint.

Must statement: ../fields[name = current()]
Location: entities/primary_key
"""
import pytest
from xYang import YangValidator, parse_yang_file
from pathlib import Path


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_primary_key_reference_valid(meta_model):
    """Test that primary key referencing existing field passes validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "id",
                    "fields": [
                        {"name": "id", "type": "integer"}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Primary key referencing existing field should pass. Errors: {errors}"


def test_primary_key_reference_valid_multiple(meta_model):
    """Test that composite primary key field referencing existing subcomponents passes."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "composite_key",
                    "fields": [
                        {
                            "name": "composite_key",
                            "type": "composite",
                            "composite": [
                                {"name": "id", "type": "integer"}
                            ]
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Composite primary key referencing existing subcomponents should pass. Errors: {errors}"


def test_primary_key_reference_invalid_missing_field(meta_model):
    """Test that primary key referencing non-existent field fails validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "nonexistent",
                    "fields": [
                        {"name": "id", "type": "integer"}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Primary key referencing non-existent field should fail"
    assert any("primary_key" in str(err).lower() or "field" in str(err).lower() for err in errors), \
        f"Should have primary key reference error. Errors: {errors}"


def test_primary_key_reference_invalid_partial(meta_model):
    """Test that primary key referencing non-existent composite field fails."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "nonexistent_composite",
                    "fields": [
                        {"name": "id", "type": "integer"}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "Primary key referencing non-existent composite field should fail"
    assert any("primary_key" in str(err).lower() or "field" in str(err).lower() for err in errors), \
        f"Should have primary key reference error. Errors: {errors}"
