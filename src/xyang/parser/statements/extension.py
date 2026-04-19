"""
Parsing helpers for ``extension`` statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..parser_context import TokenStream, ParserContext, YangTokenType
from ...ast import YangExtensionStmt
from ...ext import ExtensionIdentity, get_extension_apply_callback

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class ExtensionStatementParser:
    """Parsers for extension definition and extension argument statements."""

    def __init__(self, parsers: StatementParsers) -> None:
        self._parsers = parsers

    def parse_extension_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse extension definition (RFC 7950 §7.17)."""
        tokens.consume_type(YangTokenType.EXTENSION)
        name = tokens.consume_type(YangTokenType.IDENTIFIER)
        ext = YangExtensionStmt(name=name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(ext)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                tt = tokens.peek_type()
                if tt == YangTokenType.ARGUMENT:
                    self._parse_extension_argument_stmt(tokens, new_context)
                elif tt == YangTokenType.DESCRIPTION:
                    self._parsers.parse_description(tokens, new_context)
                elif tt == YangTokenType.REFERENCE:
                    self._parsers.parse_reference_string_only(tokens, new_context)
                elif tt == YangTokenType.IF_FEATURE:
                    self._parsers.parse_if_feature_stmt(tokens, new_context)
                elif self._parsers._skip_unsupported_if_present(
                    tokens, f"extension '{name}'"
                ):
                    continue
                else:
                    raise tokens._make_error(
                        f"Unknown statement in extension '{name}': {tokens.peek()!r}"
                    )
            tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        cb = get_extension_apply_callback(
            ExtensionIdentity(
                module_name=context.module.name,
                extension_name=name,
            )
        )
        if cb is not None:
            ext.apply_callback = cb
        context.module.extensions[name] = ext
        self._parsers._add_to_parent_or_module(context, ext)

    def _parse_extension_argument_stmt(
        self, tokens: TokenStream, context: ParserContext
    ) -> None:
        """Parse ``argument`` substatement inside ``extension``."""
        tokens.consume_type(YangTokenType.ARGUMENT)
        tt = tokens.peek_type()
        if tt == YangTokenType.STRING:
            arg = tokens.consume_type(YangTokenType.STRING)
        elif tt == YangTokenType.IDENTIFIER:
            arg = tokens.consume_type(YangTokenType.IDENTIFIER)
        else:
            raise tokens._make_error(
                f"Expected extension argument identifier/string, got {tt.name if tt else 'end'}"
            )
        parent = context.current_parent
        if isinstance(parent, YangExtensionStmt):
            parent.argument_name = arg
        if tokens.consume_if_type(YangTokenType.LBRACE):
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                if tokens.peek_type() == YangTokenType.YIN_ELEMENT:
                    self._parse_extension_argument_yin_element(tokens, context)
                elif self._parsers._skip_unsupported_if_present(tokens, "extension argument"):
                    continue
                else:
                    raise tokens._make_error(
                        f"Unknown statement in extension argument: {tokens.peek()!r}"
                    )
            tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def _parse_extension_argument_yin_element(
        self, tokens: TokenStream, context: ParserContext
    ) -> None:
        """Parse ``yin-element`` under ``extension argument``."""
        tokens.consume_type(YangTokenType.YIN_ELEMENT)
        _, tt = tokens.consume_oneof([YangTokenType.TRUE, YangTokenType.FALSE])
        parent = context.current_parent
        if isinstance(parent, YangExtensionStmt):
            parent.argument_yin_element = tt == YangTokenType.TRUE
        tokens.consume_if_type(YangTokenType.SEMICOLON)
