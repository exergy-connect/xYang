"""
Parsing helpers for ``identity`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING

from ..parser_context import TokenStream, ParserContext, YangTokenType
from ...ast import YangIdentityStmt
from ...identifier_ref import identifier_ref

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class IdentityStatementParser:
    """Parsers for ``identity`` statements and their substatements."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers

    def parse_identity(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse identity statement."""
        tokens.consume(kw.IDENTITY)
        identity_name = self._parsers.parse_identifier_argument(tokens, "identity")
        identity_stmt = YangIdentityStmt(name=identity_name)
        if tokens.has_more() and tokens.peek_type() == YangTokenType.LBRACE:
            tokens.consume_type(YangTokenType.LBRACE)
            new_context = context.push_parent(identity_stmt)
            self._parsers.parse_body(
                tokens, new_context, "identity", error_context=f"identity '{identity_name}'"
            )
            tokens.consume_type(YangTokenType.RBRACE)
        context.module.identities[identity_name] = identity_stmt
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def _parse_identity_base(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse base substatement inside identity."""
        tokens.consume(kw.BASE)
        base_prefix, base_name = self._parsers.consume_identifier_ref(tokens)
        parent = context.current_parent
        if isinstance(parent, YangIdentityStmt):
            parent.bases.append(identifier_ref(base_name, base_prefix))
        tokens.consume_if_type(YangTokenType.SEMICOLON)
