"""
XPath parser that produces xpath_new AST nodes.

Uses the existing xpath tokenizer; builds PathNode, LiteralNode,
BinaryOpNode, UnaryOpNode, FunctionCallNode for Visitor-based resolution.
"""

from typing import List, Optional

from ..xpath.parser import XPathTokenizer
from ..xpath.ast import Token, TokenType
from ..errors import XPathSyntaxError

from .ast import (
    ExprNode,
    PathNode,
    PathSegment,
    LiteralNode,
    BinaryOpNode,
    UnaryOpNode,
    FunctionCallNode,
)

COMPARISON_OPS = {'=', '!=', '<', '>', '<=', '>='}
ADDITIVE_OPS = {'+', '-'}


class XPathParser:
    """Parser for XPath expressions producing xpath_new AST."""

    def __init__(self, expression: str):
        self.expression = expression
        tokenizer = XPathTokenizer(expression)
        self.tokens: List[Token] = tokenizer.tokenize()
        self.position = 0

    def parse(self) -> ExprNode:
        """Parse expression into an AST."""
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
        return Token(TokenType.EOF, '', 0)

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
        return (
            t.type == TokenType.IDENTIFIER
            and t.value.lower() == keyword.lower()
        )

    def _parse_expression(self) -> ExprNode:
        return self._parse_logical_or()

    def _parse_logical_or(self) -> ExprNode:
        left = self._parse_logical_and()
        while self._is_keyword('or'):
            self._consume()
            right = self._parse_logical_and()
            left = BinaryOpNode('or', left, right)
        return left

    def _parse_logical_and(self) -> ExprNode:
        left = self._parse_comparison()
        while self._is_keyword('and'):
            self._consume()
            right = self._parse_comparison()
            left = BinaryOpNode('and', left, right)
        return left

    def _parse_comparison(self) -> ExprNode:
        left = self._parse_additive()
        t = self._current()
        if t.type == TokenType.OPERATOR and t.value in COMPARISON_OPS:
            op = self._consume().value
            right = self._parse_additive()
            return BinaryOpNode(op, left, right)
        return left

    def _parse_additive(self) -> ExprNode:
        left = self._parse_multiplicative()
        while True:
            t = self._current()
            if t.type == TokenType.OPERATOR and t.value in ADDITIVE_OPS:
                op = self._consume().value
                right = self._parse_multiplicative()
                left = BinaryOpNode(op, left, right)
            else:
                break
        return left

    def _parse_multiplicative(self) -> ExprNode:
        left = self._parse_unary()
        while True:
            t = self._current()
            is_slash = (
                t.type == TokenType.SLASH
                or (t.type == TokenType.OPERATOR and t.value == '/')
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
                    left = BinaryOpNode('/', left, right)
            elif t.type == TokenType.OPERATOR and t.value == '*':
                op = self._consume().value
                right = self._parse_unary()
                left = BinaryOpNode(op, left, right)
            else:
                break
        return left

    def _parse_unary(self) -> ExprNode:
        t = self._current()
        if t.type == TokenType.OPERATOR and t.value == '-':
            self._consume()
            return UnaryOpNode('-', self._parse_unary())
        if t.type == TokenType.OPERATOR and t.value == '+':
            self._consume()
            return self._parse_unary()
        if self._is_keyword('not'):
            self._consume()
            self._consume(TokenType.PAREN_OPEN)
            operand = self._parse_expression()
            self._consume(TokenType.PAREN_CLOSE)
            return UnaryOpNode('not', operand)
        return self._parse_primary()

    def _parse_primary(self) -> ExprNode:
        t = self._current()
        if t.type == TokenType.STRING:
            value = self._consume().value
            return LiteralNode(value)
        if t.type == TokenType.NUMBER:
            raw = self._consume().value
            try:
                value = float(raw) if '.' in raw else int(raw)
            except ValueError:
                raise XPathSyntaxError(
                    f"Invalid number: {raw}",
                    position=t.position,
                    expression=self.expression,
                )
            return LiteralNode(value)
        if t.type == TokenType.IDENTIFIER:
            if self._is_keyword('true'):
                self._consume()
                if self._current().type == TokenType.PAREN_OPEN:
                    self._consume(TokenType.PAREN_OPEN)
                    self._consume(TokenType.PAREN_CLOSE)
                return LiteralNode(True)
            if self._is_keyword('false'):
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
                return FunctionCallNode('current', [])
            return self._parse_path(is_absolute=False, first_step='.')
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

    def _parse_function_call(self) -> ExprNode:
        name = self._consume().value
        self._consume(TokenType.PAREN_OPEN)
        args: List[ExprNode] = []
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
        predicates: List[Optional[ExprNode]] = []
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
                steps.append('.')
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
