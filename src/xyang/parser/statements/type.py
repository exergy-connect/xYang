"""
Parsing helpers for ``type`` statements and most type substatements.
"""

from __future__ import annotations

import re

from .. import keywords as kw

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangPatternSpec, YangTypeStmt
from ...identifier_ref import identifier_ref
from ...xpath import PathNode, XPathParser

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class TypeStatementParser:
    """Parsers for ``type`` statements and constraints."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers
        self._pattern_stack: list[SimpleNamespace] = []

    def _parse_type_substatement(
        self,
        tokens: TokenStream,
        context: ParserContext,
        type_stmt: YangTypeStmt,
        type_name: str,
    ) -> None:
        """Parse one substatement inside ``type { ... }``."""
        self._parsers.dispatch_substatement(
            tokens,
            context,
            "type",
            type_stmt,
            error_context=f"type '{type_name}'",
        )

    def parse_type(self, tokens: TokenStream, context: ParserContext) -> YangTypeStmt:
        """Parse type statement."""
        tokens.consume(kw.TYPE)
        type_prefix: str | None = None
        if tokens.peek_type() == YangTokenType.IDENTIFIER:
            type_prefix, type_name = self._parsers.consume_identifier_ref(tokens)
        else:
            type_name = tokens.consume()
        type_stmt = YangTypeStmt(name=type_name, prefix=type_prefix)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            type_context = context.push_parent(type_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_type_substatement(tokens, type_context, type_stmt, type_name)
            tokens.consume_type(YangTokenType.RBRACE)
        if type_stmt.name == "enumeration" and not type_stmt.enums:
            raise tokens.make_error(
                'enumeration type requires at least one "enum" statement (RFC 7950)'
            )
        if type_stmt.name == "bits":
            if not type_stmt.bits:
                raise tokens.make_error(
                    'bits type requires at least one "bit" statement (RFC 7950)'
                )
            self._parsers._bits_parser.finalize_bits_type(type_stmt, tokens)
        if type_stmt.name == "identityref" and not type_stmt.identityref_bases:
            raise tokens.make_error(
                'identityref type requires at least one "base" statement (RFC 7950)'
            )

        # Assign to parent (use setattr: current_parent is typed as YangStatementList which has no type/types)
        parent = context.current_parent
        if parent:
            if isinstance(parent, YangTypeStmt) and parent.name == "union":
                self._parsers.append_attr_list(parent, "types", type_stmt)
            elif hasattr(parent, "type") and not getattr(parent, "type", None):
                setattr(parent, "type", type_stmt)
            elif hasattr(parent, "types"):
                self._parsers.append_attr_list(parent, "types", type_stmt)
            elif hasattr(parent, "type") and getattr(parent, "type", None):
                parent_type = getattr(parent, "type", None)
                if parent_type is not None:
                    self._parsers.append_attr_list(parent_type, "types", type_stmt)

        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return type_stmt

    def parse_type_base(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse base substatement inside identityref type (RFC 7950 §9.10)."""
        tokens.consume(kw.BASE)
        base_prefix, base_name = self._parsers.consume_identifier_ref(tokens)
        type_stmt.identityref_bases.append(identifier_ref(base_name, base_prefix))
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_type_pattern(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse ``pattern`` (RFC 7950 §9.4.6): string argument, then ``;`` or substatement block."""
        tokens.consume(kw.PATTERN)
        pattern = self._parsers.parse_string_concatenation(tokens)
        acc = SimpleNamespace(error_message=None, error_app_tag=None, invert_match=False)
        self._pattern_stack.append(acc)
        try:
            if tokens.consume_if_type(YangTokenType.LBRACE):
                self._parsers.parse_body(tokens, context, "pattern", error_context="pattern")
                tokens.consume_type(YangTokenType.RBRACE)
        finally:
            self._pattern_stack.pop()
        pattern_error_message = acc.error_message
        pattern_error_app_tag = acc.error_app_tag
        invert_match = acc.invert_match
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        spec = YangPatternSpec(
            pattern=pattern,
            invert_match=invert_match,
            error_message=pattern_error_message,
            error_app_tag=pattern_error_app_tag,
        )
        type_stmt.patterns.append(spec)

    def parse_type_length(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse ``length`` as one string (``1..127`` or ``"1..127"``)."""
        tokens.consume(kw.LENGTH)
        type_stmt.length = self._parsers.parse_string_argument(tokens)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_type_range(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse range constraint."""
        tokens.consume(kw.RANGE)
        type_stmt.range = self._parsers.parse_string_argument(tokens)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_type_fraction_digits(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse fraction-digits constraint."""
        tokens.consume(kw.FRACTION_DIGITS)
        type_stmt.fraction_digits = int(tokens.consume_type(YangTokenType.INTEGER))
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_type_enum(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse ``enum`` under ``type enumeration`` (RFC 7950 §9.6.4), with optional substatement block."""
        tokens.consume(kw.ENUM)
        enum_name = tokens.consume()  # identifier or keyword (e.g. string, boolean)
        type_stmt.enums.append(enum_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            self._parsers.parse_body(
                tokens, context, "enum", error_context=f"enum '{enum_name}'"
            )
            tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_type_path(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse path constraint (for leafref). Path is parsed to XPath PathNode during parsing."""
        tokens.consume(kw.PATH)
        path_str = self._parsers.parse_string_argument(tokens)
        type_stmt.path = cast(PathNode, XPathParser(path_str).parse_path())
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_type_require_instance(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse require-instance constraint (for leafref)."""
        tokens.consume(kw.REQUIRE_INSTANCE)
        _, tt = tokens.consume_oneof([kw.TRUE, kw.FALSE])
        type_stmt.require_instance = tt == kw.TRUE
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_pattern_error_message(self, tokens: TokenStream, _context: ParserContext) -> None:
        tokens.consume(kw.ERROR_MESSAGE)
        self._pattern_stack[-1].error_message = self._parsers.parse_string_concatenation(tokens)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_pattern_error_app_tag(self, tokens: TokenStream, _context: ParserContext) -> None:
        tokens.consume(kw.ERROR_APP_TAG)
        self._pattern_stack[-1].error_app_tag = self._parsers.parse_string_concatenation(tokens)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_pattern_modifier(self, tokens: TokenStream, _context: ParserContext) -> None:
        tokens.consume(kw.MODIFIER)
        modifier = tokens.consume()
        self._pattern_stack[-1].invert_match = modifier == "invert-match"
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_enum_value(self, tokens: TokenStream, _context: ParserContext) -> None:
        tokens.consume(kw.VALUE)
        raw = self._parsers.parse_string_argument(tokens)
        if re.fullmatch(r"[+-]?\d+", raw) is None:
            raise tokens.make_error(f"value argument must be an integer, got {raw!r}")
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_enum_status(self, tokens: TokenStream, _context: ParserContext) -> None:
        tokens.consume(kw.STATUS)
        tokens.consume_type(YangTokenType.IDENTIFIER)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
