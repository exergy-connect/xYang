"""
Parsing helpers for ``augment`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING

from ..parser_context import TokenStream, ParserContext, YangTokenType
from ...ast import YangAugmentStmt, YangUsesStmt
from ...errors import YangSyntaxError
from ...identifier_ref import parse_absolute_schema_path

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class AugmentStatementParser:
    """Parser for ``augment`` statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers

    def parse_augment(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse augment statement."""
        tokens.consume(kw.AUGMENT)
        path = self._parsers.parse_string_concatenation(tokens)
        augment_path_segments: list = []
        raw = path.strip().strip('"').strip("'")
        if raw.startswith("/"):
            try:
                augment_path_segments = parse_absolute_schema_path(path)
            except ValueError as exc:
                raise YangSyntaxError(str(exc)) from exc
        aug = YangAugmentStmt(
            name="augment",
            augment_path=path,
            augment_path_segments=augment_path_segments,
        )
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(aug)
            self._parsers.parse_body(tokens, new_context, "augment", error_context="augment")
            tokens.consume_type(YangTokenType.RBRACE)
        parent = context.current_parent
        if parent is not None and isinstance(parent, YangUsesStmt):
            parent.augmentations.append(aug)
        else:
            self._parsers.add_to_parent_or_module(context, aug)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
