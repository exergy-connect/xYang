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
        self._anydata_body_dispatch = {
            kw.DESCRIPTION: self._parsers.parse_description,
            kw.WHEN: self._parsers.parse_when,
            kw.MUST: self._parsers.parse_must,
            kw.IF_FEATURE: self._parsers.parse_if_feature_stmt,
            kw.MANDATORY: self._parsers.parse_leaf_mandatory,
        }

    def parse_anydata(
        self, tokens: TokenStream, context: ParserContext
    ) -> YangAnydataStmt:
        """Parse anydata statement (RFC 7950 §7.12)."""
        tokens.consume(kw.ANYDATA)
        anydata_name = tokens.consume()
        anydata_stmt = YangAnydataStmt(name=anydata_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(anydata_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                handler = self._parsers._substatement_handler(tokens, self._anydata_body_dispatch)
                if handler:
                    handler(tokens, new_context)
                elif self._parsers._skip_unsupported_or_raise_unknown_stmt(
                    tokens, f"anydata '{anydata_name}'"
                ):
                    continue
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers._add_to_parent_or_module(context, anydata_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return anydata_stmt
