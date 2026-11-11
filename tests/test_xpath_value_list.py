"""
Tests for XPath 2.0 value list parsing: ( 'a', 'b', 'c' ) in equality.

Evaluation of value-list must constraints lives in tests/cases/xpath/value-list.
"""

from xyang.xpath import XPathParser


def test_value_list_parses():
    """Value list ( 'string', 'integer', 'number' ) parses without error."""
    ast = XPathParser("../type = ('string', 'integer', 'number')").parse()
    assert ast is not None
