"""
Test for change ID reference constraints.

Must statements:
1. ../../changes[id = current()] (for c field)
2. ../../changes[id = current()] (for m field)
Location: entities/c and entities/m
"""
import pytest
from xyang import YangValidator, parse_yang_file
from pathlib import Path


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_change_id_c_reference_valid(meta_model):
    """Test that c field referencing valid change ID passes validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "consolidated": True,
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "id",
                    "c": 1,
                    "fields": [
                        {"name": "id", "type": "integer"}
                    ]
                }
            ],
            "changes": [
                {"id": 1, "timestamp": "2025-01-15T10:00:00Z"}
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"c field referencing valid change ID should pass. Errors: {errors}"


def test_change_id_m_reference_valid(meta_model):
    """Test that m field referencing valid change IDs passes validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "consolidated": True,
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "id",
                    "c": 1,
                    "m": [2, 3],
                    "fields": [
                        {"name": "id", "type": "integer"}
                    ]
                }
            ],
            "changes": [
                {"id": 1, "timestamp": "2025-01-15T10:00:00Z"},
                {"id": 2, "timestamp": "2025-01-16T10:00:00Z"},
                {"id": 3, "timestamp": "2025-01-17T10:00:00Z"}
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"m field referencing valid change IDs should pass. Errors: {errors}"


def test_change_id_c_reference_invalid(meta_model):
    """Test that c field referencing invalid change ID fails validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "consolidated": True,
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "id",
                    "c": 999,
                    "fields": [
                        {"name": "id", "type": "integer"}
                    ]
                }
            ],
            "changes": [
                {"id": 1, "timestamp": "2025-01-15T10:00:00Z"}
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "c field referencing invalid change ID should fail"
    assert any("change id" in str(err).lower() or "c must reference" in str(err).lower() for err in errors), \
        f"Should have change ID reference error. Errors: {errors}"


def test_change_id_m_reference_invalid(meta_model):
    """Test that m field referencing invalid change ID fails validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "consolidated": True,
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": "id",
                    "c": 1,
                    "m": [2, 999],
                    "fields": [
                        {"name": "id", "type": "integer"}
                    ]
                }
            ],
            "changes": [
                {"id": 1, "timestamp": "2025-01-15T10:00:00Z"},
                {"id": 2, "timestamp": "2025-01-16T10:00:00Z"}
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "m field referencing invalid change ID should fail"
    assert any("change id" in str(err).lower() or "m value must reference" in str(err).lower() for err in errors), \
        f"Should have change ID reference error. Errors: {errors}"
