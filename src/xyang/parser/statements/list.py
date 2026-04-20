"""
Parsing helpers for ``list`` statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangListStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class ListStatementParser:
    """Parser for ``list`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers
        self._list_substatement_dispatch = {
            YangTokenType.KEY: self._parsers.parse_list_key,
            YangTokenType.MIN_ELEMENTS: self._parsers.parse_min_elements,
            YangTokenType.MAX_ELEMENTS: self._parsers.parse_max_elements,
            YangTokenType.ORDERED_BY: self._parsers.parse_ordered_by,
            YangTokenType.DESCRIPTION: self._parsers.parse_description,
            YangTokenType.WHEN: self._parsers.parse_when,
            YangTokenType.LEAF: self._parsers.parse_leaf,
            YangTokenType.CONTAINER: self._parsers.parse_container,
            YangTokenType.LIST: self._parsers.parse_list,
            YangTokenType.LEAF_LIST: self._parsers.parse_leaf_list,
            YangTokenType.MUST: self._parsers.parse_must,
            YangTokenType.USES: self._parsers.parse_uses,
            YangTokenType.CHOICE: self._parsers.parse_choice,
            YangTokenType.IF_FEATURE: self._parsers.parse_if_feature_stmt,
            YangTokenType.ANYDATA: self._parsers.parse_anydata,
            YangTokenType.ANYXML: self._parsers.parse_anyxml,
            YangTokenType.IDENTIFIER: self._parsers._parse_prefixed_extension_statement,
        }

    def _parse_list_substatement(
        self, tokens: TokenStream, context: ParserContext, list_name: str
    ) -> None:
        unsupported = f"list '{list_name}'"
        handler = self._list_substatement_dispatch.get(tokens.peek_type())
        if handler:
            handler(tokens, context)
        elif self._parsers._skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

    def parse_list(self, tokens: TokenStream, context: ParserContext) -> YangListStmt:
        """Parse list statement."""
        tokens.consume_type(YangTokenType.LIST)
        list_name = tokens.consume()  # identifier or keyword
        list_stmt = YangListStmt(name=list_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(list_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_list_substatement(tokens, new_context, list_name)
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers._add_to_parent_or_module(context, list_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return list_stmt
