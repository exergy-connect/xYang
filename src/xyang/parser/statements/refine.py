"""
Parsing helpers for ``refine`` statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangRefineStmt, YangUsesStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class RefineStatementParser:
    """Parsers for ``refine`` statements."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers

    def _parse_refine_substatement(
        self, tokens: TokenStream, context: ParserContext, target_path: str
    ) -> None:
        """One substatement inside ``refine { ... }`` (no ``refine:*`` registry keys)."""
        unsupported = f"refine '{target_path}'"
        tt = tokens.peek_type()
        if tt == YangTokenType.MUST:
            self._parsers.parse_must(tokens, context)
        elif tt == YangTokenType.DESCRIPTION:
            self._parsers.parse_description(tokens, context)
        elif tt == YangTokenType.MIN_ELEMENTS:
            self._parsers.parse_min_elements(tokens, context)
        elif tt == YangTokenType.MAX_ELEMENTS:
            self._parsers.parse_max_elements(tokens, context)
        elif tt == YangTokenType.ORDERED_BY:
            self._parsers.parse_ordered_by(tokens, context)
        elif tt == YangTokenType.MANDATORY:
            self._parse_refine_mandatory(tokens, context)
        elif tt == YangTokenType.DEFAULT:
            self._parse_refine_default(tokens, context)
        elif tt == YangTokenType.IF_FEATURE:
            self._parsers.parse_if_feature_stmt(tokens, context)
        elif tt == YangTokenType.TYPE:
            self._parsers.parse_type(tokens, context)
        elif tt == YangTokenType.IDENTIFIER:
            self._parsers._parse_prefixed_extension_statement(tokens, context)
        elif self._parsers._skip_unsupported_if_present(tokens, unsupported):
            return
        else:
            raise tokens._make_error(
                f"Unknown statement in {unsupported}: {tokens.peek()!r}"
            )

    def _parse_refine_mandatory(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse mandatory in refine (RFC 7950 section 7.13.2: leaf / choice target)."""
        tokens.consume_type(YangTokenType.MANDATORY)
        _, tt = tokens.consume_oneof([YangTokenType.TRUE, YangTokenType.FALSE])
        parent = context.current_parent
        if isinstance(parent, YangRefineStmt):
            parent.refined_mandatory = tt == YangTokenType.TRUE
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def _parse_refine_default(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse default in refine (RFC 7950 section 7.13.2; applied to expanded leaf / leaf-list)."""
        tokens.consume_type(YangTokenType.DEFAULT)
        parent = context.current_parent
        if isinstance(parent, YangRefineStmt):
            parent.refined_defaults.append(self._parsers._parse_default_value_tokens(tokens))
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_refine(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse refine statement (supports descendant paths ``a/b``)."""
        tokens.consume_type(YangTokenType.REFINE)
        parts = [tokens.consume()]
        while tokens.peek_type() == YangTokenType.SLASH:
            tokens.consume_type(YangTokenType.SLASH)
            parts.append(tokens.consume())
        target_path = "/".join(parts)
        refine_stmt = YangRefineStmt(name="refine", target_path=target_path)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(refine_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_refine_substatement(tokens, new_context, target_path)
            tokens.consume_type(YangTokenType.RBRACE)
        if context.current_parent and isinstance(context.current_parent, YangUsesStmt):
            context.current_parent.refines.append(refine_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
