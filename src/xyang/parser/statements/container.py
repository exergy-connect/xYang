"""
Parsing helpers for ``container`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangContainerStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class ContainerStatementParser:
    """Parser for ``container`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers

    def parse_container(self, tokens: TokenStream, context: ParserContext) -> YangContainerStmt:
        """Parse container statement."""
        tokens.consume(kw.CONTAINER)
        container_name = tokens.consume()  # identifier or keyword (e.g. type)
        container_stmt = YangContainerStmt(name=container_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(container_stmt)
            prev_index = -1
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                if tokens.index == prev_index:
                    raise tokens.make_error(
                        f"Infinite loop detected at token: {tokens.peek()}"
                    )
                prev_index = tokens.index
                self._parsers.dispatch_substatement(
                    tokens,
                    new_context,
                    "container",
                    error_context=f"container '{container_name}'",
                )
            if tokens.has_more() and tokens.peek_type() == YangTokenType.RBRACE:
                tokens.consume_type(YangTokenType.RBRACE)
        self._parsers.add_to_parent_or_module(context, container_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return container_stmt
