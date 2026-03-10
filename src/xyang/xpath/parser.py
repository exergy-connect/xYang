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
        self, is_absolute: bool, first_step: Optional[str] = None
    ) -> Tuple[PathNode, bool]:
        steps: List[str] = []
        predicates: List[Optional[ASTNode]] = []
        cacheable = is_absolute
        if first_step is not None:
            steps.append(first_step)
            predicates.append(None)
            if self._current().type == TokenType.BRACKET_OPEN:
                self._consume(TokenType.BRACKET_OPEN)
                pred_node, pred_cacheable = self._parse_expression()
                predicates[-1] = pred_node
                cacheable = cacheable and pred_cacheable
                self._consume(TokenType.BRACKET_CLOSE)
            if self._current().type == TokenType.SLASH:
                self._consume()
        while True:
            t = self._current()
            if t.type == TokenType.DOTDOT:
                steps.append(self._consume().value)
                predicates.append(None)
                if self._current().type == TokenType.BRACKET_OPEN:
                    self._consume(TokenType.BRACKET_OPEN)
                    pred_node, pred_cacheable = self._parse_expression()
                    predicates[-1] = pred_node
                    cacheable = cacheable and pred_cacheable
                    self._consume(TokenType.BRACKET_CLOSE)
                if self._current().type == TokenType.SLASH:
                    self._consume()
                else:
                    break
            elif t.type == TokenType.DOT:
                self._consume()
                steps.append(".")
                predicates.append(None)
                if self._current().type == TokenType.BRACKET_OPEN:
                    self._consume(TokenType.BRACKET_OPEN)
                    pred_node, pred_cacheable = self._parse_expression()
                    predicates[-1] = pred_node
                    cacheable = cacheable and pred_cacheable
                    self._consume(TokenType.BRACKET_CLOSE)
                if self._current().type == TokenType.SLASH:
                    self._consume()
                else:
                    break
            elif t.type == TokenType.IDENTIFIER:
                steps.append(self._consume().value)
                predicates.append(None)
                if self._current().type == TokenType.BRACKET_OPEN:
                    self._consume(TokenType.BRACKET_OPEN)
                    pred_node, pred_cacheable = self._parse_expression()
                    predicates[-1] = pred_node
                    cacheable = cacheable and pred_cacheable
                    self._consume(TokenType.BRACKET_CLOSE)
                if self._current().type == TokenType.SLASH:
                    self._consume()
                else:
                    break
            else:
                break
        segments = [PathSegment(step, pred) for step, pred in zip(steps, predicates)]
        return PathNode(segments, is_absolute, is_cacheable=cacheable), cacheable
