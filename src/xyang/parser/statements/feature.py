"""
Parsing helpers for ``feature`` and ``if-feature`` statements.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from ..parser_context import TokenStream, ParserContext, YangTokenType
from ..statement_dispatch import StatementDispatchSpec

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
                if tokens.peek_type() == YangTokenType.DESCRIPTION:
                    self._parsers.parse_optional_description(tokens, feat_ctx)
                    continue
                self._parsers._parse_statement(
                    tokens,
                    feat_ctx,
                    StatementDispatchSpec(
                        registry_prefix="feature",
                        unsupported_context=f"feature '{name}'",
                        allowed_keywords=frozenset({"if-feature", "reference"}),
                        try_skip_when_disallowed=True,
                    ),
                )
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
                if tokens.peek_type() == YangTokenType.DESCRIPTION:
                    self._parsers.parse_optional_description(
                        tokens, context.push_parent(SimpleNamespace())
                    )
                    continue
                self._parsers._parse_statement(
                    tokens,
                    context,
                    StatementDispatchSpec(
                        registry_prefix="if_feature",
                        unsupported_context="if-feature substatement",
                        allowed_keywords=frozenset({"reference"}),
                        try_skip_when_disallowed=True,
                    ),
                )
            tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
