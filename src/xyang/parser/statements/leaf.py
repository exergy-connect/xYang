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

    def parse_leaf(self, tokens: TokenStream, context: ParserContext) -> YangLeafStmt:
        """Parse leaf statement."""
        tokens.consume(kw.LEAF)
        leaf_name = self._parsers.parse_identifier_argument(tokens, "leaf")
        leaf_stmt = YangLeafStmt(name=leaf_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(leaf_stmt)
            self._parsers.parse_body(
                tokens, new_context, "leaf", error_context=f"leaf '{leaf_name}'"
            )
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers.add_to_parent_or_module(context, leaf_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return leaf_stmt
