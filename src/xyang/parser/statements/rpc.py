"""
Parsing helpers for ``rpc`` statements and ``input`` / ``output`` blocks (RFC 7950 §7.14).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import keywords as kw

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangInputStmt, YangOutputStmt, YangRpcStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class RpcStatementParser:
    """Parser for ``rpc`` and its ``input`` / ``output`` substatements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers

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
            self._parsers.parse_body(
                tokens, new_context, keyword, error_context=f"{keyword} block"
            )
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

    def parse_rpc(self, tokens: TokenStream, context: ParserContext) -> YangRpcStmt:
        """Parse ``rpc`` statement."""
        tokens.consume(kw.RPC)
        rpc_name = tokens.consume()
        rpc_stmt = YangRpcStmt(name=rpc_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(rpc_stmt)
            self._parsers.parse_body(
                tokens, new_context, "rpc", error_context=f"rpc '{rpc_name}'"
            )
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers.add_to_parent_or_module(context, rpc_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return rpc_stmt
