"""
Parsing helpers for ``refine`` statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ..statement_dispatch import StatementDispatchSpec
from ...ast import YangRefineStmt, YangUsesStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers
    from ..statement_registry import StatementRegistry


class RefineStatementParser:
    """Parsers and registration helpers for ``refine`` statements."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers

    def register_uses_refine_handler(self, registry: StatementRegistry) -> None:
        """Register ``uses:refine`` handler."""
        registry.register("uses:refine", self._parsers.parse_refine)

    def register_refine_body_handlers(self, registry: StatementRegistry) -> None:
        """Register all supported ``refine`` substatement handlers."""
        registry.register("refine:must", self._parsers.parse_must)
        registry.register("refine:description", self._parsers.parse_description)
        registry.register("refine:min-elements", self._parsers.parse_min_elements)
        registry.register("refine:max-elements", self._parsers.parse_max_elements)
        registry.register("refine:ordered-by", self._parsers.parse_ordered_by)
        registry.register("refine:mandatory", self._parsers.parse_refine_mandatory)
        registry.register("refine:default", self._parsers.parse_refine_default)
        registry.register("refine:if-feature", self._parsers.parse_if_feature_stmt)
        registry.register("refine:type", self._parsers.parse_type)

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
                self._parsers._parse_statement(
                    tokens,
                    new_context,
                    StatementDispatchSpec(
                        registry_prefix="refine",
                        unsupported_context=f"refine '{target_path}'",
                    ),
                )
            tokens.consume_type(YangTokenType.RBRACE)
        if context.current_parent and isinstance(context.current_parent, YangUsesStmt):
            context.current_parent.refines.append(refine_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
