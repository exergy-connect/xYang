"""
Parsing helpers for ``submodule`` header statements.
"""

from __future__ import annotations

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
            YangTokenType.YANG_VERSION: self._module_parser.parse_yang_version,
            YangTokenType.IMPORT: self._module_parser.parse_import_stmt,
            YangTokenType.INCLUDE: self._module_parser.parse_include_stmt,
            YangTokenType.REVISION: self._parsers.parse_revision,
            YangTokenType.FEATURE: self._parsers.parse_feature_stmt,
            YangTokenType.EXTENSION: self._parsers.parse_extension_stmt,
            YangTokenType.TYPEDEF: self._parsers.parse_typedef,
            YangTokenType.IDENTITY: self._parsers.parse_identity,
            YangTokenType.GROUPING: self._parsers.parse_grouping,
            YangTokenType.AUGMENT: self._parsers.parse_augment,
            YangTokenType.CONTAINER: self._parsers.parse_container,
            YangTokenType.LIST: self._parsers.parse_list,
            YangTokenType.LEAF: self._parsers.parse_leaf,
            YangTokenType.LEAF_LIST: self._parsers.parse_leaf_list,
            YangTokenType.ANYDATA: self._parsers.parse_anydata,
            YangTokenType.ANYXML: self._parsers.parse_anyxml,
        }

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
        tt = tokens.peek_type()
        if tt == YangTokenType.IDENTIFIER:
            self._parsers._parse_prefixed_extension_statement(tokens, context)
            return
        handler = self._submodule_dispatch.get(tt)
        if handler:
            handler(tokens, context)
            return
        if self._parsers._skip_unsupported_if_present(tokens, "submodule body"):
            return
        raise tokens._make_error(
            f"Unknown statement in submodule body: {tokens.peek()!r}"
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
