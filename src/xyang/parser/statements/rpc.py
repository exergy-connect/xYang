"""
Parsing helpers for ``rpc`` statements and ``input`` / ``output`` blocks (RFC 7950 §7.14).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import keywords as kw

from ..metadata_substatements import with_metadata_substatements
from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangInputStmt, YangOutputStmt, YangRpcStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class RpcStatementParser:
    """Parser for ``rpc`` and its ``input`` / ``output`` substatements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers
        self._io_substatement_dispatch = with_metadata_substatements(
            self._parsers,
            {
                kw.TYPEDEF: self._parsers.parse_typedef,
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
            },
        )
        self._rpc_substatement_dispatch = with_metadata_substatements(
            self._parsers,
            {
                kw.WHEN: self._parsers.parse_when,
                kw.MUST: self._parsers.parse_must,
                kw.INPUT: self.parse_input,
                kw.OUTPUT: self.parse_output,
                kw.IF_FEATURE: self._parsers.parse_if_feature_stmt,
            },
        )

    def _parse_io_substatement(
        self, tokens: TokenStream, context: ParserContext, block_name: str
    ) -> None:
        unsupported = f"{block_name} block"
        handler = self._parsers.substatement_handler(
            tokens, self._io_substatement_dispatch
        )
        if handler:
            handler(tokens, context)
        elif self._parsers.is_prefixed_extension_start(tokens):
            self._parsers.parse_prefixed_extension_statement(tokens, context)
        elif self._parsers.skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

    def _parse_io_block(
        self,
        tokens: TokenStream,
        context: ParserContext,
        keyword: str,
        io_stmt: YangInputStmt | YangOutputStmt,
    ) -> YangInputStmt | YangOutputStmt:
        tokens.consume(keyword)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(io_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_io_substatement(tokens, new_context, keyword)
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers.add_to_parent_or_module(context, io_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return io_stmt

    def parse_input(
        self, tokens: TokenStream, context: ParserContext
    ) -> YangInputStmt:
        """Parse ``input { ... }`` (no statement argument)."""
        result = self._parse_io_block(tokens, context, kw.INPUT, YangInputStmt(name=kw.INPUT))
        assert isinstance(result, YangInputStmt)
        return result

    def parse_output(
        self, tokens: TokenStream, context: ParserContext
    ) -> YangOutputStmt:
        """Parse ``output { ... }`` (no statement argument)."""
        result = self._parse_io_block(tokens, context, kw.OUTPUT, YangOutputStmt(name=kw.OUTPUT))
        assert isinstance(result, YangOutputStmt)
        return result

    def _parse_rpc_substatement(
        self, tokens: TokenStream, context: ParserContext, rpc_name: str
    ) -> None:
        unsupported = f"rpc '{rpc_name}'"
        handler = self._parsers.substatement_handler(
            tokens, self._rpc_substatement_dispatch
        )
        if handler:
            handler(tokens, context)
        elif self._parsers.is_prefixed_extension_start(tokens):
            self._parsers.parse_prefixed_extension_statement(tokens, context)
        elif self._parsers.skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

    def parse_rpc(self, tokens: TokenStream, context: ParserContext) -> YangRpcStmt:
        """Parse ``rpc`` statement."""
        tokens.consume(kw.RPC)
        rpc_name = tokens.consume()
        rpc_stmt = YangRpcStmt(name=rpc_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(rpc_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_rpc_substatement(tokens, new_context, rpc_name)
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers.add_to_parent_or_module(context, rpc_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return rpc_stmt
