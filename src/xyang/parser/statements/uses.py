"""
Parsing helpers for ``uses`` statements.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ..parser_context import TokenStream, ParserContext, YangTokenType
from ...ast import YangUsesStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class UsesStatementParser:
    """Parser for ``uses`` statements."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers

    def _parse_uses_substatement(
        self, tokens: TokenStream, context: ParserContext, grouping_name: str
    ) -> None:
        """One substatement inside ``uses { ... }``."""
        unsupported = f"uses '{grouping_name}'"
        tt = tokens.peek_type()
        if tt == YangTokenType.DESCRIPTION:
            self._parsers.parse_description(tokens, context)
        elif tt == YangTokenType.WHEN:
            self._parsers.parse_when(tokens, context)
        elif tt == YangTokenType.IF_FEATURE:
            self._parsers.parse_if_feature_stmt(tokens, context)
        elif tt == YangTokenType.REFINE:
            self._parsers.parse_refine(tokens, context)
        elif tt == YangTokenType.IDENTIFIER:
            self._parsers._parse_prefixed_extension_statement(tokens, context)
        elif self._parsers._skip_unsupported_if_present(tokens, unsupported):
            return
        else:
            raise tokens._make_error(
                f"Unknown statement in {unsupported}: {tokens.peek()!r}"
            )

    def parse_uses(
        self, tokens: TokenStream, context: ParserContext
    ) -> Optional[YangUsesStmt]:
        """Parse uses statement.

        Uses statements are stored temporarily and expanded after all groupings
        have been parsed. A YangUsesStmt node is created as a placeholder.
        """
        tokens.consume_type(YangTokenType.USES)
        if tokens.peek_type() == YangTokenType.IDENTIFIER:
            grouping_name = self._parsers._consume_qname_from_identifier(tokens)
        else:
            grouping_name = tokens.consume()
        uses_stmt = YangUsesStmt(name="uses", grouping_name=grouping_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(uses_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_uses_substatement(tokens, new_context, grouping_name)
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers._add_to_parent_or_module(context, uses_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return uses_stmt
