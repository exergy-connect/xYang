"""
Parsing helpers for ``anyxml`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING

from ..parser_context import TokenStream, ParserContext, YangTokenType
from ...ast import YangAnyxmlStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class AnyxmlStatementParser:
    """Parser for ``anyxml`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers

    def parse_anyxml(
        self, tokens: TokenStream, context: ParserContext
    ) -> YangAnyxmlStmt:
        """Parse anyxml statement (RFC 7950 §7.11)."""
        tokens.consume(kw.ANYXML)
        anyxml_name = self._parsers.parse_identifier_argument(tokens, "anyxml")
        anyxml_stmt = YangAnyxmlStmt(name=anyxml_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(anyxml_stmt)
            self._parsers.parse_body(
                tokens, new_context, "anyxml", error_context=f"anyxml '{anyxml_name}'"
            )
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers.add_to_parent_or_module(context, anyxml_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return anyxml_stmt
