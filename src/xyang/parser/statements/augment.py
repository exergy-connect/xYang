"""
Parsing helpers for ``augment`` statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..parser_context import TokenStream, ParserContext, YangTokenType
from ...ast import YangAugmentStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class AugmentStatementParser:
    """Parser for ``augment`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers
        self._augment_body_dispatch = {
            YangTokenType.IF_FEATURE: self._parsers.parse_if_feature_stmt,
            YangTokenType.USES: self._parsers.parse_uses,
            YangTokenType.LEAF: self._parsers.parse_leaf,
            YangTokenType.LEAF_LIST: self._parsers.parse_leaf_list,
            YangTokenType.CONTAINER: self._parsers.parse_container,
            YangTokenType.LIST: self._parsers.parse_list,
            YangTokenType.CHOICE: self._parsers.parse_choice,
            YangTokenType.ANYDATA: self._parsers.parse_anydata,
            YangTokenType.ANYXML: self._parsers.parse_anyxml,
            YangTokenType.DESCRIPTION: self._parsers.parse_description,
            YangTokenType.WHEN: self._parsers.parse_when,
            YangTokenType.MUST: self._parsers.parse_must,
            YangTokenType.IDENTIFIER: self._parsers._parse_prefixed_extension_statement,
        }

    def parse_augment(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse augment statement."""
        tokens.consume_type(YangTokenType.AUGMENT)
        path = self._parsers._parse_string_concatenation(tokens)
        aug = YangAugmentStmt(name="augment", augment_path=path)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(aug)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                tt = tokens.peek_type()
                handler = self._augment_body_dispatch.get(tt)
                if handler:
                    handler(tokens, new_context)
                elif self._parsers._skip_unsupported_or_raise_unknown_stmt(
                    tokens, "augment"
                ):
                    continue
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers._add_to_parent_or_module(context, aug)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
