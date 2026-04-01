"""
Tests for when expression support.
"""

from typing import Any, List

import pytest
from xyang import parse_yang_string, YangValidator
from xyang.ast import YangStatementWithWhen
from xyang.xpath import (
    Context,
    Node,
    XPathEvaluator,
    XPathParser,
    SchemaNav,
    yang_bool,
)


def _make_node_context(
    data: Any,
    module: Any,
    context_path: List[Any],
) -> tuple[Context, Node]:
    """Build (Context, Node) for xyang evaluator from data, module, and path."""
    root = Node(data, module, None)
    current_node = root
    for seg in context_path:
        if isinstance(current_node.data, list):
            current_data = current_node.data[seg]
            current_schema = current_node.schema
        else:
            current_schema = SchemaNav.child(current_node.schema, seg)
            if current_schema is None:
                raise ValueError(
                    f"no schema for {seg!r} under "
                    f"{getattr(current_node.schema, 'name', current_node.schema)}"
                )
            data_val = (
                current_node.data.get(seg)
                if isinstance(current_node.data, dict)
                else None
            )
            if data_val is None:
                data_val = SchemaNav.default(current_schema)
            current_data = data_val
        current_node = Node(current_data, current_schema, current_node)
    ctx = Context(current=current_node, root=root, path_cache={})
    return ctx, current_node


def _evaluate_bool(ev: XPathEvaluator, expr: str, ctx: Context, node: Node) -> bool:
    """Parse expr, evaluate, return YANG boolean."""
    ast = XPathParser(expr).parse()
    result = ev.eval(ast, ctx, node)
    return yang_bool(result)


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
    assert isinstance(item_type, YangStatementWithWhen)
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


def test_when_braced_form_with_description():
    """RFC 7950: when may include a description substatement in the braced form."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf mode {
      type string;
    }
    leaf extra {
      when "../mode = 'on'" {
        description "Only when mode is on.";
      }
      type string;
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    data_model = module.find_statement("data")
    assert data_model is not None
    extra = next(s for s in data_model.statements if getattr(s, "name", None) == "extra")
    assert extra.when is not None
    assert extra.when.condition == "../mode = 'on'"
    assert "Only when mode is on" in extra.when.description


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
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf type { type string; }
    container item_type {
      when "../type = 'array'";
      leaf primitive { type string; }
    }
  }
}
"""
    module = parse_yang_string(yang_content)

    # When is evaluated in parent context: current = container "data"
    # ../type from item_type = parent.type = "array"
    data_true = {"data": {"type": "array", "item_type": {"primitive": "string"}}}
    ctx, node = _make_node_context(data_true, module, ["data", "item_type"])
    evaluator = XPathEvaluator()
    result = _evaluate_bool(evaluator, "../type = 'array'", ctx, node)
    assert result is True

    # False condition
    data_false = {"data": {"type": "string", "item_type": {}}}
    ctx2, node2 = _make_node_context(data_false, module, ["data", "item_type"])
    result2 = _evaluate_bool(evaluator, "../type = 'array'", ctx2, node2)
    assert result2 is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
