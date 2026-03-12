"""
XPath parser for xpath. Produces AST nodes with accept(ev, ctx, node).
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

from ..errors import XPathSyntaxError

from .tokenizer import XPathTokenizer
from .tokens import Token, TokenType

from .ast import (
    ASTNode,
    BinaryOpNode,
    FunctionCallNode,
    LiteralNode,
    PathNode,
    PathSegment,
)

logger = logging.getLogger(__name__)

_COMPARISON_OPS = {"=", "!=", "<", ">", "<=", ">="}
_ADDITIVE_OPS = {"+", "-"}


class XPathParser:
    """Parser for XPath expressions producing xpath AST.

    Each _parse_* method returns (ASTNode, is_cacheable). Cacheability is propagated:
    trivial expressions (e.g. integer literal) are cacheable; binary operators are
    cacheable when both operands are; paths are cacheable when absolute and all
    predicates are cacheable (no context-dependent predicates). PathNode.is_cacheable
    is set for use by the evaluator (caching beneficial for absolute paths with
    no context-dependent predicates).
    """

    def __init__(self, expression: str):
        self.expression = expression
        tokenizer = XPathTokenizer(expression)
        self.tokens: List[Token] = tokenizer.tokenize()
        self.position = 0

    def parse(self) -> ASTNode:
        if not self.tokens or self.tokens[0].type == TokenType.EOF:
            raise XPathSyntaxError("Empty expression")
        node, _ = self._parse_expression()
        t = self._current()
        if t.type != TokenType.EOF:
            raise XPathSyntaxError(
                f"Unexpected token: {t.type.name} ({t.value!r})",
                position=t.position,
                expression=self.expression,
            )
        return node

    def parse_path(self) -> PathNode:
        """
        Parse the expression *strictly* as a path and return a PathNode.

        This uses the internal _parse_path() helper directly instead of the full
        expression grammar, so only simple path expressions are accepted:
        - absolute paths starting with '/'
        - relative paths starting with '.', '..', or an identifier
        Predicates (e.g. [cond]) are explicitly rejected here.
        """
        if not self.tokens or self.tokens[0].type == TokenType.EOF:
            raise XPathSyntaxError("Empty path expression")

        t = self._current()
        # Absolute path: leading '/'
        is_absolute = t.type == TokenType.SLASH
        if is_absolute:
            self._consume(TokenType.SLASH)
        # First step parsed by _parse_path (absolute or relative)
        path, _ = self._parse_path(is_absolute=is_absolute, allow_predicate=False)

        # Ensure we've consumed the entire input
        if self._current().type != TokenType.EOF:
            t = self._current()
            raise XPathSyntaxError(
                f"Unexpected token after path: {t.type.name} ({t.value!r})",
                position=t.position,
                expression=self.expression,
            )
        return path

    def _current(self) -> Token:
        if self.position < len(self.tokens):
            return self.tokens[self.position]
        return Token(TokenType.EOF, "", 0)

    def _consume(
        self,
        expected_type: Optional[TokenType] = None,
    ) -> Token:
        t = self._current()
        if expected_type and t.type != expected_type:
            raise XPathSyntaxError(
                f"Expected {expected_type.name}, got {t.type.name} ({t.value!r})",
                position=t.position,
                expression=self.expression,
            )
        self.position += 1
        return t

    def _is_keyword(self, keyword: str) -> bool:
        t = self._current()
        return t.type == TokenType.IDENTIFIER and t.value.lower() == keyword.lower()

    def _parse_expression(self) -> Tuple[ASTNode, bool]:
        return self._parse_logical_or()

    def _parse_logical_or(self) -> Tuple[ASTNode, bool]:
        left, cacheable = self._parse_logical_and()
        while self._is_keyword("or"):
            self._consume()
            right, rc = self._parse_logical_and()
            left = BinaryOpNode(left, "or", right)
            cacheable = cacheable and rc
        return left, cacheable

    def _parse_logical_and(self) -> Tuple[ASTNode, bool]:
        left, cacheable = self._parse_comparison()
        while self._is_keyword("and"):
            self._consume()
            right, rc = self._parse_comparison()
            left = BinaryOpNode(left, "and", right)
            cacheable = cacheable and rc
        return left, cacheable

    def _parse_comparison(self) -> Tuple[ASTNode, bool]:
        left, cacheable = self._parse_additive()
        t = self._current()
        if t.type == TokenType.OPERATOR and t.value in _COMPARISON_OPS:
            op = self._consume().value
            right, rc = self._parse_additive()
            return BinaryOpNode(left, op, right), cacheable and rc
        return left, cacheable

    def _parse_additive(self) -> Tuple[ASTNode, bool]:
        left, cacheable = self._parse_multiplicative()
        while True:
            t = self._current()
            if t.type == TokenType.OPERATOR and t.value in _ADDITIVE_OPS:
                op = self._consume().value
                right, rc = self._parse_multiplicative()
                left = BinaryOpNode(left, op, right)
                cacheable = cacheable and rc
            else:
                break
        return left, cacheable

    def _parse_multiplicative(self) -> Tuple[ASTNode, bool]:
        left, cacheable = self._parse_unary()
        while True:
            t = self._current()
            if t.type == TokenType.SLASH:
                self._consume()
                right, rc = self._parse_path(is_absolute=False)
                left = BinaryOpNode(left, "/", right)
                cacheable = cacheable and rc
            elif t.type == TokenType.OPERATOR and t.value == "*":
                self._consume()
                right, rc = self._parse_unary()
                left = BinaryOpNode(left, "*", right)
                cacheable = cacheable and rc
            else:
                break
        return left, cacheable

    def _parse_unary(self) -> Tuple[ASTNode, bool]:
        t = self._current()
        if t.type == TokenType.OPERATOR and t.value == "-":
            self._consume()
            operand, _ = self._parse_unary()
            return BinaryOpNode(LiteralNode(0), "-", operand), False
        if t.type == TokenType.OPERATOR and t.value == "+":
            self._consume()
            return self._parse_unary()
        if self._is_keyword("not"):
            self._consume()
            self._consume(TokenType.PAREN_OPEN)
            operand, _ = self._parse_expression()
            self._consume(TokenType.PAREN_CLOSE)
            return FunctionCallNode("not", [operand]), False
        return self._parse_primary()

    def _parse_primary(self) -> Tuple[ASTNode, bool]:
        t = self._current()
        if t.type == TokenType.STRING:
            value = self._consume().value
            return LiteralNode(value), False
        if t.type == TokenType.NUMBER:
            raw = self._consume().value
            try:
                value = float(raw) if "." in raw else int(raw)
            except ValueError:
                raise XPathSyntaxError(
                    f"Invalid number: {raw}",
                    position=t.position,
                    expression=self.expression,
                )
            return LiteralNode(value), isinstance(value, int)
        if t.type == TokenType.IDENTIFIER:
            if self._is_keyword("true"):
                self._consume()
                if self._current().type == TokenType.PAREN_OPEN:
                    self._consume(TokenType.PAREN_OPEN)
                    self._consume(TokenType.PAREN_CLOSE)
                return LiteralNode(True), False
            if self._is_keyword("false"):
                self._consume()
                if self._current().type == TokenType.PAREN_OPEN:
                    self._consume(TokenType.PAREN_OPEN)
                    self._consume(TokenType.PAREN_CLOSE)
                return LiteralNode(False), False
            if (
                self.position + 1 < len(self.tokens)
                and self.tokens[self.position + 1].type == TokenType.PAREN_OPEN
            ):
                return self._parse_function_call()
            return self._parse_path(is_absolute=False)
        if t.type == TokenType.DOT:
            self._consume()
            if self._current().type == TokenType.PAREN_OPEN:
                self._consume(TokenType.PAREN_OPEN)
                self._consume(TokenType.PAREN_CLOSE)
                return FunctionCallNode("current", []), False
            return self._parse_path(is_absolute=False, first_step=".")
        if t.type == TokenType.DOTDOT:
            return self._parse_path(is_absolute=False)
        if t.type == TokenType.SLASH:
            self._consume()
            return self._parse_path(is_absolute=True)
        if t.type == TokenType.PAREN_OPEN:
            self._consume(TokenType.PAREN_OPEN)
            # XPath 2.0 value list: ( 'a', 'b', 'c' ) when first token is string/number
            peek = self._current()
            if peek.type in (TokenType.STRING, TokenType.NUMBER):
                first, _ = self._parse_primary()
                if isinstance(first, LiteralNode) and self._current().type == TokenType.COMMA:
                    values: List[Any] = [first.value]
                    while self._current().type == TokenType.COMMA:
                        self._consume(TokenType.COMMA)
                        next_node, _ = self._parse_primary()
                        if not isinstance(next_node, LiteralNode):
                            raise XPathSyntaxError(
                                "Value list may only contain literals (string or number)",
                                position=self._current().position,
                                expression=self.expression,
                            )
                        values.append(next_node.value)
                    self._consume(TokenType.PAREN_CLOSE)
                    return LiteralNode(tuple(values)), False
                if self._current().type == TokenType.PAREN_CLOSE:
                    self._consume(TokenType.PAREN_CLOSE)
                    return first, isinstance(first.value, int) if isinstance(first, LiteralNode) else False
            # Single expression in parentheses
            expr, cacheable = self._parse_expression()
            self._consume(TokenType.PAREN_CLOSE)
            return expr, cacheable
        raise XPathSyntaxError(
            f"Unexpected token: {t}",
            position=t.position,
            expression=self.expression,
        )

    def _parse_function_call(self) -> Tuple[ASTNode, bool]:
        name = self._consume().value
        self._consume(TokenType.PAREN_OPEN)
        args: List[ASTNode] = []
        if self._current().type != TokenType.PAREN_CLOSE:
            node, _ = self._parse_expression()
            args.append(node)
            while self._current().type == TokenType.COMMA:
                self._consume(TokenType.COMMA)
                node, _ = self._parse_expression()
                args.append(node)
        self._consume(TokenType.PAREN_CLOSE)
        return FunctionCallNode(name, args), False

    def _parse_path(
        self,
        is_absolute: bool,
        first_step: Optional[str] = None,
        allow_predicate: bool = True,
    ) -> Tuple[PathNode, bool]:
        segments: List[PathSegment] = []
        cacheable = is_absolute

        def _add_step_and_optional_predicate(step: str) -> bool:
            """
            Append a step (segment) with an optional predicate, and then
            consume a trailing '/' if present.

            Returns True if a '/' was consumed (meaning another step may follow),
            otherwise False.
            """
            nonlocal cacheable
            seg = PathSegment(step, None)
            segments.append(seg)
            if self._current().type == TokenType.BRACKET_OPEN:
                if not allow_predicate:
                    raise XPathSyntaxError(
                        "Predicates are not allowed in this path context",
                        position=self._current().position,
                        expression=self.expression,
                    )
                self._consume(TokenType.BRACKET_OPEN)
                pred_node, pred_cacheable = self._parse_expression()
                seg.predicate = pred_node
                cacheable = cacheable and pred_cacheable
                self._consume(TokenType.BRACKET_CLOSE)
            if self._current().type == TokenType.SLASH:
                self._consume()
                return True
            return False
        if first_step is not None:
            _add_step_and_optional_predicate(first_step)
        while self._current().type in (TokenType.DOT, TokenType.DOTDOT, TokenType.IDENTIFIER):
            step = self._consume().value
            if not _add_step_and_optional_predicate(step):
                break
        return PathNode(segments, is_absolute, is_cacheable=cacheable), cacheable
