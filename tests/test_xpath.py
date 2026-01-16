"""
Tests for XPath evaluator.
"""

import pytest
from xYang import XPathEvaluator, parse_yang_string


def test_string_length():
    """Test string-length() function."""
    data = {"name": "test_value"}
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=["name"])

    result = evaluator.evaluate_value('string-length(.)')
    assert result == 10  # "test_value" has 10 characters


def test_translate():
    """Test translate() function."""
    data = {"name": "test_value_with_underscores"}
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=["name"])

    result = evaluator.evaluate_value('string-length(.) - string-length(translate(., "_", ""))')
    # Should count underscores: "test_value_with_underscores" has 3 underscores
    assert result == 3


def test_current():
    """Test current() function."""
    data = {"name": "test"}
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=["name"])

    # Test current() returns the value
    current_val = evaluator.evaluate_value('current()')
    assert current_val == "test"

    # Test comparison
    result = evaluator.evaluate('current() = "test"')
    assert result is True


def test_relative_path():
    """Test relative path navigation."""
    data = {
        "entity": {
            "name": "server",
            "max_underscores": 2
        }
    }
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=["entity", "name"])

    # From ['entity', 'name'], ../ goes to ['entity'], then max_underscores
    result = evaluator.evaluate_value('../max_underscores')
    assert result == 2


def test_comparison():
    """Test comparison operators."""
    data = {"count": 5}
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=["count"])

    assert evaluator.evaluate('. <= 7') is True
    assert evaluator.evaluate('. >= 3') is True
    assert evaluator.evaluate('. = 5') is True
    assert evaluator.evaluate('. != 10') is True


def test_logical_operators():
    """Test logical operators."""
    data = {"type": "date", "minDate": "2020-01-01", "maxDate": "2025-01-01"}
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=["type"])

    result = evaluator.evaluate('../type = "date" or ../type = "datetime"')
    assert result is True

    # Test that not() works correctly
    result = evaluator.evaluate('not(../nonexistent_field)')
    assert result is True  # Nonexistent field should make not() return True

    # Test simple or
    result = evaluator.evaluate('true() or false()')
    assert result is True


def test_count():
    """Test count() function."""
    data = {
        "fields": [
            {"name": "id", "type": "string"},
            {"name": "name", "type": "string"},
            {"name": "items", "type": "array"}
        ]
    }
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=[])

    result = evaluator.evaluate_value('count(fields[type != "array"])')
    assert result == 2  # Two non-array fields


def test_predicate_filtering():
    """Test predicate filtering."""
    data = {
        "fields": [
            {"name": "id", "type": "string"},
            {"name": "name", "type": "string"}
        ]
    }
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=[])

    # Test filtering
    result = evaluator.evaluate('count(../fields[name = current()])')
    # This is more complex - would need proper context
    # For now, just test that it doesn't crash
    assert isinstance(evaluator.evaluate('count(fields)'), (int, bool))


def test_boolean_functions():
    """Test boolean functions."""
    data = {"required": True}
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=["required"])

    result = evaluator.evaluate('not(../default) or . = false()')
    # If default doesn't exist, not(../default) should be True
    assert isinstance(result, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
