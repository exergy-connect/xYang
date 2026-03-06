"""
Test for list key uniqueness.

YANG lists with a key statement require unique key values within the list.
Enforced by StructureValidator._validate_list.
"""
import pytest
from xYang import YangValidator, parse_yang_string


@pytest.fixture
def module_with_keyed_list():
    """Minimal YANG module with a list that has a key."""
    yang = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container root {
    list items {
      key name;
      leaf name {
        type string;
      }
      leaf value {
        type string;
      }
    }
  }
}
"""
    return parse_yang_string(yang)


def test_list_key_unique_valid(module_with_keyed_list):
    """List entries with unique key values pass validation."""
    validator = YangValidator(module_with_keyed_list)
    data = {
        "root": {
            "items": [
                {"name": "a", "value": "one"},
                {"name": "b", "value": "two"},
            ]
        }
    }
    is_valid, errors, _ = validator.validate(data)
    assert is_valid, f"Unique keys should pass. Errors: {errors}"


def test_list_key_duplicate_invalid(module_with_keyed_list):
    """List entries with duplicate key values fail validation."""
    validator = YangValidator(module_with_keyed_list)
    data = {
        "root": {
            "items": [
                {"name": "a", "value": "one"},
                {"name": "a", "value": "two"},
            ]
        }
    }
    is_valid, errors, _ = validator.validate(data)
    assert not is_valid, "Duplicate key values should fail"
    assert any("duplicate key" in str(err).lower() for err in errors), (
        f"Expected duplicate key error. Errors: {errors}"
    )


def test_list_key_duplicate_error_message(module_with_keyed_list):
    """Duplicate key error mentions list name and key."""
    validator = YangValidator(module_with_keyed_list)
    data = {"root": {"items": [{"name": "x", "value": "1"}, {"name": "x", "value": "2"}]}}
    is_valid, errors, _ = validator.validate(data)
    assert not is_valid
    err_str = " ".join(str(e) for e in errors).lower()
    assert "items" in err_str
    assert "name" in err_str
