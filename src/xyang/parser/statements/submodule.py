"""
Parsing helpers for ``submodule`` header statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..parser_context import TokenStream, ParserContext, YangTokenType
from ..statement_dispatch import StatementDispatchSpec

if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers
    from .module import ModuleStatementParser


class SubmoduleStatementParser:
    """Parsers for submodule header statements."""

    def __init__(
        self, parsers: "StatementParsers", module_parser: "ModuleStatementParser"
    ) -> None:
        self._parsers = parsers
        self._module_parser = module_parser

    def parse_submodule(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse submodule statement (YANG 1.1)."""
        tokens.consume_type(YangTokenType.SUBMODULE)
        submodule_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        tokens.consume_type(YangTokenType.LBRACE)
        context.module.name = submodule_name
        while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
            if tokens.peek_type() == YangTokenType.BELONGS_TO:
                self._parse_belongs_to(tokens, context)
            else:
                self._parse_submodule_statement(tokens, context)
        tokens.consume_type(YangTokenType.RBRACE)

    def _parse_submodule_statement(
        self, tokens: TokenStream, context: ParserContext
    ) -> None:
        self._parsers._parse_statement(
            tokens,
            context,
            StatementDispatchSpec(
                registry_prefix="submodule", unsupported_context="submodule body"
            ),
        )

    def _parse_belongs_to(self, tokens: TokenStream, context: ParserContext) -> None:
        tokens.consume_type(YangTokenType.BELONGS_TO)
        parent_module = tokens.consume_type(YangTokenType.IDENTIFIER)
        context.module.belongs_to_module = parent_module
        tokens.consume_type(YangTokenType.LBRACE)
        while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
            if tokens.peek_type() == YangTokenType.PREFIX:
                self._module_parser.parse_prefix_value_stmt(tokens, context)
            elif self._parsers._skip_unsupported_if_present(tokens, "belongs-to"):
                continue
            else:
                raise tokens._make_error(
                    f"Unknown statement in belongs-to: {tokens.peek()!r}"
                )
        tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
