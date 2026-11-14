"""
Parsing helpers for ``submodule`` header statements.
"""

from __future__ import annotations

from .. import keywords as kw

from typing import TYPE_CHECKING

from ..parser_context import TokenStream, ParserContext, YangTokenType

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
        tokens.consume(kw.SUBMODULE)
        submodule_name = self._parsers.parse_identifier_argument(tokens, "submodule")
        tokens.consume_type(YangTokenType.LBRACE)
        context.module.name = submodule_name
        while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
            if tokens.peek() == kw.BELONGS_TO:
                self._parse_belongs_to(tokens, context)
            else:
                self._parse_submodule_statement(tokens, context)
        tokens.consume_type(YangTokenType.RBRACE)

    def _parse_submodule_statement(
        self, tokens: TokenStream, context: ParserContext
    ) -> None:
        self._parsers.dispatch_substatement(
            tokens, context, "submodule", error_context="submodule body"
        )

    def _parse_belongs_to(self, tokens: TokenStream, context: ParserContext) -> None:
        tokens.consume(kw.BELONGS_TO)
        parent_module = self._parsers.parse_identifier_argument(tokens, "belongs-to")
        context.module.belongs_to_module = parent_module
        tokens.consume_type(YangTokenType.LBRACE)
        self._parsers.parse_body(tokens, context, "belongs-to", error_context="belongs-to")
        tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
