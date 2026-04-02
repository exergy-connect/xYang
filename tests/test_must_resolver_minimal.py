"""
Minimal tests for must expressions evaluated by xpath_new ResolverVisitor.

Each test targets one failing pattern so resolver fixes can be validated in isolation.
"""

import pytest
from xyang import parse_yang_string, YangValidator


def test_primary_key_fields_name_equals_current():
    """Must ../fields[name = current()]: current() = the primary_key leaf value."""
    yang = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  container data {
    list entities {
      key name;
      leaf name { type string; }
      leaf primary_key {
        type string;
        must "../fields[name = current()]";
      }
      list fields {
        key name;
        leaf name { type string; }
      }
    }
  }
}
"""
    module = parse_yang_string(yang)
    validator = YangValidator(module)
    # primary_key "id" must match a field name in ../fields
    data = {
        "data": {
            "entities": [
                {
                    "name": "e1",
                    "primary_key": "id",
                    "fields": [{"name": "id"}, {"name": "other"}],
                }
            ]
        }
    }
    is_valid, errors, _ = validator.validate(data)
    assert is_valid, errors


def test_primary_key_fields_name_equals_current_invalid():
    """Must ../fields[name = current()] fails when no field matches."""
    yang = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  container data {
    list entities {
      key name;
      leaf name { type string; }
      leaf primary_key {
        type string;
        must "../fields[name = current()]";
      }
      list fields {
        key name;
        leaf name { type string; }
      }
    }
  }
}
"""
    module = parse_yang_string(yang)
    validator = YangValidator(module)
    data = {
        "data": {
            "entities": [
                {
                    "name": "e1",
                    "primary_key": "nonexistent",
                    "fields": [{"name": "id"}],
                }
            ]
        }
    }
    is_valid, errors, _ = validator.validate(data)
    assert not is_valid
    assert any("primary_key" in str(e).lower() for e in errors)


def test_must_boolean_current_equals_true():
    """Must boolean(current()) = true(): boolean() and current() on leaf."""
    yang = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  container data {
    leaf enabled {
      type boolean;
      must "boolean(current()) = true()";
    }
  }
}
"""
    module = parse_yang_string(yang)
    validator = YangValidator(module)
    data = {"data": {"enabled": "true"}}
    is_valid, errors, _ = validator.validate(data)
    assert is_valid, errors


def test_must_string_length_dot_gt_zero():
    """Must string-length(.) > 0: . is current node (leaf value)."""
    yang = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  container data {
    leaf name {
      type string;
      must "string-length(.) > 0";
    }
  }
}
"""
    module = parse_yang_string(yang)
    validator = YangValidator(module)
    data = {"data": {"name": "x"}}
    is_valid, errors, _ = validator.validate(data)
    assert is_valid, errors


def test_must_string_length_fails_empty():
    """Must string-length(.) > 0 fails for empty string."""
    yang = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  container data {
    leaf name {
      type string;
      must "string-length(.) > 0";
    }
  }
}
"""
    module = parse_yang_string(yang)
    validator = YangValidator(module)
    data = {"data": {"name": ""}}
    is_valid, errors, _ = validator.validate(data)
    assert not is_valid


def test_must_absolute_or_relative_list_item():
    """Must /data-model/consolidated = false() or type = 'test' or value != '' on list item."""
    yang = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  container data {
    list items {
      key id;
      leaf id { type string; }
      leaf type { type string; }
      leaf value { type string; }
      must "/data-model/consolidated = false() or type = 'test' or value != ''";
    }
  }
}
"""
    module = parse_yang_string(yang)
    validator = YangValidator(module)
    valid_data = {"data": {"items": [{"id": "1", "type": "test", "value": ""}]}}
    is_valid, errors, _ = validator.validate(valid_data)
    assert is_valid, errors
    invalid_data = {"data": {"items": [{"id": "2", "type": "other", "value": ""}]}}
    is_valid2, errors2, _ = validator.validate(invalid_data)
    assert not is_valid2, "Should fail when type != 'test' and value empty"
