"""
Tests for when expression support.
"""

import pytest
from xYang import parse_yang_string, YangValidator
from tests.test_utils import create_context


def test_when_condition_true():
    """Test when condition that evaluates to true."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf type {
      type string;
    }
    container item_type {
      when "../type = 'array'";
      description "Only present when type is array";
      leaf primitive {
        type string;
      }
    }
  }
}
"""
    module = parse_yang_string(yang_content)

    # Find the container with when condition
    data_model = module.find_statement("data")
    assert data_model is not None

    item_type = None
    for stmt in data_model.statements:
        if hasattr(stmt, 'name') and stmt.name == 'item_type':
            item_type = stmt
            break

    assert item_type is not None
    assert item_type.when is not None
    assert item_type.when.condition == "../type = 'array'"

    # Test validation with when condition true
    validator = YangValidator(module)
    data = {
        "data": {
            "type": "array",
            "item_type": {
                "primitive": "string"
            }
        }
    }

    is_valid, errors, warnings = validator.validate(data)
    # Should be valid when condition is true
    assert is_valid or len(errors) == 0


def test_when_condition_false():
    """Test when condition that evaluates to false - container should be skipped."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf type {
      type string;
    }
    container item_type {
      when "../type = 'array'";
      description "Only present when type is array";
      leaf primitive {
        type string;
        mandatory true;
      }
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)

    # When condition is false, container should be skipped
    # Even if item_type is missing, it shouldn't cause validation errors
    data = {
        "data": {
            "type": "string"  # Not 'array', so when condition is false
        }
    }

    is_valid, errors, warnings = validator.validate(data)
    # Should be valid - when condition false means container is optional
    assert is_valid

    # When condition is false, item_type must not appear; if present it is invalid
    data_with_item_type = {
        "data": {
            "type": "string",
            "item_type": {
                "primitive": "string"
            }
        }
    }
    is_valid_extra, errors_extra, _ = validator.validate(data_with_item_type)
    assert not is_valid_extra, "item_type with type != 'array' should be invalid"
    assert any("item_type" in str(e).lower() for e in errors_extra)


def test_when_condition_empty_type_leaf():
    """Test when condition based on a leaf with type empty (presence/absence)."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf enabled {
      type empty;
      description "Flag leaf - no value, only presence";
    }
    container optional_section {
      when "../enabled";
      description "Only present when enabled (type empty) is present";
      leaf note {
        type string;
      }
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)

    # When enabled (empty leaf) is present, condition is true - optional_section valid
    # Empty type in data: key present with value None; when "../enabled" must evaluate true
    data_enabled = {
        "data": {
            "enabled": None,
            "optional_section": {
                "note": "enabled is set"
            }
        }
    }
    is_valid, errors, _ = validator.validate(data_enabled)
    assert is_valid, errors

    # When enabled is absent, condition is false - optional_section not in schema
    data_disabled = {
        "data": {}
    }
    is_valid, errors, _ = validator.validate(data_disabled)
    assert is_valid, errors

    # When enabled is absent but optional_section is present: invalid (unknown field)
    data_extra = {
        "data": {
            "optional_section": {"note": "ignored"}
        }
    }
    is_valid, errors, _ = validator.validate(data_extra)
    assert not is_valid
    assert any("optional_section" in e for e in errors)


def test_when_with_xpath_evaluator():
    """Test that when conditions use XPath evaluator."""
    from xYang import XPathEvaluator

    data = {
        "type": "array"
    }
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=["item_type"])

    # Test the when condition expression
    context = create_context(data, ["item_type"])
    result = evaluator.evaluate("../type = 'array'", context)
    assert result is True

    # Test with false condition
    data2 = {"type": "string"}
    evaluator2 = XPathEvaluator(data2, module, context_path=["item_type"])
    context2 = create_context(data2, ["item_type"])
    result2 = evaluator2.evaluate("../type = 'array'", context2)
    assert result2 is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
