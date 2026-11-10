"""
Parsing helpers for ``list`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangListStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class ListStatementParser:
    """Parser for ``list`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers

    def parse_list(self, tokens: TokenStream, context: ParserContext) -> YangListStmt:
        """Parse list statement."""
        tokens.consume(kw.LIST)
        list_name = tokens.consume()  # identifier or keyword
        list_stmt = YangListStmt(name=list_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(list_stmt)
            self._parsers.parse_body(
                tokens, new_context, "list", error_context=f"list '{list_name}'"
            )
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers.add_to_parent_or_module(context, list_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return list_stmt
