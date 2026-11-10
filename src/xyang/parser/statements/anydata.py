"""
Parsing helpers for ``anydata`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING

from ..parser_context import TokenStream, ParserContext, YangTokenType
from ...ast import YangAnydataStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class AnydataStatementParser:
    """Parser for ``anydata`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers

    def parse_anydata(
        self, tokens: TokenStream, context: ParserContext
    ) -> YangAnydataStmt:
        """Parse anydata statement (RFC 7950 §7.12)."""
        tokens.consume(kw.ANYDATA)
        anydata_name = tokens.consume()
        anydata_stmt = YangAnydataStmt(name=anydata_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(anydata_stmt)
            self._parsers.parse_body(
                tokens, new_context, "anydata", error_context=f"anydata '{anydata_name}'"
            )
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers.add_to_parent_or_module(context, anydata_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return anydata_stmt
