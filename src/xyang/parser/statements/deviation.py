"""Parsing helpers for ``deviation`` statements."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import keywords as kw
from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangDeviateStmt, YangDeviationStmt
from ...errors import YangSyntaxError
from ...identifier_ref import parse_absolute_schema_path

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class DeviationStatementParser:
    """Parser for ``deviation`` and its ``deviate`` substatements (RFC 7950 §7.20.3)."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers

    def parse_deviation(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse ``deviation "<absolute-schema-path>" { ... }``."""
        tokens.consume(kw.DEVIATION)
        path = self._parsers.parse_string_argument(tokens)
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
        if dev.not_supported and dev.deviates:
            raise tokens.make_error(
                f"deviation {path!r}: 'deviate not-supported' cannot be combined with "
                "other deviate statements (RFC 7950 §7.20.3.2)"
            )
        self._parsers.add_to_parent_or_module(context, dev)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_deviate_substatement(self, tokens: TokenStream, context: ParserContext) -> None:
        dev = context.current_parent
        if not isinstance(dev, YangDeviationStmt):
            raise tokens.make_error("internal: deviate outside deviation")
        self._parse_deviate(tokens, dev, context)

    def _parse_deviate(
        self, tokens: TokenStream, dev: YangDeviationStmt, context: ParserContext
    ) -> None:
        tokens.consume(kw.DEVIATE)
        kind = self._parsers.parse_string_argument(tokens)
        if kind == kw.NOT_SUPPORTED:
            dev.not_supported = True
            if tokens.peek_type() == YangTokenType.LBRACE:
                tokens.consume_type(YangTokenType.LBRACE)
                tokens.consume_type(YangTokenType.RBRACE)
            tokens.consume_if_type(YangTokenType.SEMICOLON)
            return
        allowed = kw.DEVIATE_SUBSTATEMENTS.get(kind)
        if allowed is None:
            raise tokens.make_error(f"Unknown deviate argument {kind!r}")
        deviate = YangDeviateStmt(kind=kind)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                keyword = tokens.peek()
                if keyword not in allowed:
                    raise tokens.make_error(
                        f"{keyword!r} is not allowed in 'deviate {kind}' (RFC 7950 §7.20.3.2)"
                    )
                self._parse_deviate_property(tokens, context, deviate, keyword)
            tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        dev.deviates.append(deviate)

    def _parse_deviate_property(
        self,
        tokens: TokenStream,
        context: ParserContext,
        deviate: YangDeviateStmt,
        keyword: str,
    ) -> None:
        p = self._parsers
        if keyword == kw.MUST:
            deviate.must_statements.append(p.parse_must(tokens, context))
            return
        if keyword == kw.TYPE:
            if deviate.type is not None:
                raise tokens.make_error(f"duplicate 'type' in 'deviate {deviate.kind}'")
            deviate.type = p.parse_type(tokens, context)
            return
        tokens.consume(keyword)
        single = {
            kw.CONFIG: deviate.config is not None,
            kw.MANDATORY: deviate.mandatory is not None,
            kw.MIN_ELEMENTS: deviate.min_elements is not None,
            kw.MAX_ELEMENTS: deviate.max_elements_set,
            kw.UNITS: deviate.units is not None,
        }
        if single.get(keyword):
            raise tokens.make_error(f"duplicate {keyword!r} in 'deviate {deviate.kind}'")
        if keyword == kw.CONFIG:
            deviate.config = p.parse_boolean_argument(tokens, "config")
        elif keyword == kw.MANDATORY:
            deviate.mandatory = p.parse_boolean_argument(tokens, "mandatory")
        elif keyword == kw.MIN_ELEMENTS:
            value = p.parse_integer_or_unbounded(tokens, "min-elements")
            if value is None:
                raise tokens.make_error("min-elements cannot be 'unbounded'")
            deviate.min_elements = value
        elif keyword == kw.MAX_ELEMENTS:
            deviate.max_elements = p.parse_integer_or_unbounded(tokens, "max-elements")
            deviate.max_elements_set = True
        elif keyword == kw.UNITS:
            deviate.units = p.parse_string_argument(tokens)
        elif keyword == kw.DEFAULT:
            deviate.defaults.append(p.parse_default_value_tokens(tokens))
        elif keyword == kw.UNIQUE:
            arg = p.parse_string_argument(tokens)
            paths = [
                "/".join(seg.split(":", 1)[-1] for seg in path.split("/") if seg)
                for path in arg.split()
            ]
            if not paths:
                raise tokens.make_error("unique requires at least one descendant path")
            deviate.unique.append(paths)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
