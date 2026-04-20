"""
Parsing helpers for ``feature`` and ``if-feature`` statements.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from ..parser_context import TokenStream, ParserContext, YangTokenType

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class FeatureStatementParser:
    """Parsers for feature and if-feature statements."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers

    def parse_feature_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        tokens.consume_type(YangTokenType.FEATURE)
        name = tokens.consume_type(YangTokenType.IDENTIFIER)
        context.module.features.add(name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            holder = SimpleNamespace(if_features=[])
            feat_ctx = context.push_parent(holder)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                tt = tokens.peek_type()
                if tt == YangTokenType.DESCRIPTION:
                    self._parsers.parse_optional_description(tokens, feat_ctx)
                    continue
                if tt == YangTokenType.IF_FEATURE:
                    self._parsers.parse_if_feature_stmt(tokens, feat_ctx)
                    continue
                if tt == YangTokenType.REFERENCE:
                    self._parsers.parse_reference_string_only(tokens, feat_ctx)
                    continue
                if self._parsers._skip_unsupported_or_raise_unknown_stmt(
                    tokens, f"feature '{name}'"
                ):
                    continue
            tokens.consume_type(YangTokenType.RBRACE)
            if holder.if_features:
                if name in context.module.feature_if_features:
                    raise tokens._make_error(
                        f"Duplicate if-feature block for feature {name!r}"
                    )
                context.module.feature_if_features[name] = list(holder.if_features)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_if_feature_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse if-feature; expression is stored on the parent schema node (not evaluated)."""
        tokens.consume_type(YangTokenType.IF_FEATURE)
        expression = self._parsers._parse_string_concatenation(tokens)
        parent = context.current_parent
        if parent is not None:
            feats = getattr(parent, "if_features", None)
            if isinstance(feats, list):
                feats.append(expression)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                tt = tokens.peek_type()
                if tt == YangTokenType.DESCRIPTION:
                    self._parsers.parse_optional_description(
                        tokens, context.push_parent(SimpleNamespace())
                    )
                    continue
                if tt == YangTokenType.REFERENCE:
                    self._parsers.parse_reference_string_only(tokens, context)
                    continue
                if self._parsers._skip_unsupported_or_raise_unknown_stmt(
                    tokens, "if-feature substatement"
                ):
                    continue
            tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
