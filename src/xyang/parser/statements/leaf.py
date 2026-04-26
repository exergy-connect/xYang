"""
Parsing helpers for ``leaf`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangLeafStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class LeafStatementParser:
    """Parser for ``leaf`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers
        self._leaf_substatement_dispatch = {
            kw.TYPE: self._parsers.parse_type,
            kw.MANDATORY: self._parsers.parse_leaf_mandatory,
            kw.DEFAULT: self._parsers.parse_leaf_default,
            kw.DESCRIPTION: self._parsers.parse_description,
            kw.MUST: self._parsers.parse_must,
            kw.WHEN: self._parsers.parse_when,
            kw.IF_FEATURE: self._parsers.parse_if_feature_stmt,
        }

    def _parse_leaf_substatement(
        self, tokens: TokenStream, context: ParserContext, leaf_name: str
    ) -> None:
        unsupported = f"leaf '{leaf_name}'"
        handler = self._leaf_substatement_dispatch.get(self._parsers._dispatch_key(tokens))
        if handler:
            handler(tokens, context)
        elif self._parsers._is_prefixed_extension_start(tokens):
            self._parsers._parse_prefixed_extension_statement(tokens, context)
        elif self._parsers._skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

    def parse_leaf(self, tokens: TokenStream, context: ParserContext) -> YangLeafStmt:
        """Parse leaf statement."""
        tokens.consume(kw.LEAF)
        leaf_name = tokens.consume()  # identifier or keyword (e.g. type)
        leaf_stmt = YangLeafStmt(name=leaf_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(leaf_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_leaf_substatement(tokens, new_context, leaf_name)
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers._add_to_parent_or_module(context, leaf_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return leaf_stmt
