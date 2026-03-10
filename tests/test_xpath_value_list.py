"""
Tests for XPath 2.0 value list support: ( 'a', 'b', 'c' ) in equality.
"""

import pytest
from xyang.xpath import Context, Node, XPathEvaluator, XPathParser, yang_bool


def test_value_list_parses():
    """Value list ( 'string', 'integer', 'number' ) parses without error."""
    ast = XPathParser("../type = ('string', 'integer', 'number')").parse()
    assert ast is not None


def test_value_list_equality_true():
    """type = ('string', 'integer', 'number') is true when type is 'integer'."""
    root_data = {"type": "integer"}
    root = Node(root_data, None, None)
    ctx = Context(current=root, root=root, path_cache={})
    ev = XPathEvaluator()
    ast = XPathParser("type = ('string', 'integer', 'number')").parse()
    result = ev.eval(ast, ctx, root)
    assert yang_bool(result) is True


def test_value_list_equality_false():
    """type = ('string', 'integer') is false when type is 'number'."""
    root_data = {"type": "number"}
    root = Node(root_data, None, None)
    ctx = Context(current=root, root=root, path_cache={})
    ev = XPathEvaluator()
    ast = XPathParser("type = ('string', 'integer')").parse()
    result = ev.eval(ast, ctx, root)
    assert yang_bool(result) is False


def test_value_list_numbers():
    """Numeric value list (1, 2, 3) works in equality."""
    root_data = {"x": 2}
    root = Node(root_data, None, None)
    ctx = Context(current=root, root=root, path_cache={})
    ev = XPathEvaluator()
    ast = XPathParser("x = (1, 2, 3)").parse()
    result = ev.eval(ast, ctx, root)
    assert yang_bool(result) is True
