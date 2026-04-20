"""
Parsing helpers for ``grouping`` statements.
"""

from __future__ import annotations

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
            YangTokenType.DESCRIPTION: self._parsers.parse_description,
            YangTokenType.CHOICE: self._parsers.parse_choice,
            YangTokenType.CONTAINER: self._parsers.parse_container,
            YangTokenType.LIST: self._parsers.parse_list,
            YangTokenType.LEAF: self._parsers.parse_leaf,
            YangTokenType.LEAF_LIST: self._parsers.parse_leaf_list,
            YangTokenType.USES: self._parsers.parse_uses,
            YangTokenType.IF_FEATURE: self._parsers.parse_if_feature_stmt,
            YangTokenType.WHEN: self._parsers.parse_when,
            YangTokenType.MUST: self._parsers.parse_must,
            YangTokenType.ANYDATA: self._parsers.parse_anydata,
            YangTokenType.ANYXML: self._parsers.parse_anyxml,
            YangTokenType.IDENTIFIER: self._parsers._parse_prefixed_extension_statement,
        }

    def _parse_grouping_substatement(
        self, tokens: TokenStream, context: ParserContext, grouping_name: str
    ) -> None:
        unsupported = f"grouping '{grouping_name}'"
        handler = self._grouping_substatement_dispatch.get(tokens.peek_type())
        if handler:
            handler(tokens, context)
        elif self._parsers._skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

    def parse_grouping(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse grouping statement."""
        tokens.consume_type(YangTokenType.GROUPING)
        grouping_name = tokens.consume()  # identifier or keyword
        grouping_stmt = YangGroupingStmt(name=grouping_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(grouping_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_grouping_substatement(tokens, new_context, grouping_name)
            tokens.consume_type(YangTokenType.RBRACE)
        context.module.groupings[grouping_name] = grouping_stmt
        tokens.consume_if_type(YangTokenType.SEMICOLON)
