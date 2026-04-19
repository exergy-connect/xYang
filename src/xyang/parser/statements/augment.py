"""
Parsing helpers for ``augment`` statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..parser_context import TokenStream, ParserContext, YangTokenType
from ..statement_dispatch import StatementDispatchSpec
from ...ast import YangAugmentStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class AugmentStatementParser:
    """Parser for ``augment`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers

    def parse_augment(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse augment statement."""
        tokens.consume_type(YangTokenType.AUGMENT)
        path = self._parsers._parse_string_concatenation(tokens)
        aug = YangAugmentStmt(name="augment", augment_path=path)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(aug)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parsers._parse_statement(
                    tokens,
                    new_context,
                    StatementDispatchSpec(
                        registry_prefix="augment",
                        unsupported_context="augment",
                    ),
                )
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers._add_to_parent_or_module(context, aug)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
