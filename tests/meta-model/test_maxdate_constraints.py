"""
Test for maxDate constraints.

Must statements:
1. ../type = 'date' or ../type = 'datetime'
2. not(../minDate) or . >= ../minDate
Location: entities/fields/maxDate

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


def test_maxdate_valid_date_type(meta_model):
    """Test that maxDate with date type passes validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "enddate",
                            "type": "date",
                            "maxDate": "2020-12-31"
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"maxDate with date type should pass. Errors: {errors}"


def test_maxdate_valid_datetime_type(meta_model):
    """Test that maxDate with datetime type passes validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "enddatetime",
                            "type": "datetime",
                            "maxDate": "2020-12-31"
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"maxDate with datetime type should pass. Errors: {errors}"


def test_maxdate_valid_with_mindate(meta_model):
    """Test that maxDate >= minDate passes validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "daterange",
                            "type": "date",
                            "minDate": "2020-01-01",
                            "maxDate": "2020-12-31"
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"maxDate >= minDate should pass. Errors: {errors}"


def test_maxdate_invalid_wrong_type(meta_model):
    """Test that maxDate with non-date/datetime type fails validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "name",
                            "type": "string",
                            "maxDate": "2020-12-31"
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "maxDate with non-date/datetime type should fail"
    assert any("maxdate" in str(err).lower() and ("date" in str(err).lower() or "datetime" in str(err).lower()) for err in errors), \
        f"Should have maxDate type error. Errors: {errors}"


def test_maxdate_invalid_less_than_mindate(meta_model):
    """Test that maxDate < minDate fails validation."""
    validator = YangValidator(meta_model)
    
    data = {
        "data-model": {
            "name": "Test Model",
            "version": "25.01.27.1",
            "author": "Test",
            "entities": [
                {
                    "name": "entity1",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "integer"},
                        {
                            "name": "daterange",
                            "type": "date",
                            "minDate": "2020-12-31",
                            "maxDate": "2020-01-01"
                        }
                    ]
                }
            ]
        }
    }
    
    is_valid, errors, warnings = validator.validate(data)
    assert not is_valid, "maxDate < minDate should fail"
    assert any("maxdate" in str(err).lower() and "mindate" in str(err).lower() for err in errors), \
        f"Should have maxDate/minDate comparison error. Errors: {errors}"
