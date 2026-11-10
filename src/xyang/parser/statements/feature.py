"""
Parsing helpers for ``feature`` and ``if-feature`` statements.
"""

from __future__ import annotations

from .. import keywords as kw

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
        tokens.consume(kw.FEATURE)
        name = tokens.consume_type(YangTokenType.IDENTIFIER)
        context.module.features.add(name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            holder = SimpleNamespace(if_features=[], description="", reference="")
            feat_ctx = context.push_parent(holder)
            self._parsers.parse_body(
                tokens, feat_ctx, "feature", error_context=f"feature '{name}'"
            )
            tokens.consume_type(YangTokenType.RBRACE)
            if holder.if_features:
                if name in context.module.feature_if_features:
                    raise tokens.make_error(
                        f"Duplicate if-feature block for feature {name!r}"
                    )
                context.module.feature_if_features[name] = list(holder.if_features)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_if_feature_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse if-feature; expression is stored on the parent schema node (not evaluated)."""
        tokens.consume(kw.IF_FEATURE)
        expression = self._parsers.parse_string_argument(tokens)
        # ``prefix:name`` is one unquoted argument; the lexer splits on ':'.
        if tokens.has_more() and tokens.peek_type() == YangTokenType.COLON:
            tokens.consume_type(YangTokenType.COLON)
            expression = f"{expression}:{tokens.consume()}"
        parent = context.current_parent
        if parent is not None:
            feats = getattr(parent, "if_features", None)
            if isinstance(feats, list):
                feats.append(expression)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            self._parsers.parse_body(
                tokens, context, "if-feature", error_context="if-feature substatement"
            )
            tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
