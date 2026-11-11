"""
Parsing helpers for ``must`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangMustStmt, YangStatementWithMust

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class MustStatementParser:
    """Parsers for ``must`` statements and their substatements."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers

    def parse_must(self, tokens: TokenStream, context: ParserContext) -> YangMustStmt:
        """Parse ``must`` statement with optional ``{ error-message|description }`` body."""
        tokens.consume(kw.MUST)
        expression = self._parsers.parse_string_concatenation(tokens)
        must_stmt = YangMustStmt(expression=expression)
        must_stmt.bind_prefixes(context.module)

        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(must_stmt)
            self._parsers.parse_body(tokens, new_context, "must", error_context="must")
            tokens.consume_type(YangTokenType.RBRACE)

        if isinstance(context.current_parent, YangStatementWithMust):
            context.current_parent.must_statements.append(must_stmt)

        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return must_stmt

    def parse_must_error_message(
        self, tokens: TokenStream, context: ParserContext
    ) -> None:
        """Parse ``error-message`` under ``must``."""
        tokens.consume(kw.ERROR_MESSAGE)
        if context.current_parent and isinstance(context.current_parent, YangMustStmt):
            context.current_parent.error_message = tokens.consume_type(YangTokenType.STRING)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
