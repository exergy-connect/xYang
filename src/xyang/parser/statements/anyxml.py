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
        self._anyxml_body_dispatch = {
            kw.DESCRIPTION: self._parsers.parse_description,
            kw.WHEN: self._parsers.parse_when,
            kw.MUST: self._parsers.parse_must,
            kw.IF_FEATURE: self._parsers.parse_if_feature_stmt,
            kw.MANDATORY: self._parsers.parse_leaf_mandatory,
        }

    def parse_anyxml(
        self, tokens: TokenStream, context: ParserContext
    ) -> YangAnyxmlStmt:
        """Parse anyxml statement (RFC 7950 §7.11)."""
        tokens.consume(kw.ANYXML)
        anyxml_name = tokens.consume()
        anyxml_stmt = YangAnyxmlStmt(name=anyxml_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(anyxml_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                tt = self._parsers._dispatch_key(tokens)
                handler = self._anyxml_body_dispatch.get(tt)
                if handler:
                    handler(tokens, new_context)
                elif self._parsers._skip_unsupported_or_raise_unknown_stmt(
                    tokens, f"anyxml '{anyxml_name}'"
                ):
                    continue
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers._add_to_parent_or_module(context, anyxml_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return anyxml_stmt
