"""
Parsing helpers for ``when`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

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
        tokens.consume(kw.WHEN)
        condition = self._parsers.parse_string_concatenation(tokens)
        when_stmt = YangWhenStmt(expression=condition)
        when_stmt.bind_prefixes(context.module)
        parent_for_when = context.current_parent

        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(when_stmt)
            self._parsers.parse_body(tokens, new_context, "when", error_context="when")
            tokens.consume_type(YangTokenType.RBRACE)

        if parent_for_when and isinstance(parent_for_when, YangStatementWithWhen):
            parent_for_when.when = when_stmt
        tokens.consume_if_type(YangTokenType.SEMICOLON)
