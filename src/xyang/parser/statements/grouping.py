"""
Parsing helpers for ``grouping`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangGroupingStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class GroupingStatementParser:
    """Parser for ``grouping`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers
        self._grouping_substatement_dispatch = {
            kw.DESCRIPTION: self._parsers.parse_description,
            kw.CHOICE: self._parsers.parse_choice,
            kw.CONTAINER: self._parsers.parse_container,
            kw.LIST: self._parsers.parse_list,
            kw.LEAF: self._parsers.parse_leaf,
            kw.LEAF_LIST: self._parsers.parse_leaf_list,
            kw.USES: self._parsers.parse_uses,
            kw.IF_FEATURE: self._parsers.parse_if_feature_stmt,
            kw.WHEN: self._parsers.parse_when,
            kw.MUST: self._parsers.parse_must,
            kw.ANYDATA: self._parsers.parse_anydata,
            kw.ANYXML: self._parsers.parse_anyxml,
        }

    def _parse_grouping_substatement(
        self, tokens: TokenStream, context: ParserContext, grouping_name: str
    ) -> None:
        unsupported = f"grouping '{grouping_name}'"
        handler = self._parsers._substatement_handler(tokens, self._grouping_substatement_dispatch)
        if handler:
            handler(tokens, context)
        elif self._parsers._is_prefixed_extension_start(tokens):
            self._parsers._parse_prefixed_extension_statement(tokens, context)
        elif self._parsers._skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

    def parse_grouping(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse grouping statement."""
        tokens.consume(kw.GROUPING)
        grouping_name = tokens.consume()  # identifier or keyword
        grouping_stmt = YangGroupingStmt(name=grouping_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(grouping_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_grouping_substatement(tokens, new_context, grouping_name)
            tokens.consume_type(YangTokenType.RBRACE)
        context.module.groupings[grouping_name] = grouping_stmt
        tokens.consume_if_type(YangTokenType.SEMICOLON)
