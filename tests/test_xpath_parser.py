"""
Tests for XPath parser covering expression cases and error paths.
"""

import pytest

from xyang.errors import XPathSyntaxError
from xyang.xpath import Context, Node, XPathEvaluator, XPathParser
from xyang.xpath.ast import BinaryOpNode, LiteralNode, PathNode


# --- parse() error paths ---


def test_empty_expression_raises():
    """Empty expression raises XPathSyntaxError."""
    with pytest.raises(XPathSyntaxError, match="Empty expression"):
        XPathParser("").parse()


def test_trailing_token_raises():
    """Unexpected token after expression raises XPathSyntaxError."""
    with pytest.raises(XPathSyntaxError, match="Unexpected token"):
        XPathParser("1 2").parse()
    with pytest.raises(XPathSyntaxError, match="Unexpected token"):
        XPathParser("a = 1 ,").parse()


def test_unexpected_primary_token_raises():
    """Invalid primary (e.g. unmatched ] or invalid char) raises XPathSyntaxError."""
    with pytest.raises(XPathSyntaxError, match="Unexpected token"):
        XPathParser("]").parse()


# --- _consume type mismatch (expected token type) ---


def test_missing_paren_close_raises():
    """Missing closing paren in not() raises XPathSyntaxError."""
    with pytest.raises(XPathSyntaxError, match="Expected.*PAREN_CLOSE|Expected.*got"):
        XPathParser("not( 1").parse()


def test_missing_paren_close_after_value_list_raises():
    """Value list missing closing paren raises XPathSyntaxError."""
    with pytest.raises(XPathSyntaxError, match="Expected|got"):
        XPathParser("x = ( 'a' , 'b' ").parse()


# --- multiplicative: slash with non-path left, operator * ---


def test_slash_with_non_path_left_parses():
    """Expression like 1/foo parses as BinaryOpNode (division-like)."""
    ast = XPathParser("1 / foo").parse()
    assert isinstance(ast, BinaryOpNode)
    assert ast.operator == "/"
    assert isinstance(ast.left, LiteralNode)
    assert ast.left.value == 1


def test_path_slash_path_parses():
    """a/b/c is parsed as a single PathNode by _parse_path (multiplicative never sees path / path)."""
    ast = XPathParser("a / b / c").parse()
    assert isinstance(ast, PathNode)
    assert [s.step for s in ast.segments] == ["a", "b", "c"]


def test_multiplication_parses():
    """Multiplication parses (e.g. 2*3)."""
    ast = XPathParser("2 * 3").parse()
    assert isinstance(ast, BinaryOpNode)
    assert ast.operator == "*"
    assert ast.left.value == 2
    assert ast.right.value == 3


# --- unary: not(...), unary + ---


def test_not_expr_parses():
    """not(...) parses."""
    ast = XPathParser("not( false )").parse()
    assert ast is not None
    # Evaluator: not(false) -> True
    root = Node({}, None, None)
    ctx = Context(current=root, root=root, path_cache={})
    result = XPathEvaluator().eval(ast, ctx, root)
    assert result is True


def test_unary_plus_parses():
    """Unary + parses (e.g. +1) and yields the operand."""
    ast = XPathParser("+ 1").parse()
    assert ast is not None
    # Parser reduces +1 to the inner expression (LiteralNode 1)
    assert isinstance(ast, LiteralNode)
    assert ast.value == 1


# --- primary: true(), leading .., value list error, single literal in parens ---


def test_true_with_parens_parses():
    """true() parses as LiteralNode(True)."""
    ast = XPathParser("true()").parse()
    assert isinstance(ast, LiteralNode)
    assert ast.value is True


def test_leading_dotdot_parses():
    """Leading .. parses as path."""
    ast = XPathParser("../foo").parse()
    assert isinstance(ast, PathNode)
    assert len(ast.segments) >= 1
    assert ast.segments[0].step == ".."


def test_value_list_with_non_literal_raises():
    """Value list containing non-literal (e.g. path) raises."""
    with pytest.raises(XPathSyntaxError, match="Value list may only contain literals"):
        XPathParser("x = ( 1, foo )").parse()
    with pytest.raises(XPathSyntaxError, match="Value list may only contain literals"):
        XPathParser("x = ( 'a', bar )").parse()


def test_single_parenthesized_literal_parses():
    """Single literal in parentheses ( 42 ) parses."""
    ast = XPathParser("( 42 )").parse()
    assert isinstance(ast, LiteralNode)
    assert ast.value == 42


# --- path steps with predicates ---


def test_path_first_step_with_predicate_parses():
    """Path starting with . and predicate .[1]/a parses."""
    ast = XPathParser(".[ 1 ] / a").parse()
    assert isinstance(ast, PathNode)
    assert len(ast.segments) >= 1
    assert ast.segments[0].step == "."
    assert ast.segments[0].predicate is not None


def test_path_dotdot_with_predicate_parses():
    """Path step .. with predicate parses (e.g. ..[1] or ..[x=1])."""
    ast = XPathParser("..[ x = 1 ]").parse()
    assert isinstance(ast, PathNode)
    assert ast.segments[0].step == ".."
    assert ast.segments[0].predicate is not None


def test_path_dot_with_predicate_parses():
    """Path step . with predicate parses."""
    ast = XPathParser(". [ 1 ]").parse()
    assert isinstance(ast, PathNode)
    assert ast.segments[0].step == "."
    assert ast.segments[0].predicate is not None


def test_path_identifier_with_predicate_parses():
    """Path step identifier with predicate parses (e.g. a[1], foo[bar=1])."""
    ast = XPathParser("a[ 1 ]").parse()
    assert isinstance(ast, PathNode)
    assert ast.segments[0].step == "a"
    assert ast.segments[0].predicate is not None
    ast2 = XPathParser("foo[ bar = 1 ]").parse()
    assert isinstance(ast2, PathNode)
    assert ast2.segments[0].step == "foo"
    assert ast2.segments[0].predicate is not None


# --- invalid number (ValueError in primary) ---


def test_invalid_number_raises():
    """Invalid number literal raises XPathSyntaxError."""
    # Tokenizer may still hand us something that parses as NUMBER but fails int/float
    with pytest.raises((XPathSyntaxError, ValueError)):
        XPathParser("1e2e3").parse()
