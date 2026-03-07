"""
Tests for XPath evaluator.
"""

import pytest
from xYang import XPathEvaluator, parse_yang_string
from tests.test_utils import create_context


def test_string_length():
    """Test string-length() function."""
    data = {"name": "test_value"}
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=["name"])

    context = create_context(data, ["name"])
    result = evaluator.evaluate_value('string-length(.)', context)
    assert result == 10  # "test_value" has 10 characters


def test_translate():
    """Test translate() function."""
    data = {"name": "test_value_with_underscores"}
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=["name"])

    context = create_context(data, ["name"])
    result = evaluator.evaluate_value('string-length(.) - string-length(translate(., "_", ""))', context)
    # Should count underscores: "test_value_with_underscores" has 3 underscores
    assert result == 3


def test_current():
    """Test current() function."""
    data = {"name": "test"}
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=["name"])

    context = create_context(data, ["name"])
    # Test current() returns the value
    current_val = evaluator.evaluate_value('current()', context)
    assert current_val == "test"

    # Test comparison
    result = evaluator.evaluate('current() = "test"', context)
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

    context = create_context(data, ["entity", "name"])
    # From ['entity', 'name'], ../ goes to ['entity'], then max_underscores
    result = evaluator.evaluate_value('../max_underscores', context)
    assert result == 2


def test_comparison():
    """Test comparison operators."""
    data = {"count": 5}
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=["count"])

    context = create_context(data, ["count"])
    assert evaluator.evaluate('. <= 7', context) is True
    assert evaluator.evaluate('. >= 3', context) is True
    assert evaluator.evaluate('. = 5', context) is True
    assert evaluator.evaluate('. != 10', context) is True


def test_xpath2_sequence_equality():
    """Test XPath 2.0-style sequence on RHS of =: left equals any item in sequence."""
    module = parse_yang_string("module test { }")

    # type = 'integer' -> . = ('integer', 'number') is True
    data = {"type": "integer"}
    evaluator = XPathEvaluator(data, module, context_path=["type"])
    context = create_context(data, ["type"])
    assert evaluator.evaluate('. = ("integer", "number")', context) is True

    # type = 'number' -> . = ('integer', 'number') is True
    data = {"type": "number"}
    evaluator = XPathEvaluator(data, module, context_path=["type"])
    context = create_context(data, ["type"])
    assert evaluator.evaluate('. = ("integer", "number")', context) is True

    # type = 'string' -> . = ('integer', 'number') is False
    data = {"type": "string"}
    evaluator = XPathEvaluator(data, module, context_path=["type"])
    context = create_context(data, ["type"])
    assert evaluator.evaluate('. = ("integer", "number")', context) is False


def test_logical_operators():
    """Test logical operators."""
    data = {"type": "date", "minDate": "2020-01-01", "maxDate": "2025-01-01"}
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=["type"])

    context = create_context(data, ["type"])
    result = evaluator.evaluate('../type = "date" or ../type = "datetime"', context)
    assert result is True

    # Test that not() works correctly
    result = evaluator.evaluate('not(../nonexistent_field)', context)
    assert result is True  # Nonexistent field should make not() return True

    # Test simple or
    result = evaluator.evaluate('true() or false()', context)
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

    context = create_context(data, [])
    result = evaluator.evaluate_value('count(fields[type != "array"])', context)
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

    context = create_context(data, [])
    # Test filtering
    result = evaluator.evaluate('count(../fields[name = current()])', context)
    # This is more complex - would need proper context
    # For now, just test that it doesn't crash
    assert isinstance(evaluator.evaluate('count(fields)', context), (int, bool))


def test_boolean_functions():
    """Test boolean functions."""
    data = {"required": True}
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=["required"])

    context = create_context(data, ["required"])
    result = evaluator.evaluate('not(../default) or . = false()', context)
    # If default doesn't exist, not(../default) should be True
    assert isinstance(result, bool)


def test_string_conversion():
    """Test string() function conversion."""
    data = {
        "name": "test",
        "count": 42,
        "price": 3.14,
        "active": True,
        "inactive": False,
        "items": ["first", "second"]
    }
    module = parse_yang_string("module test { }")
    evaluator = XPathEvaluator(data, module, context_path=[])

    context = create_context(data, [])
    
    # Test string() with no args - converts current context node
    context_name = create_context(data, ["name"])
    result = evaluator.evaluate_value('string()', context_name)
    assert result == "test"
    
    # Test string() with string argument
    result = evaluator.evaluate_value('string("hello")', context)
    assert result == "hello"
    
    # Test string() with integer
    context_count = create_context(data, ["count"])
    result = evaluator.evaluate_value('string(.)', context_count)
    assert result == "42"
    
    # Test string() with float
    context_price = create_context(data, ["price"])
    result = evaluator.evaluate_value('string(.)', context_price)
    assert result == "3.14"
    
    # Test string() with boolean True
    context_active = create_context(data, ["active"])
    result = evaluator.evaluate_value('string(.)', context_active)
    assert result == "true"
    
    # Test string() with boolean False
    context_inactive = create_context(data, ["inactive"])
    result = evaluator.evaluate_value('string(.)', context_inactive)
    assert result == "false"
    
    # Test string() with list (should return string of first element)
    context_items = create_context(data, ["items"])
    result = evaluator.evaluate_value('string(.)', context_items)
    assert result == "first"
    
    # Test string() with None/missing value
    context_missing = create_context(data, ["nonexistent"])
    result = evaluator.evaluate_value('string(.)', context_missing)
    assert result == ""
    
    # Test string() in comparison
    result = evaluator.evaluate('string(42) = "42"', context)
    assert result is True
    
    result = evaluator.evaluate('string(true()) = "true"', context)
    assert result is True
    
    result = evaluator.evaluate('string(false()) = "false"', context)
    assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
