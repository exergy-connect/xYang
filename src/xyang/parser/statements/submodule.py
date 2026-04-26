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
        self._submodule_dispatch = {
            kw.YANG_VERSION: self._module_parser.parse_yang_version,
            kw.IMPORT: self._module_parser.parse_import_stmt,
            kw.INCLUDE: self._module_parser.parse_include_stmt,
            kw.REVISION: self._parsers.parse_revision,
            kw.FEATURE: self._parsers.parse_feature_stmt,
            kw.EXTENSION: self._parsers.parse_extension_stmt,
            kw.TYPEDEF: self._parsers.parse_typedef,
            kw.IDENTITY: self._parsers.parse_identity,
            kw.GROUPING: self._parsers.parse_grouping,
            kw.AUGMENT: self._parsers.parse_augment,
            kw.CONTAINER: self._parsers.parse_container,
            kw.LIST: self._parsers.parse_list,
            kw.LEAF: self._parsers.parse_leaf,
            kw.LEAF_LIST: self._parsers.parse_leaf_list,
            kw.ANYDATA: self._parsers.parse_anydata,
            kw.ANYXML: self._parsers.parse_anyxml,
        }

    def parse_submodule(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse submodule statement (YANG 1.1)."""
        tokens.consume(kw.SUBMODULE)
        submodule_name = tokens.consume_type(YangTokenType.IDENTIFIER)
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
        tt = self._parsers._dispatch_key(tokens)
        handler = self._submodule_dispatch.get(tt)
        if handler:
            handler(tokens, context)
            return
        if self._parsers._is_prefixed_extension_start(tokens):
            self._parsers._parse_prefixed_extension_statement(tokens, context)
            return
        if self._parsers._skip_unsupported_or_raise_unknown_stmt(tokens, "submodule body"):
            return

    def _parse_belongs_to(self, tokens: TokenStream, context: ParserContext) -> None:
        tokens.consume(kw.BELONGS_TO)
        parent_module = tokens.consume_type(YangTokenType.IDENTIFIER)
        context.module.belongs_to_module = parent_module
        tokens.consume_type(YangTokenType.LBRACE)
        while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
            if tokens.peek() == kw.PREFIX:
                self._module_parser.parse_prefix_value_stmt(tokens, context)
            elif self._parsers._skip_unsupported_or_raise_unknown_stmt(
                tokens, "belongs-to"
            ):
                continue
        tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
