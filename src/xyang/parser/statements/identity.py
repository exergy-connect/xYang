"""
Parsing helpers for ``identity`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING

from ..parser_context import TokenStream, ParserContext, YangTokenType
from ...ast import YangIdentityStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class IdentityStatementParser:
    """Parsers for ``identity`` statements and their substatements."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers
        self._identity_substatement_dispatch = {
            kw.BASE: self._parse_identity_base,
            kw.IF_FEATURE: self._parsers.parse_if_feature_stmt,
        }

    def _parse_identity_substatement(
        self, tokens: TokenStream, context: ParserContext, identity_name: str
    ) -> None:
        unsupported = f"identity '{identity_name}'"
        tt = self._parsers._dispatch_key(tokens)
        handler = self._identity_substatement_dispatch.get(tt)
        if handler:
            handler(tokens, context)
        elif self._parsers._is_prefixed_extension_start(tokens):
            self._parsers._parse_prefixed_extension_statement(tokens, context)
        elif self._parsers._skip_unsupported_or_raise_unknown_stmt(tokens, unsupported):
            return

    def parse_identity(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse identity statement."""
        tokens.consume(kw.IDENTITY)
        identity_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        identity_stmt = YangIdentityStmt(name=identity_name)
        if tokens.has_more() and tokens.peek_type() == YangTokenType.LBRACE:
            tokens.consume_type(YangTokenType.LBRACE)
            new_context = context.push_parent(identity_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_identity_substatement(tokens, new_context, identity_name)
            tokens.consume_type(YangTokenType.RBRACE)
        context.module.identities[identity_name] = identity_stmt
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def _parse_identity_base(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse base substatement inside identity."""
        tokens.consume(kw.BASE)
        base_name = self._parsers._consume_qname_from_identifier(tokens)
        parent = context.current_parent
        if isinstance(parent, YangIdentityStmt):
            parent.bases.append(base_name)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
