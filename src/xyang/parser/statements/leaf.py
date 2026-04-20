"""
Parsing helpers for ``leaf`` statements.
"""

from __future__ import annotations

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
            YangTokenType.TYPE: self._parsers.parse_type,
            YangTokenType.MANDATORY: self._parsers.parse_leaf_mandatory,
            YangTokenType.DEFAULT: self._parsers.parse_leaf_default,
            YangTokenType.DESCRIPTION: self._parsers.parse_description,
            YangTokenType.MUST: self._parsers.parse_must,
            YangTokenType.WHEN: self._parsers.parse_when,
            YangTokenType.IF_FEATURE: self._parsers.parse_if_feature_stmt,
            YangTokenType.IDENTIFIER: self._parsers._parse_prefixed_extension_statement,
        }

    def _parse_leaf_substatement(
        self, tokens: TokenStream, context: ParserContext, leaf_name: str
    ) -> None:
        unsupported = f"leaf '{leaf_name}'"
        handler = self._leaf_substatement_dispatch.get(tokens.peek_type())
        if handler:
            handler(tokens, context)
        elif self._parsers._skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

    def parse_leaf(self, tokens: TokenStream, context: ParserContext) -> YangLeafStmt:
        """Parse leaf statement."""
        tokens.consume_type(YangTokenType.LEAF)
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
