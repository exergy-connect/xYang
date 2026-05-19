"""
Parsing helpers for ``augment`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING

from ..metadata_substatements import with_data_node_substatements
from ..parser_context import TokenStream, ParserContext, YangTokenType
from ...ast import YangAugmentStmt, YangUsesStmt

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class AugmentStatementParser:
    """Parser for ``augment`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers
        self._augment_body_dispatch = with_data_node_substatements(
            self._parsers,
            {
                kw.IF_FEATURE: self._parsers.parse_if_feature_stmt,
                kw.USES: self._parsers.parse_uses,
                kw.LEAF: self._parsers.parse_leaf,
                kw.LEAF_LIST: self._parsers.parse_leaf_list,
                kw.CONTAINER: self._parsers.parse_container,
                kw.LIST: self._parsers.parse_list,
                kw.CHOICE: self._parsers.parse_choice,
                kw.CASE: self._parsers.parse_case,
                kw.ANYDATA: self._parsers.parse_anydata,
                kw.ANYXML: self._parsers.parse_anyxml,
                kw.WHEN: self._parsers.parse_when,
                kw.MUST: self._parsers.parse_must,
            },
        )

    def parse_augment(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse augment statement."""
        tokens.consume(kw.AUGMENT)
        path = self._parsers._parse_string_concatenation(tokens)
        aug = YangAugmentStmt(name="augment", augment_path=path)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(aug)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                handler = self._parsers._substatement_handler(tokens, self._augment_body_dispatch)
                if handler:
                    handler(tokens, new_context)
                elif self._parsers._skip_unsupported_or_raise_unknown_stmt(
                    tokens, "augment"
                ):
                    continue
            tokens.consume_type(YangTokenType.RBRACE)
        parent = context.current_parent
        if parent is not None and isinstance(parent, YangUsesStmt):
            parent.augmentations.append(aug)
        else:
            self._parsers._add_to_parent_or_module(context, aug)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
