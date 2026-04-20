"""
Parsing helpers for ``when`` statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangStatementWithWhen, YangWhenStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class WhenStatementParser:
    """Parsers for ``when`` statements and their substatements."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers

    def parse_when(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse ``when`` with optional ``{ description; }`` body."""
        tokens.consume_type(YangTokenType.WHEN)
        condition = self._parsers._parse_string_concatenation(tokens)
        when_stmt = YangWhenStmt(expression=condition)
        parent_for_when = context.current_parent

        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(when_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                token_type = tokens.peek_type()
                if token_type == YangTokenType.DESCRIPTION:
                    self._parsers.parse_description(tokens, new_context)
                elif self._parsers._skip_unsupported_or_raise_unknown_stmt(
                    tokens, "when"
                ):
                    continue
            tokens.consume_type(YangTokenType.RBRACE)

        if parent_for_when and isinstance(parent_for_when, YangStatementWithWhen):
            parent_for_when.when = when_stmt
        tokens.consume_if_type(YangTokenType.SEMICOLON)
