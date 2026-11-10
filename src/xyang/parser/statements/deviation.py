"""Parsing helpers for ``deviation`` statements."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import keywords as kw
from ..parser_context import ParserContext, TokenStream, YangTokenType
from ..unsupported_skip import _consume_balanced_braces, warn_unsupported_deviate
from ...ast import YangDeviationStmt
from ...errors import YangSyntaxError
from ...identifier_ref import parse_absolute_schema_path

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class DeviationStatementParser:
    """Parser for ``deviation`` / ``deviate not-supported``."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers

    def parse_deviation(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse ``deviation "<absolute-schema-path>" { ... }``."""
        tokens.consume(kw.DEVIATION)
        if tokens.peek_type() != YangTokenType.STRING:
            raise tokens.make_error(
                "deviation argument must be a quoted absolute schema path"
            )
        path = self._parsers.parse_string_concatenation(tokens)
        try:
            segments = parse_absolute_schema_path(path)
        except ValueError as exc:
            raise YangSyntaxError(str(exc)) from exc
        dev = YangDeviationStmt(
            name="deviation",
            target_path=path,
            target_path_segments=segments,
        )
        if tokens.consume_if_type(YangTokenType.LBRACE):
            body = context.push_parent(dev)
            self._parsers.parse_body(tokens, body, "deviation", error_context="deviation")
            tokens.consume_type(YangTokenType.RBRACE)
        self._parsers.add_to_parent_or_module(context, dev)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_deviate_substatement(self, tokens: TokenStream, context: ParserContext) -> None:
        dev = context.current_parent
        if not isinstance(dev, YangDeviationStmt):
            raise tokens.make_error("internal: deviate outside deviation")
        self._parse_deviate(tokens, dev)

    def _parse_deviate(self, tokens: TokenStream, dev: YangDeviationStmt) -> None:
        tokens.consume(kw.DEVIATE)
        if tokens.peek_type() != YangTokenType.IDENTIFIER:
            raise tokens.make_error(
                f"Expected deviate argument, got {tokens.peek()!r}"
            )
        kind = tokens.consume_type(YangTokenType.IDENTIFIER)
        if kind == kw.NOT_SUPPORTED:
            dev.not_supported = True
            tokens.consume_if_type(YangTokenType.SEMICOLON)
            return
        if kind in kw.UNSUPPORTED_DEVIATE_KINDS:
            warn_unsupported_deviate(kind, dev.target_path)
            if tokens.peek_type() == YangTokenType.LBRACE:
                _consume_balanced_braces(tokens)
            tokens.consume_if_type(YangTokenType.SEMICOLON)
            return
        raise tokens.make_error(f"Unknown deviate argument {kind!r}")
