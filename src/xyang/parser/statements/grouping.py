"""
Parsing helpers for ``grouping`` statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import keywords as kw

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangContainerStmt, YangGroupingStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class GroupingStatementParser:
    """Parser for ``grouping`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers

    def parse_grouping(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse grouping statement."""
        tokens.consume(kw.GROUPING)
        grouping_name = self._parsers.parse_identifier_argument(tokens, "grouping")
        grouping_stmt = YangGroupingStmt(name=grouping_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(grouping_stmt)
            self._parsers.parse_body(
                tokens, new_context, "grouping", error_context=f"grouping '{grouping_name}'"
            )
            tokens.consume_type(YangTokenType.RBRACE)
        parent = context.current_parent
        if isinstance(parent, YangContainerStmt):
            parent.groupings[grouping_name] = grouping_stmt
        else:
            context.module.groupings[grouping_name] = grouping_stmt
        tokens.consume_if_type(YangTokenType.SEMICOLON)
