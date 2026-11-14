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

    def parse_leaf_list(
        self, tokens: TokenStream, context: ParserContext
    ) -> YangLeafListStmt:
        """Parse leaf-list statement."""
        tokens.consume(kw.LEAF_LIST)
        leaf_list_name = self._parsers.parse_identifier_argument(tokens, "leaf-list")
        leaf_list_stmt = YangLeafListStmt(name=leaf_list_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(leaf_list_stmt)
            self._parsers.parse_body(
                tokens,
                new_context,
                "leaf-list",
                error_context=f"leaf-list '{leaf_list_name}'",
            )
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers.add_to_parent_or_module(context, leaf_list_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return leaf_list_stmt
