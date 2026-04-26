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
        self._container_substatement_dispatch = {
            kw.DESCRIPTION: self._parsers.parse_description,
            kw.PRESENCE: self._parsers.parse_presence,
            kw.WHEN: self._parsers.parse_when,
            kw.MUST: self._parsers.parse_must,
            kw.LEAF: self._parsers.parse_leaf,
            kw.CONTAINER: self._parsers.parse_container,
            kw.LIST: self._parsers.parse_list,
            kw.LEAF_LIST: self._parsers.parse_leaf_list,
            kw.USES: self._parsers.parse_uses,
            kw.CHOICE: self._parsers.parse_choice,
            kw.IF_FEATURE: self._parsers.parse_if_feature_stmt,
            kw.ANYDATA: self._parsers.parse_anydata,
            kw.ANYXML: self._parsers.parse_anyxml,
        }

    def _parse_container_substatement(
        self, tokens: TokenStream, context: ParserContext, container_name: str
    ) -> None:
        unsupported = f"container '{container_name}'"
        handler = self._container_substatement_dispatch.get(self._parsers._dispatch_key(tokens))
        if handler:
            handler(tokens, context)
        elif self._parsers._is_prefixed_extension_start(tokens):
            self._parsers._parse_prefixed_extension_statement(tokens, context)
        elif self._parsers._skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

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
                    raise tokens._make_error(
                        f"Infinite loop detected at token: {tokens.peek()}"
                    )
                prev_index = tokens.index
                self._parse_container_substatement(tokens, new_context, container_name)
            if tokens.has_more() and tokens.peek_type() == YangTokenType.RBRACE:
                tokens.consume_type(YangTokenType.RBRACE)
        self._parsers._add_to_parent_or_module(context, container_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return container_stmt
