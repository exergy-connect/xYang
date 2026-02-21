"""
New unit tests for XPathEvaluator focusing on Context parameter usage.

This test file focuses on testing the refactored path_evaluator that uses
Context as a parameter instead of accessing evaluator attributes directly.
"""

import pytest
from xYang import XPathEvaluator, parse_yang_string
from xYang.xpath.context import Context


# Sample YANG module for testing
SAMPLE_YANG = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data-model {
    list entities {
      key name;
      leaf name {
        type string;
      }
      list fields {
        key name;
        leaf name {
          type string;
        }
        leaf type {
          type string;
        }
      }
    }
  }
}
"""


class TestContextParameterUsage:
    """Test that Context parameter is properly used in path evaluation."""

    def test_evaluate_path_with_context(self):
        """Test that evaluate_path requires and uses Context parameter."""
        data = {
            "data-model": {
                "entities": [
                    {"name": "company", "fields": [{"name": "id", "type": "string"}]}
                ]
            }
        }
        module = parse_yang_string(SAMPLE_YANG)
        evaluator = XPathEvaluator(data, module)
        
        context = evaluator.create_context(data, ["data-model", "entities", 0])
        result = evaluator.path_evaluator.evaluate_path("name", context)
        assert result == "company"

    def test_evaluate_path_absolute_with_context(self):
        """Test absolute path evaluation with context."""
        data = {
            "data-model": {
                "entities": [
                    {"name": "company"}
                ]
            }
        }
        module = parse_yang_string(SAMPLE_YANG)
        evaluator = XPathEvaluator(data, module)
        
        context = evaluator.create_context(data, [])
        result = evaluator.path_evaluator.evaluate_path("/data-model/entities", context)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["name"] == "company"

    def test_evaluate_path_relative_with_context(self):
        """Test relative path evaluation with context."""
        data = {
            "data-model": {
                "entities": [
                    {"name": "company", "fields": [{"name": "id", "type": "string"}]}
                ]
            }
        }
        module = parse_yang_string(SAMPLE_YANG)
        evaluator = XPathEvaluator(
            data,
            module,
            context_path=["data-model", "entities", 0, "fields", 0]
        )
        
        context = evaluator.create_context(data, ["data-model", "entities", 0, "fields", 0])
        result = evaluator.path_evaluator.evaluate_path("../name", context)
        assert result == "company"

    def test_get_path_value_with_context(self):
        """Test that get_path_value requires Context parameter."""
        data = {
            "data-model": {
                "entities": [
                    {"name": "company", "fields": [{"name": "id"}]}
                ]
            }
        }
        module = parse_yang_string(SAMPLE_YANG)
        evaluator = XPathEvaluator(data, module)
        
        context = evaluator.create_context(data, [])
        result = evaluator.path_evaluator.get_path_value(
            ["data-model", "entities", 0, "name"],
            context
        )
        assert result == "company"

    def test_context_independence(self):
        """Test that different contexts don't interfere with each other."""
        data = {
            "data-model": {
                "entities": [
                    {"name": "company", "fields": [{"name": "id", "type": "string"}]},
                    {"name": "department", "fields": [{"name": "dept_id", "type": "string"}]}
                ]
            }
        }
        module = parse_yang_string(SAMPLE_YANG)
        evaluator = XPathEvaluator(data, module)
        
        # Create two different contexts
        context1 = evaluator.create_context(data, ["data-model", "entities", 0])
        context2 = evaluator.create_context(data, ["data-model", "entities", 1])
        
        result1 = evaluator.path_evaluator.evaluate_path("name", context1)
        result2 = evaluator.path_evaluator.evaluate_path("name", context2)
        
        assert result1 == "company"
        assert result2 == "department"

    def test_context_with_data_modification(self):
        """Test that context.with_data() creates new context without modifying original."""
        data = {
            "data-model": {
                "entities": [
                    {"name": "company", "fields": [{"name": "id"}]}
                ]
            }
        }
        module = parse_yang_string(SAMPLE_YANG)
        evaluator = XPathEvaluator(data, module)
        
        original_context = evaluator.create_context(data, ["data-model", "entities", 0])
        new_data = {"name": "department"}
        new_context = original_context.with_data(new_data, [])
        
        # Original context should still point to original data
        result1 = evaluator.path_evaluator.evaluate_path("name", original_context)
        assert result1 == "company"
        
        # New context should point to new data
        result2 = evaluator.path_evaluator.evaluate_path("name", new_context)
        assert result2 == "department"

    def test_context_current_function(self):
        """Test that context.current() works correctly."""
        data = {
            "data-model": {
                "entities": [
                    {"name": "company"}
                ]
            }
        }
        module = parse_yang_string(SAMPLE_YANG)
        evaluator = XPathEvaluator(
            data,
            module,
            context_path=["data-model", "entities", 0, "name"]
        )
        
        context = evaluator.create_context(data, ["data-model", "entities", 0, "name"])
        current_value = context.current()
        assert current_value == "company"

    def test_evaluate_path_node_with_context(self):
        """Test that evaluate_path_node requires Context parameter."""
        from xYang.xpath.ast import PathNode
        
        data = {
            "data-model": {
                "entities": [
                    {"name": "company", "fields": [{"name": "id"}]}
                ]
            }
        }
        module = parse_yang_string(SAMPLE_YANG)
        evaluator = XPathEvaluator(data, module)
        
        path_node = PathNode(steps=["data-model", "entities", "0", "name"], is_absolute=False)
        context = evaluator.create_context(data, [])
        result = evaluator.path_evaluator.evaluate_path_node(path_node, context)
        assert result == "company"

    def test_context_preserves_original_for_current(self):
        """Test that context preserves original_context_path for current() function."""
        data = {
            "data-model": {
                "entities": [
                    {"name": "company", "fields": [{"name": "id", "type": "string"}]}
                ]
            }
        }
        module = parse_yang_string(SAMPLE_YANG)
        evaluator = XPathEvaluator(
            data,
            module,
            context_path=["data-model", "entities", 0, "name"]
        )
        
        original_context = evaluator.create_context(data, ["data-model", "entities", 0, "name"])
        
        # Create new context with different data but preserve original
        new_data = {"name": "department"}
        new_context = original_context.with_data(new_data, [])
        
        # current() should still return original value
        assert new_context.current() == "company"
        
        # But direct access should return new value
        result = evaluator.path_evaluator.evaluate_path("name", new_context)
        assert result == "department"

    def test_context_root_data_access(self):
        """Test that context.root_data is accessible for absolute paths."""
        data = {
            "data-model": {
                "entities": [
                    {"name": "company"}
                ]
            }
        }
        module = parse_yang_string(SAMPLE_YANG)
        evaluator = XPathEvaluator(data, module)
        
        context = evaluator.create_context(data, ["data-model", "entities", 0])
        
        # Should be able to access root_data through context
        assert context.root_data == data
        # context.data is the full data when context_path is set
        assert context.data == data

    def test_multiple_context_creations(self):
        """Test creating multiple contexts from same evaluator."""
        data = {
            "data-model": {
                "entities": [
                    {"name": "company"},
                    {"name": "department"}
                ]
            }
        }
        module = parse_yang_string(SAMPLE_YANG)
        evaluator = XPathEvaluator(data, module)
        
        context1 = evaluator.create_context(data, ["data-model", "entities", 0])
        context2 = evaluator.create_context(data, ["data-model", "entities", 1])
        
        result1 = evaluator.path_evaluator.evaluate_path("name", context1)
        result2 = evaluator.path_evaluator.evaluate_path("name", context2)
        
        assert result1 == "company"
        assert result2 == "department"

    def test_context_with_empty_path(self):
        """Test context creation with empty context_path."""
        data = {"value": "test"}
        module = parse_yang_string("module test { }")
        evaluator = XPathEvaluator(data, module)
        
        context = evaluator.create_context(data, [])
        result = evaluator.path_evaluator.evaluate_path(".", context)
        # When context_path is empty and data is a dict, "." returns the dict
        # But if data has a single key with a primitive value, it might return that value
        assert result == data or result == "test"

    def test_context_path_navigation(self):
        """Test that context_path is used correctly for relative navigation."""
        data = {
            "data-model": {
                "entities": [
                    {
                        "name": "company",
                        "fields": [
                            {"name": "id", "type": "string"},
                            {"name": "name", "type": "string"}
                        ]
                    }
                ]
            }
        }
        module = parse_yang_string(SAMPLE_YANG)
        evaluator = XPathEvaluator(
            data,
            module,
            context_path=["data-model", "entities", 0, "fields", 0]
        )
        
        context = evaluator.create_context(data, ["data-model", "entities", 0, "fields", 0])
        
        # Navigate up one level
        result = evaluator.path_evaluator.evaluate_path("../../name", context)
        assert result == "company"
        
        # Navigate to sibling field - fields[2] in XPath means the second field (1-indexed)
        # But we need to navigate to the name field of that field
        # The path "../fields[2]/name" should get the name of the second field
        result = evaluator.path_evaluator.evaluate_path("../fields[2]/name", context)
        # If it returns the field dict, extract the name
        if isinstance(result, dict):
            assert result.get("name") == "name"
        else:
            assert result == "name"

    def test_context_immutability(self):
        """Test that Context objects are immutable (frozen dataclass)."""
        data = {"value": "test"}
        module = parse_yang_string("module test { }")
        evaluator = XPathEvaluator(data, module)
        
        context = evaluator.create_context(data, [])
        
        # Should not be able to modify context directly
        with pytest.raises(Exception):  # dataclass.FrozenInstanceError
            context.data = {"new": "data"}

    def test_evaluate_path_with_predicate_and_context(self):
        """Test path evaluation with predicate using context."""
        data = {
            "data-model": {
                "entities": [
                    {
                        "name": "company",
                        "fields": [
                            {"name": "id", "type": "string"},
                            {"name": "name", "type": "string"}
                        ]
                    }
                ]
            }
        }
        module = parse_yang_string(SAMPLE_YANG)
        evaluator = XPathEvaluator(data, module)
        
        context = evaluator.create_context(data, ["data-model", "entities", 0])
        result = evaluator.path_evaluator.evaluate_path("fields[name = 'id']", context)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["name"] == "id"
