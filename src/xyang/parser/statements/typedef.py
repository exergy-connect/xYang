"""
Parsing helpers for ``typedef`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING, Optional

from ..parser_context import TokenStream, ParserContext, YangTokenType
from ...ast import YangTypedefStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class TypedefStatementParser:
    """Parser for ``typedef`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers
        self._typedef_body_dispatch = {
            kw.TYPE: self._parsers.parse_type,
            kw.DESCRIPTION: self._parsers.parse_description,
        }

    def parse_typedef(
        self, tokens: TokenStream, context: ParserContext
    ) -> Optional[YangTypedefStmt]:
        """Parse typedef statement."""
        tokens.consume(kw.TYPEDEF)
        typedef_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        typedef_stmt = YangTypedefStmt(name=typedef_name)
        unsupported_ctx = f"typedef '{typedef_name}'"

        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(typedef_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                tt = self._parsers._dispatch_key(tokens)
                handler = self._typedef_body_dispatch.get(tt)
                if handler:
                    handler(tokens, new_context)
                elif self._parsers._skip_unsupported_or_raise_unknown_stmt(
                    tokens, unsupported_ctx
                ):
                    continue
            tokens.consume_type(YangTokenType.RBRACE)

        context.module.typedefs[typedef_name] = typedef_stmt
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return None
