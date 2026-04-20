"""
Parsing helpers for ``type`` statements and most type substatements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..parser_context import ParserContext, TokenStream, YangTokenType
from ...ast import YangTypeStmt
from ...xpath import XPathParser

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class TypeStatementParser:
    """Parsers for ``type`` statements and constraints."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers
        self._type_substatement_dispatch = {
            YangTokenType.TYPE: lambda t, c, _s: self.parse_type(t, c),
            YangTokenType.PATTERN: self.parse_type_pattern,
            YangTokenType.LENGTH: self.parse_type_length,
            YangTokenType.RANGE: self.parse_type_range,
            YangTokenType.FRACTION_DIGITS: self.parse_type_fraction_digits,
            YangTokenType.ENUM: self.parse_type_enum,
            YangTokenType.BIT: self._parsers._bits_parser.parse_type_bit,
            YangTokenType.PATH: self.parse_type_path,
            YangTokenType.REQUIRE_INSTANCE: self.parse_type_require_instance,
            YangTokenType.BASE: self.parse_type_base,
            YangTokenType.IDENTIFIER: (
                lambda t, c, _s: self._parsers._parse_prefixed_extension_statement(t, c)
            ),
        }

    def _parse_type_substatement(
        self,
        tokens: TokenStream,
        context: ParserContext,
        type_stmt: YangTypeStmt,
        type_name: str,
    ) -> None:
        """Parse one substatement inside ``type { ... }`` without registry indirection."""
        token_type = tokens.peek_type()
        handler = self._type_substatement_dispatch.get(token_type)
        if handler:
            handler(tokens, context, type_stmt)
            return
        if self._parsers._skip_unsupported_or_raise_unknown_stmt(
            tokens, f"type '{type_name}'"
        ):
            return

    def parse_type(self, tokens: TokenStream, context: ParserContext) -> YangTypeStmt:
        """Parse type statement."""
        tokens.consume_type(YangTokenType.TYPE)
        if tokens.peek_type() == YangTokenType.IDENTIFIER:
            type_name = self._parsers._consume_qname_from_identifier(tokens)
        else:
            type_name = tokens.consume()
        type_stmt = YangTypeStmt(name=type_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            type_context = context.push_parent(type_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_type_substatement(tokens, type_context, type_stmt, type_name)
            tokens.consume_type(YangTokenType.RBRACE)
        if type_stmt.name == "enumeration" and not type_stmt.enums:
            raise tokens._make_error(
                'enumeration type requires at least one "enum" statement (RFC 7950)'
            )
        if type_stmt.name == "bits":
            if not type_stmt.bits:
                raise tokens._make_error(
                    'bits type requires at least one "bit" statement (RFC 7950)'
                )
            self._parsers._bits_parser.finalize_bits_type(type_stmt, tokens)
        if type_stmt.name == "identityref" and not type_stmt.identityref_bases:
            raise tokens._make_error(
                'identityref type requires at least one "base" statement (RFC 7950)'
            )

        # Assign to parent (use setattr: current_parent is typed as YangStatementList which has no type/types)
        parent = context.current_parent
        if parent:
            if isinstance(parent, YangTypeStmt) and parent.name == "union":
                self._parsers._append_attr_list(parent, "types", type_stmt)
            elif hasattr(parent, "type") and not getattr(parent, "type", None):
                setattr(parent, "type", type_stmt)
            elif hasattr(parent, "types"):
                self._parsers._append_attr_list(parent, "types", type_stmt)
            elif hasattr(parent, "type") and getattr(parent, "type", None):
                parent_type = getattr(parent, "type", None)
                if parent_type is not None:
                    self._parsers._append_attr_list(parent_type, "types", type_stmt)

        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return type_stmt

    def parse_type_base(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse base substatement inside identityref type."""
        tokens.consume_type(YangTokenType.BASE)
        base_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        type_stmt.identityref_bases.append(base_name)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_type_pattern(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse ``pattern`` (RFC 7950 §9.4.6): string argument, then ``;`` or substatement block."""
        tokens.consume_type(YangTokenType.PATTERN)
        pattern = tokens.consume_type(YangTokenType.STRING)
        type_stmt.pattern = pattern
        type_stmt.pattern_error_message = None
        type_stmt.pattern_error_app_tag = None
        if tokens.consume_if_type(YangTokenType.LBRACE):
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                pt = tokens.peek_type()
                if pt == YangTokenType.DESCRIPTION:
                    self._parsers.parse_description(tokens, context)
                elif pt == YangTokenType.REFERENCE:
                    self._parsers.parse_reference_string_only(tokens, context)
                elif pt == YangTokenType.ERROR_MESSAGE:
                    tokens.consume_type(YangTokenType.ERROR_MESSAGE)
                    type_stmt.pattern_error_message = tokens.consume_type(
                        YangTokenType.STRING
                    )
                    tokens.consume_if_type(YangTokenType.SEMICOLON)
                elif pt == YangTokenType.ERROR_APP_TAG:
                    tokens.consume_type(YangTokenType.ERROR_APP_TAG)
                    type_stmt.pattern_error_app_tag = tokens.consume_type(
                        YangTokenType.STRING
                    )
                    tokens.consume_if_type(YangTokenType.SEMICOLON)
                elif pt == YangTokenType.IDENTIFIER and tokens.peek_type_at(1) == YangTokenType.COLON:
                    self._parsers._parse_prefixed_extension_statement(tokens, context)
                elif self._parsers._skip_unsupported_or_raise_unknown_stmt(
                    tokens,
                    "pattern",
                    error_message=(
                        f"Unknown substatement in pattern: {tokens.peek()!r}"
                    ),
                ):
                    pass
            tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_type_length(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse length constraint."""
        tokens.consume_type(YangTokenType.LENGTH)
        length = tokens.consume().strip('"\'')
        type_stmt.length = length
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_type_range(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse range constraint."""
        tokens.consume_type(YangTokenType.RANGE)
        range_val = tokens.consume_type(YangTokenType.STRING)
        type_stmt.range = range_val
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_type_fraction_digits(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse fraction-digits constraint."""
        tokens.consume_type(YangTokenType.FRACTION_DIGITS)
        type_stmt.fraction_digits = int(tokens.consume_type(YangTokenType.INTEGER))
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_type_enum(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse ``enum`` under ``type enumeration`` (RFC 7950 §9.6.4), with optional substatement block."""
        tokens.consume_type(YangTokenType.ENUM)
        enum_name = tokens.consume()  # identifier or keyword (e.g. string, boolean)
        type_stmt.enums.append(enum_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                pt = tokens.peek_type()
                if pt == YangTokenType.DESCRIPTION:
                    self._parsers.parse_description(tokens, context)
                elif pt == YangTokenType.REFERENCE:
                    self._parsers.parse_reference_string_only(tokens, context)
                elif pt == YangTokenType.IF_FEATURE:
                    self._parsers.parse_if_feature_stmt(tokens, context)
                elif pt == YangTokenType.VALUE:
                    tokens.consume_type(YangTokenType.VALUE)
                    tokens.consume_type(YangTokenType.INTEGER)
                    tokens.consume_if_type(YangTokenType.SEMICOLON)
                elif pt == YangTokenType.STATUS:
                    tokens.consume_type(YangTokenType.STATUS)
                    tokens.consume_type(YangTokenType.IDENTIFIER)
                    tokens.consume_if_type(YangTokenType.SEMICOLON)
                elif pt == YangTokenType.IDENTIFIER and tokens.peek_type_at(1) == YangTokenType.COLON:
                    self._parsers._parse_prefixed_extension_statement(tokens, context)
                elif self._parsers._skip_unsupported_or_raise_unknown_stmt(
                    tokens,
                    f"enum '{enum_name}'",
                    error_message=(
                        f"Unknown substatement in enum '{enum_name}': {tokens.peek()!r}"
                    ),
                ):
                    pass
            tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_type_path(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse path constraint (for leafref). Path is parsed to XPath PathNode during parsing."""
        tokens.consume_type(YangTokenType.PATH)
        path_str = tokens.consume_type(YangTokenType.STRING)
        setattr(type_stmt, "path", XPathParser(path_str).parse())
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_type_require_instance(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse require-instance constraint (for leafref)."""
        tokens.consume_type(YangTokenType.REQUIRE_INSTANCE)
        _, tt = tokens.consume_oneof([YangTokenType.TRUE, YangTokenType.FALSE])
        type_stmt.require_instance = tt == YangTokenType.TRUE
        tokens.consume_if_type(YangTokenType.SEMICOLON)
