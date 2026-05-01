"""
Parsing helpers for ``leaf-list`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangLeafListStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class LeafListStatementParser:
    """Parser for ``leaf-list`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers
        self._leaf_list_substatement_dispatch = {
            kw.TYPE: self._parsers.parse_type,
            kw.MIN_ELEMENTS: self._parsers.parse_min_elements,
            kw.MAX_ELEMENTS: self._parsers.parse_max_elements,
            kw.ORDERED_BY: self._parsers.parse_ordered_by,
            kw.DESCRIPTION: self._parsers.parse_description,
            kw.WHEN: self._parsers.parse_when,
            kw.MUST: self._parsers.parse_must,
            kw.IF_FEATURE: self._parsers.parse_if_feature_stmt,
        }

    def _parse_leaf_list_substatement(
        self, tokens: TokenStream, context: ParserContext, leaf_list_name: str
    ) -> None:
        unsupported = f"leaf-list '{leaf_list_name}'"
        handler = self._parsers._substatement_handler(tokens, self._leaf_list_substatement_dispatch)
        if handler:
            handler(tokens, context)
        elif self._parsers._is_prefixed_extension_start(tokens):
            self._parsers._parse_prefixed_extension_statement(tokens, context)
        elif self._parsers._skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

    def parse_leaf_list(
        self, tokens: TokenStream, context: ParserContext
    ) -> YangLeafListStmt:
        """Parse leaf-list statement."""
        tokens.consume(kw.LEAF_LIST)
        leaf_list_name = tokens.consume()  # identifier or keyword
        leaf_list_stmt = YangLeafListStmt(name=leaf_list_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(leaf_list_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_leaf_list_substatement(tokens, new_context, leaf_list_name)
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers._add_to_parent_or_module(context, leaf_list_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return leaf_list_stmt
