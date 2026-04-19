"""
Parsing helpers for ``module`` header and linkage statements.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from ..parser_context import TokenStream, ParserContext, YangTokenType
if TYPE_CHECKING:
    from ..statement_parsers import StatementParsers


class ModuleStatementParser:
    """Parsers for module header and import/include linkage statements."""

    def __init__(self, parsers: "StatementParsers") -> None:
        self._parsers = parsers
        self._module_dispatch = {
            YangTokenType.LEAF: self._parsers.parse_leaf,
            YangTokenType.LIST: self._parsers.parse_list,
            YangTokenType.LEAF_LIST: self._parsers.parse_leaf_list,
            YangTokenType.CONTAINER: self._parsers.parse_container,
            YangTokenType.ANYDATA: self._parsers.parse_anydata,
            YangTokenType.ANYXML: self._parsers.parse_anyxml,
            YangTokenType.TYPEDEF: self._parsers.parse_typedef,
            YangTokenType.GROUPING: self._parsers.parse_grouping,
            YangTokenType.IMPORT: self.parse_import_stmt,
            YangTokenType.INCLUDE: self.parse_include_stmt,
            YangTokenType.REVISION: self._parsers.parse_revision,
            YangTokenType.DESCRIPTION: self._parsers.parse_description,
            YangTokenType.FEATURE: self._parsers.parse_feature_stmt,
            YangTokenType.IDENTITY: self._parsers.parse_identity,
            YangTokenType.EXTENSION: self._parsers.parse_extension_stmt,
            YangTokenType.AUGMENT: self._parsers.parse_augment,
            YangTokenType.YANG_VERSION: self.parse_yang_version,
            YangTokenType.NAMESPACE: self.parse_namespace,
            YangTokenType.PREFIX: self.parse_prefix,
            YangTokenType.ORGANIZATION: self.parse_organization,
            YangTokenType.CONTACT: self.parse_contact,
        }

    def parse_module(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse module statement."""
        tokens.consume_type(YangTokenType.MODULE)
        module_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        tokens.consume_type(YangTokenType.LBRACE)

        context.module.name = module_name

        while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
            self._parse_module_statement(tokens, context)

        tokens.consume_type(YangTokenType.RBRACE)

    def _parse_module_statement(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse one statement in module body."""
        tt = tokens.peek_type()
        if tt == YangTokenType.IDENTIFIER:
            self._parsers._parse_prefixed_extension_statement(tokens, context)
            return
        if tt is None:
            raise tokens._make_error("Unexpected end of input in module body")
        handler = self._module_dispatch.get(tt)
        if handler:
            handler(tokens, context)
            return
        if self._parsers._skip_unsupported_if_present(tokens, "module body"):
            return
        raise tokens._make_error(f"Unknown statement in module body: {tokens.peek()!r}")

    def parse_import_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse import and load the referenced module (RFC 7950)."""
        tokens.consume_type(YangTokenType.IMPORT)
        imported_module_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        if tokens.consume_if_type(YangTokenType.SEMICOLON):
            return
        if not tokens.consume_if_type(YangTokenType.LBRACE):
            raise tokens._make_error("Expected '{' or ';' after import module name")
        acc = SimpleNamespace(local_prefix=None, revision_date=None)
        self._parsers._import_parse_state = acc
        try:
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                if tokens.peek_type() == YangTokenType.REVISION_DATE:
                    self._parse_import_revision_date_binding(tokens, context)
                    continue
                if tokens.peek_type() == YangTokenType.DESCRIPTION:
                    self._parsers.parse_optional_description(
                        tokens, context.push_parent(SimpleNamespace())
                    )
                    continue
                tt = tokens.peek_type()
                if tt == YangTokenType.IDENTIFIER:
                    self._parsers._parse_prefixed_extension_statement(tokens, context)
                elif tt == YangTokenType.PREFIX:
                    self.parse_import_prefix_binding(tokens, context)
                elif tt == YangTokenType.REFERENCE:
                    self._parsers.parse_reference_string_only(tokens, context)
                elif self._parsers._skip_unsupported_if_present(tokens, "import"):
                    continue
                else:
                    raise tokens._make_error(
                        "Unknown statement in import: "
                        f"{tokens.peek()!r} (allowed: prefix, reference, revision-date)"
                    )
        finally:
            self._parsers._import_parse_state = None
        tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        if self._parsers._yang_parser is not None and acc.local_prefix:
            self._parsers._yang_parser.register_import(
                parent=context.module,
                imported_module_name=imported_module_name,
                local_prefix=acc.local_prefix,
                revision_date=acc.revision_date,
                source_dir=context.source_dir,
                tokens=tokens,
            )

    def parse_include_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse include and merge the submodule into the current module (RFC 7950)."""
        tokens.consume_type(YangTokenType.INCLUDE)
        sub_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        revision_date = None
        if tokens.consume_if_type(YangTokenType.LBRACE):
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                if tokens.peek_type() == YangTokenType.REVISION_DATE:
                    revision_date = self._parsers._revision_parser.parse_revision_date_statement(
                        tokens
                    )
                elif tokens.peek_type() == YangTokenType.DESCRIPTION:
                    self._parsers.parse_optional_description(
                        tokens, context.push_parent(SimpleNamespace())
                    )
                else:
                    tt = tokens.peek_type()
                    if tt == YangTokenType.IDENTIFIER:
                        self._parsers._parse_prefixed_extension_statement(tokens, context)
                    elif tt == YangTokenType.PREFIX:
                        self.parse_prefix_value_stmt(tokens, context)
                    elif tt == YangTokenType.REFERENCE:
                        self._parsers.parse_reference_string_only(tokens, context)
                    elif self._parsers._skip_unsupported_if_present(tokens, "include"):
                        continue
                    else:
                        raise tokens._make_error(
                            f"Unknown statement in include: {tokens.peek()!r}"
                        )
            tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        if self._parsers._yang_parser is not None:
            self._parsers._yang_parser.merge_included_submodule(
                parent=context.module,
                submodule_name=sub_name,
                revision_date=revision_date,
                source_dir=context.source_dir,
                tokens=tokens,
            )

    def parse_prefix_value_stmt(
        self, tokens: TokenStream, _context: ParserContext
    ) -> None:
        """Prefix substatement inside import or belongs-to (not module-level prefix)."""
        tokens.consume_type(YangTokenType.PREFIX)
        self._parsers._consume_prefix_argument(tokens)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_import_prefix_binding(
        self, tokens: TokenStream, _context: ParserContext
    ) -> None:
        """``prefix`` inside ``import { ... }``; updates ``_import_parse_state``."""
        acc = self._parsers._import_parse_state
        if acc is None:
            raise tokens._make_error("internal: import prefix outside import block")
        tokens.consume_type(YangTokenType.PREFIX)
        tt = tokens.peek_type()
        if tt == YangTokenType.STRING:
            acc.local_prefix = tokens.consume_type(YangTokenType.STRING)
        elif tt == YangTokenType.IDENTIFIER:
            acc.local_prefix = tokens.consume_type(YangTokenType.IDENTIFIER)
        else:
            raise tokens._make_error(
                f"Expected prefix string or identifier, got {tt.name if tt else 'end'}"
            )
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def _parse_import_revision_date_binding(
        self, tokens: TokenStream, _context: ParserContext
    ) -> None:
        """``revision-date`` inside ``import { ... }``."""
        acc = self._parsers._import_parse_state
        if acc is None:
            raise tokens._make_error("internal: revision-date outside import block")
        acc.revision_date = self._parsers._revision_parser.parse_revision_date_statement(tokens)

    def parse_yang_version(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse yang-version statement."""
        tokens.consume_type(YangTokenType.YANG_VERSION)
        version, _ = tokens.consume_oneof(
            [YangTokenType.IDENTIFIER, YangTokenType.DOTTED_NUMBER]
        )
        context.module.yang_version = version
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_namespace(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse namespace statement."""
        tokens.consume_type(YangTokenType.NAMESPACE)
        namespace = tokens.consume_type(YangTokenType.STRING)
        context.module.namespace = namespace
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_prefix(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse module-level prefix statement."""
        tokens.consume_type(YangTokenType.PREFIX)
        tt = tokens.peek_type()
        if tt == YangTokenType.STRING:
            context.module.prefix = tokens.consume_type(YangTokenType.STRING)
        elif tt == YangTokenType.IDENTIFIER:
            context.module.prefix = tokens.consume_type(YangTokenType.IDENTIFIER)
        else:
            raise tokens._make_error(
                f"Expected prefix string or identifier, got {tt.name if tt else 'end'}"
            )
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_organization(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse organization statement."""
        tokens.consume_type(YangTokenType.ORGANIZATION)
        context.module.organization = tokens.consume_type(YangTokenType.STRING)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_contact(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse contact statement."""
        tokens.consume_type(YangTokenType.CONTACT)
        context.module.contact = tokens.consume_type(YangTokenType.STRING)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
