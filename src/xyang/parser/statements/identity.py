"""
Parsing helpers for ``identity`` statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..parser_context import TokenStream, ParserContext, YangTokenType
from ...ast import YangIdentityStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class IdentityStatementParser:
    """Parsers for ``identity`` statements and their substatements."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers

    def _parse_identity_substatement(
        self, tokens: TokenStream, context: ParserContext, identity_name: str
    ) -> None:
        unsupported = f"identity '{identity_name}'"
        tt = tokens.peek_type()
        if tt == YangTokenType.BASE:
            self._parse_identity_base(tokens, context)
        elif tt == YangTokenType.IF_FEATURE:
            self._parsers.parse_if_feature_stmt(tokens, context)
        elif tt == YangTokenType.IDENTIFIER:
            self._parsers._parse_prefixed_extension_statement(tokens, context)
        elif self._parsers._skip_unsupported_if_present(tokens, unsupported):
            return
        else:
            raise tokens._make_error(
                f"Unknown statement in {unsupported}: {tokens.peek()!r}"
            )

    def parse_identity(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse identity statement."""
        tokens.consume_type(YangTokenType.IDENTITY)
        identity_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        identity_stmt = YangIdentityStmt(name=identity_name)
        if tokens.peek_type() == YangTokenType.LBRACE:
            tokens.consume_type(YangTokenType.LBRACE)
            new_context = context.push_parent(identity_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_identity_substatement(tokens, new_context, identity_name)
            tokens.consume_type(YangTokenType.RBRACE)
        context.module.identities[identity_name] = identity_stmt
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def _parse_identity_base(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse base substatement inside identity."""
        tokens.consume_type(YangTokenType.BASE)
        base_name = self._parsers._consume_qname_from_identifier(tokens)
        parent = context.current_parent
        if isinstance(parent, YangIdentityStmt):
            parent.bases.append(base_name)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
