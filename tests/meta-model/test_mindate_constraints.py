"""
Test for minDate constraints.

Must statements:
1. ../type = 'date' or ../type = 'datetime'
2. not(../maxDate) or . <= ../maxDate
Location: entities/fields/minDate

Note: Date comparison uses direct string comparison (not number()) since
date strings in YYYY-MM-DD format compare correctly lexicographically.
"""
import pytest
from xYang import YangValidator, parse_yang_file
from pathlib import Path


@pytest.fixture
def meta_model():
    """Load the meta-model YANG module."""
    yang_path = Path(__file__).parent.parent.parent / "examples" / "meta-model.yang"
    return parse_yang_file(str(yang_path))


def test_mindate_valid_date_type(meta_model):
    """Test that minDate with date type passes validation."""
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
                        {"name": "id", "type": "integer"},
                        {"name": "startdate", "type": "date", "minDate": "2020-01-01"}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"minDate with date type should pass. Errors: {errors}"


def test_mindate_valid_datetime_type(meta_model):
    """Test that minDate with datetime type passes validation."""
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
                        {"name": "id", "type": "integer"},
                        {"name": "startdatetime", "type": "datetime", "minDate": "2020-01-01"}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"minDate with datetime type should pass. Errors: {errors}"


def test_mindate_valid_with_maxdate(meta_model):
    """Test that minDate <= maxDate passes validation."""
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
                        {"name": "id", "type": "integer"},
                        {"name": "daterange", "type": "date", "minDate": "2020-01-01", "maxDate": "2020-12-31"}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"minDate <= maxDate should pass. Errors: {errors}"


def test_mindate_invalid_wrong_type(meta_model):
    """Test that minDate with non-date/datetime type fails validation."""
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
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "name", "type": "string", "minDate": "2020-01-01"}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "minDate with non-date/datetime type should fail"
    assert any("mindate" in str(err).lower() and ("date" in str(err).lower() or "datetime" in str(err).lower()) for err in errors), \
        f"Should have minDate type error. Errors: {errors}"


def test_mindate_invalid_greater_than_maxdate(meta_model):
    """Test that minDate > maxDate fails validation."""
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
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {"name": "daterange", "type": "date", "minDate": "2020-12-31", "maxDate": "2020-01-01"}
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "minDate > maxDate should fail"
    assert any("mindate" in str(err).lower() and "maxdate" in str(err).lower() for err in errors), \
        f"Should have minDate/maxDate comparison error. Errors: {errors}"
