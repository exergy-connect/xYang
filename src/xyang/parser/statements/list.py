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
        self._list_substatement_dispatch = {
            kw.KEY: self._parsers.parse_list_key,
            kw.MIN_ELEMENTS: self._parsers.parse_min_elements,
            kw.MAX_ELEMENTS: self._parsers.parse_max_elements,
            kw.ORDERED_BY: self._parsers.parse_ordered_by,
            kw.DESCRIPTION: self._parsers.parse_description,
            kw.WHEN: self._parsers.parse_when,
            kw.LEAF: self._parsers.parse_leaf,
            kw.CONTAINER: self._parsers.parse_container,
            kw.LIST: self._parsers.parse_list,
            kw.LEAF_LIST: self._parsers.parse_leaf_list,
            kw.MUST: self._parsers.parse_must,
            kw.USES: self._parsers.parse_uses,
            kw.CHOICE: self._parsers.parse_choice,
            kw.IF_FEATURE: self._parsers.parse_if_feature_stmt,
            kw.ANYDATA: self._parsers.parse_anydata,
            kw.ANYXML: self._parsers.parse_anyxml,
        }

    def _parse_list_substatement(
        self, tokens: TokenStream, context: ParserContext, list_name: str
    ) -> None:
        unsupported = f"list '{list_name}'"
        handler = self._parsers._substatement_handler(tokens, self._list_substatement_dispatch)
        if handler:
            handler(tokens, context)
        elif self._parsers._is_prefixed_extension_start(tokens):
            self._parsers._parse_prefixed_extension_statement(tokens, context)
        elif self._parsers._skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

    def parse_list(self, tokens: TokenStream, context: ParserContext) -> YangListStmt:
        """Parse list statement."""
        tokens.consume(kw.LIST)
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
