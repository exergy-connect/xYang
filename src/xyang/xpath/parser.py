"""
XPath parser for xpath. Produces AST nodes with accept(ev, ctx, node).
"""

from __future__ import annotations

from typing import List, Optional

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

_COMPARISON_OPS = {"=", "!=", "<", ">", "<=", ">="}
_ADDITIVE_OPS = {"+", "-"}


class XPathParser:
    """Parser for XPath expressions producing xpath AST."""

    def __init__(self, expression: str):
        self.expression = expression
        tokenizer = XPathTokenizer(expression)
        self.tokens: List[Token] = tokenizer.tokenize()
        self.position = 0

    def parse(self) -> ASTNode:
        if not self.tokens or self.tokens[0].type == TokenType.EOF:
            raise XPathSyntaxError("Empty expression")
        node = self._parse_expression()
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
        expected_value: Optional[str] = None,
    ) -> Token:
        t = self._current()
        if expected_type and t.type != expected_type:
            raise XPathSyntaxError(
                f"Expected {expected_type.name}, got {t.type.name} ({t.value!r})",
                position=t.position,
                expression=self.expression,
            )
        if expected_value and t.value != expected_value:
            raise XPathSyntaxError(
                f"Expected {expected_value!r}, got {t.value!r}",
                position=t.position,
                expression=self.expression,
            )
        self.position += 1
        return t

    def _is_keyword(self, keyword: str) -> bool:
        t = self._current()
        return t.type == TokenType.IDENTIFIER and t.value.lower() == keyword.lower()

    def _parse_expression(self) -> ASTNode:
        return self._parse_logical_or()

    def _parse_logical_or(self) -> ASTNode:
        left = self._parse_logical_and()
        while self._is_keyword("or"):
            self._consume()
            right = self._parse_logical_and()
            left = BinaryOpNode(left, "or", right)
        return left

    def _parse_logical_and(self) -> ASTNode:
        left = self._parse_comparison()
        while self._is_keyword("and"):
            self._consume()
            right = self._parse_comparison()
            left = BinaryOpNode(left, "and", right)
        return left

    def _parse_comparison(self) -> ASTNode:
        left = self._parse_additive()
        t = self._current()
        if t.type == TokenType.OPERATOR and t.value in _COMPARISON_OPS:
            op = self._consume().value
            right = self._parse_additive()
            return BinaryOpNode(left, op, right)
        return left

    def _parse_additive(self) -> ASTNode:
        left = self._parse_multiplicative()
        while True:
            t = self._current()
            if t.type == TokenType.OPERATOR and t.value in _ADDITIVE_OPS:
                op = self._consume().value
                right = self._parse_multiplicative()
                left = BinaryOpNode(left, op, right)
            else:
                break
        return left

    def _parse_multiplicative(self) -> ASTNode:
        left = self._parse_unary()
        while True:
            t = self._current()
            is_slash = (
                t.type == TokenType.SLASH
                or (t.type == TokenType.OPERATOR and t.value == "/")
            )
            if is_slash:
                self._consume()
                right = self._parse_path(is_absolute=False)
                if isinstance(left, PathNode):
                    left = PathNode(
                        left.segments + right.segments,
                        is_absolute=left.is_absolute,
                    )
                else:
                    left = BinaryOpNode(left, "/", right)
            elif t.type == TokenType.OPERATOR and t.value == "*":
                self._consume()
                right = self._parse_unary()
                left = BinaryOpNode(left, "*", right)
            else:
                break
        return left

    def _parse_unary(self) -> ASTNode:
        t = self._current()
        if t.type == TokenType.OPERATOR and t.value == "-":
            self._consume()
            return BinaryOpNode(LiteralNode(0), "-", self._parse_unary())
        if t.type == TokenType.OPERATOR and t.value == "+":
            self._consume()
            return self._parse_unary()
        if self._is_keyword("not"):
            self._consume()
            self._consume(TokenType.PAREN_OPEN)
            operand = self._parse_expression()
            self._consume(TokenType.PAREN_CLOSE)
            return FunctionCallNode("not", [operand])
        return self._parse_primary()

    def _parse_primary(self) -> ASTNode:
        t = self._current()
        if t.type == TokenType.STRING:
            value = self._consume().value
            return LiteralNode(value)
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
            return LiteralNode(value)
        if t.type == TokenType.IDENTIFIER:
            if self._is_keyword("true"):
                self._consume()
                if self._current().type == TokenType.PAREN_OPEN:
                    self._consume(TokenType.PAREN_OPEN)
                    self._consume(TokenType.PAREN_CLOSE)
                return LiteralNode(True)
            if self._is_keyword("false"):
                self._consume()
                if self._current().type == TokenType.PAREN_OPEN:
                    self._consume(TokenType.PAREN_OPEN)
                    self._consume(TokenType.PAREN_CLOSE)
                return LiteralNode(False)
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
                return FunctionCallNode("current", [])
            return self._parse_path(is_absolute=False, first_step=".")
        if t.type == TokenType.DOTDOT:
            return self._parse_path(is_absolute=False)
        if t.type == TokenType.SLASH:
            self._consume()
            return self._parse_path(is_absolute=True)
        if t.type == TokenType.PAREN_OPEN:
            self._consume(TokenType.PAREN_OPEN)
            expr = self._parse_expression()
            self._consume(TokenType.PAREN_CLOSE)
            return expr
        raise XPathSyntaxError(
            f"Unexpected token: {t}",
            position=t.position,
            expression=self.expression,
        )

    def _parse_function_call(self) -> ASTNode:
        name = self._consume().value
        self._consume(TokenType.PAREN_OPEN)
        args: List[ASTNode] = []
        if self._current().type != TokenType.PAREN_CLOSE:
            args.append(self._parse_expression())
            while self._current().type == TokenType.COMMA:
                self._consume(TokenType.COMMA)
                args.append(self._parse_expression())
        self._consume(TokenType.PAREN_CLOSE)
        return FunctionCallNode(name, args)

    def _parse_path(
        self, is_absolute: bool, first_step: Optional[str] = None
    ) -> PathNode:
        steps: List[str] = []
        predicates: List[Optional[ASTNode]] = []
        if first_step is not None:
            steps.append(first_step)
            predicates.append(None)
            if self._current().type == TokenType.BRACKET_OPEN:
                self._consume(TokenType.BRACKET_OPEN)
                predicates[-1] = self._parse_expression()
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
                    predicates[-1] = self._parse_expression()
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
                    predicates[-1] = self._parse_expression()
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
                    predicates[-1] = self._parse_expression()
                    self._consume(TokenType.BRACKET_CLOSE)
                if self._current().type == TokenType.SLASH:
                    self._consume()
                else:
                    break
            else:
                break
        segments = [PathSegment(step, pred) for step, pred in zip(steps, predicates)]
        return PathNode(segments, is_absolute)
