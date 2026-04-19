"""
Statement parsers for YANG statements.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Optional, TYPE_CHECKING, TypeVar
from .parser_context import TokenStream, ParserContext, YangTokenType
from .statement_dispatch import StatementDispatchSpec
from .statements.extension import ExtensionStatementParser
from .statements.feature import FeatureStatementParser
from .statements.identity import IdentityStatementParser
from .statements.bits import BitsStatementParser
from .statements.module import ModuleStatementParser
from .statements.submodule import SubmoduleStatementParser
from .statements.refine import RefineStatementParser
from .statements.revision import RevisionStatementParser
from .statements.type import TypeStatementParser
from .statements.uses import UsesStatementParser
from ..ast import (
    YangAnydataStmt,
    YangAnyxmlStmt,
    YangContainerStmt, YangListStmt, YangLeafStmt,
    YangLeafListStmt, YangTypeStmt, YangMustStmt, YangWhenStmt, YangTypedefStmt,
    YangExtensionInvocationStmt,
    YangGroupingStmt, YangUsesStmt, YangAugmentStmt, YangRefineStmt, YangChoiceStmt, YangCaseStmt,
    YangStatementList, YangStatementWithMust,
    YangStatementWithWhen,
)
from ..ext import (
    ensure_builtin_extensions_loaded,
)

from ..refine_expand import copy_yang_statement
from .unsupported_skip import (
    _consume_balanced_braces,
    is_unsupported_construct_start,
    skip_unsupported_construct,
)

if TYPE_CHECKING:
    from .statement_registry import StatementRegistry
    from .yang_parser import YangParser
    from ..ast import YangStatement
    from ..module import YangModule

# Generic statement type used for blocks like container/list/leaf/leaf-list.
# These concrete statement classes all inherit from YangStatement, so bind
# the type variable to YangStatement (not YangStatementList) to satisfy
# type checkers when passing instances to _add_to_parent_or_module.
_StatementT = TypeVar("_StatementT", bound="YangStatement")


class StatementParsers:
    """Collection of statement parsing methods."""

    def __init__(self, registry: "StatementRegistry", yang_parser: Optional["YangParser"] = None):
        self.registry = registry
        self._yang_parser: Optional["YangParser"] = yang_parser
        #: Set only while parsing an ``import { ... }`` block (prefix / revision-date capture).
        self._import_parse_state: Optional[SimpleNamespace] = None
        self._extension_parser = ExtensionStatementParser(self)
        self._feature_parser = FeatureStatementParser(self)
        self._identity_parser = IdentityStatementParser(self)
        self._module_parser = ModuleStatementParser(self)
        self._submodule_parser = SubmoduleStatementParser(self, self._module_parser)
        self._refine_parser = RefineStatementParser(self)
        self._revision_parser = RevisionStatementParser(self)
        self._bits_parser = BitsStatementParser(self)
        self._type_parser = TypeStatementParser(self)
        self._uses_parser = UsesStatementParser(self)
        ensure_builtin_extensions_loaded()

    # ------------------------------------------------------------------
    # Small helpers for common patterns
    # ------------------------------------------------------------------

    def _add_to_parent_or_module(
        self, context: ParserContext, stmt: "YangStatement"
    ) -> None:
        """Add statement to the current parent (if it can contain statements) or to the module."""
        parent = context.current_parent
        if isinstance(parent, YangStatementList):
            parent.statements.append(stmt)
        else:
            # Fallback to module-level statements (e.g. when no parent or parent is a type).
            context.module.statements.append(stmt)

    def _append_attr_list(self, obj: object, attr: str, value: object) -> None:
        """Append value to a list attribute on obj, creating the list if needed."""
        current = getattr(obj, attr, None)
        if current is None:
            current = []
            setattr(obj, attr, current)
        current.append(value)

    def _skip_unsupported_if_present(self, tokens: TokenStream, context: str) -> bool:
        """If the next token starts deviation/extension/rpc/..., skip it and warn. Returns True if skipped."""
        if not is_unsupported_construct_start(tokens):
            return False
        skip_unsupported_construct(tokens, context=context)
        return True

    def _consume_qname_from_identifier(self, tokens: TokenStream) -> str:
        """Consume ``name`` or ``prefix:name`` (``prefix:...`` chain). Current token must be IDENTIFIER."""
        parts = [tokens.consume_type(YangTokenType.IDENTIFIER)]
        while tokens.consume_if_type(YangTokenType.COLON):
            parts.append(tokens.consume_type(YangTokenType.IDENTIFIER))
        return ":".join(parts)

    def _consume_prefix_argument(self, tokens: TokenStream) -> None:
        """Prefix argument as string or bare identifier (common in example modules)."""
        tt = tokens.peek_type()
        if tt == YangTokenType.STRING:
            tokens.consume_type(YangTokenType.STRING)
        elif tt == YangTokenType.IDENTIFIER:
            tokens.consume_type(YangTokenType.IDENTIFIER)
        else:
            raise tokens._make_error(
                f"Expected prefix string or identifier, got {tt.name if tt else 'end'}"
            )

    def _consume_optional_extension_argument(
        self, tokens: TokenStream
    ) -> Optional[str]:
        """Consume optional extension argument as normalized string (unquoted)."""
        tt = tokens.peek_type()
        if tt is None or tt in (YangTokenType.LBRACE, YangTokenType.SEMICOLON):
            return None
        if tt == YangTokenType.STRING:
            return self._parse_string_concatenation(tokens)
        if tt in (
            YangTokenType.IDENTIFIER,
            YangTokenType.INTEGER,
            YangTokenType.DOTTED_NUMBER,
            YangTokenType.TRUE,
            YangTokenType.FALSE,
        ):
            return tokens.consume()
        return None

    def _parse_extension_invocation_substatement(
        self,
        tokens: TokenStream,
        context: ParserContext,
        inv_name: str,
    ) -> None:
        """One substatement inside ``prefix:extension { ... }`` (after the opening ``{``)."""
        self._parse_statement(
            tokens,
            context,
            StatementDispatchSpec(
                registry_prefix="extension_invocation",
                unsupported_context=f"extension invocation '{inv_name}'",
                fallback_registry_key_prefix="module",
            ),
        )

    def _parse_prefixed_extension_statement(
        self, tokens: TokenStream, context: ParserContext
    ) -> None:
        """Parse ``prefix:extension``; current token must be the *prefix* (IDENTIFIER).

        The prefix is consumed, then ``:`` and the extension name. No handler lookup is
        used for the prefix token (only ``identifier`` … ``:`` commits to an extension).
        """
        prefix = tokens.consume_type(YangTokenType.IDENTIFIER)
        if not tokens.consume_if_type(YangTokenType.COLON):
            raise tokens._make_error(
                f"Expected ':' after extension prefix {prefix!r}"
            )
        if tokens.peek_type() != YangTokenType.IDENTIFIER:
            raise tokens._make_error(
                f"Expected extension name after prefix {prefix!r} and ':'"
            )
        ext_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        resolved_module = context.module.resolve_prefixed_module(prefix)
        if resolved_module is None:
            raise tokens._make_error(
                f"Unknown extension prefix {prefix!r} in invocation {prefix}:{ext_name}"
            )
        resolved_extension = resolved_module.get_extension(ext_name)
        if resolved_extension is None:
            raise tokens._make_error(
                f"Unknown extension {ext_name!r} in module {resolved_module.name!r} "
                f"for invocation {prefix}:{ext_name}"
            )
        arg = self._consume_optional_extension_argument(tokens)
        inv = YangExtensionInvocationStmt(
            name=f"{prefix}:{ext_name}",
            prefix=prefix,
            resolved_module=resolved_module,
            resolved_extension=resolved_extension,
            argument=arg,
        )
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(inv)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_extension_invocation_substatement(
                    tokens, new_context, inv.name
                )
            tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        self._add_to_parent_or_module(context, inv)

    def _parse_statement(
        self,
        tokens: TokenStream,
        context: ParserContext,
        spec: StatementDispatchSpec,
    ) -> None:
        """Parse one substatement: optional identifier-as-keyword, extension, registry, skip, error."""
        key_prefix = (
            spec.registry_key_prefix
            if spec.registry_key_prefix is not None
            else spec.registry_prefix
        )

        if tokens.peek_type() == YangTokenType.IDENTIFIER:
            ident = tokens.peek() or ""
            if (
                spec.identifier_dispatch_keywords is not None
                and ident in spec.identifier_dispatch_keywords
            ):
                keyword = ident
                if spec.allowed_keywords is not None and keyword not in spec.allowed_keywords:
                    if spec.try_skip_when_disallowed and self._skip_unsupported_if_present(
                        tokens, spec.unsupported_context
                    ):
                        return
                    allowed = ", ".join(sorted(spec.allowed_keywords))
                    raise tokens._make_error(
                        f"Unknown statement in {spec.unsupported_context}: "
                        f"{keyword!r} (allowed: {allowed})"
                    )
                if spec.type_stmt is not None:
                    handler = self.registry.get_handler(f"type:{keyword}")
                    if handler:
                        if tokens.peek_type() == YangTokenType.TYPE:
                            handler(tokens, context)
                        else:
                            handler(tokens, context, spec.type_stmt)
                        return
                    if self._skip_unsupported_if_present(tokens, spec.unsupported_context):
                        return
                    raise tokens._make_error(
                        f"Unknown statement in {spec.unsupported_context}: {keyword!r}"
                    )
                handler = self.registry.get_handler(f"{key_prefix}:{keyword}")
                if handler:
                    handler(tokens, context)
                    return
                if self._skip_unsupported_if_present(tokens, spec.unsupported_context):
                    return
                raise tokens._make_error(
                    f"Unknown statement in {spec.unsupported_context}: {keyword!r}"
                )
            self._parse_prefixed_extension_statement(tokens, context)
            return

        keyword = tokens.peek() or ""

        if spec.type_stmt is not None:
            if spec.allowed_keywords is not None and keyword not in spec.allowed_keywords:
                if spec.try_skip_when_disallowed and self._skip_unsupported_if_present(
                    tokens, spec.unsupported_context
                ):
                    return
                allowed = ", ".join(sorted(spec.allowed_keywords))
                raise tokens._make_error(
                    f"Unknown statement in {spec.unsupported_context}: "
                    f"{keyword!r} (allowed: {allowed})"
                )
            handler = self.registry.get_handler(f"type:{keyword}")
            if handler:
                if tokens.peek_type() == YangTokenType.TYPE:
                    handler(tokens, context)
                else:
                    handler(tokens, context, spec.type_stmt)
                return
            if self._skip_unsupported_if_present(tokens, spec.unsupported_context):
                return
            raise tokens._make_error(
                f"Unknown statement in {spec.unsupported_context}: {keyword!r}"
            )

        if spec.allowed_keywords is not None and keyword not in spec.allowed_keywords:
            if spec.try_skip_when_disallowed and self._skip_unsupported_if_present(
                tokens, spec.unsupported_context
            ):
                return
            allowed = ", ".join(sorted(spec.allowed_keywords))
            raise tokens._make_error(
                f"Unknown statement in {spec.unsupported_context}: "
                f"{keyword!r} (allowed: {allowed})"
            )

        handler = self.registry.get_handler(f"{key_prefix}:{keyword}")
        if not handler and spec.fallback_registry_key_prefix is not None:
            handler = self.registry.get_handler(
                f"{spec.fallback_registry_key_prefix}:{keyword}"
            )
        if handler:
            handler(tokens, context)
            return
        if self._skip_unsupported_if_present(tokens, spec.unsupported_context):
            return
        raise tokens._make_error(
            f"Unknown statement in {spec.unsupported_context}: {keyword!r}"
        )

    def parse_revision_date_statement(
        self, tokens: TokenStream, context: ParserContext
    ) -> None:
        """Parse ``revision-date`` substatement (e.g. under ``include``)."""
        self._revision_parser.parse_revision_date_statement(tokens)

    def parse_reference_string_only(self, tokens: TokenStream, context: ParserContext) -> None:
        tokens.consume_type(YangTokenType.REFERENCE)
        tokens.consume_type(YangTokenType.STRING)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_extension_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        self._extension_parser.parse_extension_stmt(tokens, context)

    def parse_feature_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        self._feature_parser.parse_feature_stmt(tokens, context)

    def parse_if_feature_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        self._feature_parser.parse_if_feature_stmt(tokens, context)

    def parse_uses(
        self, tokens: TokenStream, context: ParserContext
    ) -> Optional[YangUsesStmt]:
        return self._uses_parser.parse_uses(tokens, context)

    def parse_augment(self, tokens: TokenStream, context: ParserContext) -> None:
        tokens.consume_type(YangTokenType.AUGMENT)
        path = self._parse_string_concatenation(tokens)
        aug = YangAugmentStmt(name="augment", augment_path=path)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(aug)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_statement(
                    tokens,
                    new_context,
                    StatementDispatchSpec(registry_prefix="augment", unsupported_context="augment"),
                )
            tokens.consume_type(YangTokenType.RBRACE)
        self._add_to_parent_or_module(context, aug)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
    
    def parse_description(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse description statement (optional braced extension substatements are skipped)."""
        tokens.consume_type(YangTokenType.DESCRIPTION)
        desc = tokens.consume_type(YangTokenType.STRING)
        if tokens.peek_type() == YangTokenType.LBRACE:
            _consume_balanced_braces(tokens)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        parent = context.current_parent
        if parent is not None and hasattr(parent, "description"):
            setattr(parent, "description", desc)

    def parse_optional_description(
        self, tokens: TokenStream, context: ParserContext
    ) -> None:
        """If the next token is ``description``, parse it into ``current_parent.description``."""
        if tokens.peek_type() != YangTokenType.DESCRIPTION:
            return
        self.parse_description(tokens, context)

    def parse_revision(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse revision statement."""
        self._revision_parser.parse_revision(tokens, context)

    def parse_typedef(self, tokens: TokenStream, context: ParserContext) -> Optional[YangTypedefStmt]:
        """Parse typedef statement."""
        tokens.consume_type(YangTokenType.TYPEDEF)
        typedef_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        typedef_stmt = YangTypedefStmt(name=typedef_name)
        
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(typedef_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_statement(
                    tokens,
                    new_context,
                    StatementDispatchSpec(
                        registry_prefix="typedef",
                        unsupported_context=f"typedef '{typedef_name}'",
                    ),
                )
            tokens.consume_type(YangTokenType.RBRACE)

        context.module.typedefs[typedef_name] = typedef_stmt
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return None  # Typedefs are stored in module, not returned as statements

    def parse_identity(self, tokens: TokenStream, context: ParserContext) -> None:
        self._identity_parser.parse_identity(tokens, context)

    def parse_type_base(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._type_parser.parse_type_base(tokens, context, type_stmt)

    def parse_container(self, tokens: TokenStream, context: ParserContext) -> YangContainerStmt:
        """Parse container statement."""
        tokens.consume_type(YangTokenType.CONTAINER)
        container_name = tokens.consume()  # identifier or keyword (e.g. type)
        container_stmt = YangContainerStmt(name=container_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(container_stmt)
            prev_index = -1
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                if tokens.index == prev_index:
                    raise tokens._make_error(
                        f"Infinite loop detected at token: {tokens.peek()}"
                    )
                prev_index = tokens.index
                self._parse_statement(
                    tokens,
                    new_context,
                    StatementDispatchSpec(
                        registry_prefix="container",
                        unsupported_context=f"container '{container_name}'",
                    ),
                )
            if tokens.has_more() and tokens.peek_type() == YangTokenType.RBRACE:
                tokens.consume_type(YangTokenType.RBRACE)
        self._add_to_parent_or_module(context, container_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return container_stmt

    def _parse_block(
        self,
        tokens: TokenStream,
        context: ParserContext,
        block_type: str,
        stmt: _StatementT,
        name: str,
    ) -> _StatementT:
        """Parse a braced block of statements, add stmt to parent, consume semicolon.
        Handler prefix is block_type (e.g. 'leaf-list', 'list', 'leaf').
        For block_type 'list', marks key leaf/leaves on stmt after parsing the block.
        Returns stmt.
        """
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_statement(
                    tokens,
                    new_context,
                    StatementDispatchSpec(
                        registry_prefix=block_type,
                        unsupported_context=f"{block_type} '{name}'",
                    ),
                )
            tokens.consume_type(YangTokenType.RBRACE)
        self._add_to_parent_or_module(context, stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return stmt

    def parse_list(self, tokens: TokenStream, context: ParserContext) -> YangListStmt:
        """Parse list statement."""
        tokens.consume_type(YangTokenType.LIST)
        list_name = tokens.consume()  # identifier or keyword
        return self._parse_block(tokens, context, "list", YangListStmt(name=list_name), list_name)

    def parse_leaf(self, tokens: TokenStream, context: ParserContext) -> YangLeafStmt:
        """Parse leaf statement."""
        tokens.consume_type(YangTokenType.LEAF)
        leaf_name = tokens.consume()  # identifier or keyword (e.g. type)
        return self._parse_block(tokens, context, "leaf", YangLeafStmt(name=leaf_name), leaf_name)

    def parse_leaf_list(self, tokens: TokenStream, context: ParserContext) -> YangLeafListStmt:
        """Parse leaf-list statement."""
        tokens.consume_type(YangTokenType.LEAF_LIST)
        leaf_list_name = tokens.consume()  # identifier or keyword
        return self._parse_block(
            tokens, context, "leaf-list", YangLeafListStmt(name=leaf_list_name), leaf_list_name
        )

    def parse_anydata(self, tokens: TokenStream, context: ParserContext) -> YangAnydataStmt:
        """Parse anydata statement (RFC 7950 §7.12)."""
        tokens.consume_type(YangTokenType.ANYDATA)
        n = tokens.consume()
        return self._parse_block(tokens, context, "anydata", YangAnydataStmt(name=n), n)

    def parse_anyxml(self, tokens: TokenStream, context: ParserContext) -> YangAnyxmlStmt:
        """Parse anyxml statement (RFC 7950 §7.11)."""
        tokens.consume_type(YangTokenType.ANYXML)
        n = tokens.consume()
        return self._parse_block(tokens, context, "anyxml", YangAnyxmlStmt(name=n), n)

    def parse_type(self, tokens: TokenStream, context: ParserContext) -> YangTypeStmt:
        return self._type_parser.parse_type(tokens, context)

    def parse_type_pattern(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._type_parser.parse_type_pattern(tokens, context, type_stmt)

    def parse_type_length(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._type_parser.parse_type_length(tokens, context, type_stmt)

    def parse_type_range(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._type_parser.parse_type_range(tokens, context, type_stmt)

    def parse_type_fraction_digits(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._type_parser.parse_type_fraction_digits(tokens, context, type_stmt)

    def parse_type_enum(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._type_parser.parse_type_enum(tokens, context, type_stmt)

    def parse_type_bit(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._bits_parser.parse_type_bit(tokens, context, type_stmt)

    def parse_type_path(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._type_parser.parse_type_path(tokens, context, type_stmt)

    def parse_type_require_instance(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        self._type_parser.parse_type_require_instance(tokens, context, type_stmt)

    def parse_list_key(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse key in list statement."""
        tokens.consume_type(YangTokenType.KEY)
        if context.current_parent and isinstance(context.current_parent, YangListStmt):
            value, _ = tokens.consume_oneof([YangTokenType.STRING, YangTokenType.IDENTIFIER])
            context.current_parent.key = value
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_min_elements(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse min-elements (list, leaf-list, or refine)."""
        tokens.consume_type(YangTokenType.MIN_ELEMENTS)
        value = int(tokens.consume_type(YangTokenType.INTEGER))
        parent = context.current_parent
        if isinstance(parent, YangRefineStmt):
            parent.min_elements = value
        elif parent and hasattr(parent, "min_elements"):
            setattr(parent, "min_elements", value)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_max_elements(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse max-elements (list, leaf-list, or refine)."""
        tokens.consume_type(YangTokenType.MAX_ELEMENTS)
        value = int(tokens.consume_type(YangTokenType.INTEGER))
        parent = context.current_parent
        if isinstance(parent, YangRefineStmt):
            parent.max_elements = value
        elif parent and hasattr(parent, "max_elements"):
            setattr(parent, "max_elements", value)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_ordered_by(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse ordered-by under list or leaf-list (RFC 7950 §7.7.1).

        xYang does not track user vs system ordering in validation; the statement is accepted
        and discarded after syntax check.
        """
        tokens.consume_type(YangTokenType.ORDERED_BY)
        arg = tokens.consume()
        if arg not in ("user", "system"):
            raise tokens._make_error(f"ordered-by must be 'user' or 'system', got {arg!r}")
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_leaf_mandatory(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse mandatory in leaf / anydata / anyxml."""
        tokens.consume_type(YangTokenType.MANDATORY)
        parent = context.current_parent
        if isinstance(parent, (YangLeafStmt, YangAnydataStmt, YangAnyxmlStmt)):
            _, tt = tokens.consume_oneof([YangTokenType.TRUE, YangTokenType.FALSE])
            parent.mandatory = tt == YangTokenType.TRUE
        tokens.consume_if_type(YangTokenType.SEMICOLON)
    
    def _parse_default_value_tokens(self, tokens: TokenStream) -> str | int:
        """Consume a YANG ``default`` value (after the ``default`` keyword)."""
        tt = tokens.peek_type()
        if tt == YangTokenType.STRING:
            return tokens.consume_type(YangTokenType.STRING)
        if tt == YangTokenType.INTEGER:
            return tokens.consume_type(YangTokenType.INTEGER)
        if tt == YangTokenType.IDENTIFIER:
            return tokens.consume_type(YangTokenType.IDENTIFIER)
        if tt == YangTokenType.TRUE:
            tokens.consume_type(YangTokenType.TRUE)
            return "true"
        if tt == YangTokenType.FALSE:
            tokens.consume_type(YangTokenType.FALSE)
            return "false"
        raise tokens._make_error(
            f"Expected default value (string, integer, identifier, or true/false), "
            f"got {tt.name if tt else 'end'}"
        )

    def parse_leaf_default(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse default in leaf statement."""
        tokens.consume_type(YangTokenType.DEFAULT)
        if context.current_parent and isinstance(context.current_parent, YangLeafStmt):
            context.current_parent.default = self._parse_default_value_tokens(tokens)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_presence(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse presence statement for container."""
        tokens.consume_type(YangTokenType.PRESENCE)
        if context.current_parent and isinstance(context.current_parent, YangContainerStmt):
            context.current_parent.presence = tokens.consume_type(YangTokenType.STRING)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def _parse_string_concatenation(self, tokens: TokenStream) -> str:
        """Consume one or more STRING tokens with optional PLUS between; return concatenated string."""
        parts = [tokens.consume_type(YangTokenType.STRING)]
        while tokens.peek_type() == YangTokenType.PLUS:
            tokens.consume_type(YangTokenType.PLUS)
            parts.append(tokens.consume_type(YangTokenType.STRING))
        return ''.join(parts)

    def parse_must(self, tokens: TokenStream, context: ParserContext) -> YangMustStmt:
        """Parse must statement. Argument is one or more string tokens (YANG allows + concatenation)."""
        tokens.consume_type(YangTokenType.MUST)
        expression = self._parse_string_concatenation(tokens)
        must_stmt = YangMustStmt(expression=expression)
        
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(must_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_statement(
                    tokens,
                    new_context,
                    StatementDispatchSpec(
                        registry_prefix="must",
                        unsupported_context="must",
                        allowed_keywords=frozenset({"error-message", "description"}),
                        try_skip_when_disallowed=True,
                    ),
                )
            tokens.consume_type(YangTokenType.RBRACE)
        # Add to appropriate parent (leaf, leaf-list, container, list, refine)
        if isinstance(context.current_parent, YangStatementWithMust):
            context.current_parent.must_statements.append(must_stmt)
        # For YangListStmt, parse_list_must also appends; both paths are valid
        
        # Consume semicolon if present (optional for must statements in containers/lists)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return must_stmt

    def parse_must_error_message(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse error-message in must statement."""
        tokens.consume_type(YangTokenType.ERROR_MESSAGE)
        if context.current_parent and isinstance(context.current_parent, YangMustStmt):
            context.current_parent.error_message = tokens.consume_type(YangTokenType.STRING)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_when(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse when statement. Argument is string (with optional + concatenation). Uses xpath.

        RFC 7950 allows optional substatements ``description`` and ``reference`` in the braced form;
        xYang currently supports ``description`` only.
        """
        tokens.consume_type(YangTokenType.WHEN)
        condition = self._parse_string_concatenation(tokens)
        when_stmt = YangWhenStmt(expression=condition)
        parent_for_when = context.current_parent
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(when_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_statement(
                    tokens,
                    new_context,
                    StatementDispatchSpec(
                        registry_prefix="when",
                        unsupported_context="when",
                        allowed_keywords=frozenset({"description"}),
                        try_skip_when_disallowed=True,
                    ),
                )
            tokens.consume_type(YangTokenType.RBRACE)
        if parent_for_when and isinstance(parent_for_when, YangStatementWithWhen):
            parent_for_when.when = when_stmt
        tokens.consume_if_type(YangTokenType.SEMICOLON)
    
    def parse_grouping(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse grouping statement."""
        tokens.consume_type(YangTokenType.GROUPING)
        grouping_name = tokens.consume()  # identifier or keyword
        grouping_stmt = YangGroupingStmt(name=grouping_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(grouping_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_statement(
                    tokens,
                    new_context,
                    StatementDispatchSpec(
                        registry_prefix="grouping",
                        unsupported_context=f"grouping '{grouping_name}'",
                    ),
                )
            tokens.consume_type(YangTokenType.RBRACE)
        context.module.groupings[grouping_name] = grouping_stmt
        tokens.consume_if_type(YangTokenType.SEMICOLON)
    
    def parse_refine(self, tokens: TokenStream, context: ParserContext) -> None:
        self._refine_parser.parse_refine(tokens, context)
    
    def parse_choice(self, tokens: TokenStream, context: ParserContext) -> YangChoiceStmt:
        """Parse choice statement."""
        tokens.consume_type(YangTokenType.CHOICE)
        choice_name = tokens.consume()  # identifier or keyword
        choice_stmt = YangChoiceStmt(name=choice_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(choice_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_statement(
                    tokens,
                    new_context,
                    StatementDispatchSpec(
                        registry_prefix="choice",
                        unsupported_context=f"choice '{choice_name}'",
                    ),
                )
            tokens.consume_type(YangTokenType.RBRACE)
            choice_stmt.validate_case_unique_child_names()
        self._add_to_parent_or_module(context, choice_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return choice_stmt
    
    def parse_case(self, tokens: TokenStream, context: ParserContext) -> YangCaseStmt:
        """Parse case statement."""
        tokens.consume_type(YangTokenType.CASE)
        case_name = tokens.consume()  # identifier or keyword
        case_stmt = YangCaseStmt(name=case_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(case_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                self._parse_statement(
                    tokens,
                    new_context,
                    StatementDispatchSpec(
                        registry_prefix="case",
                        unsupported_context=f"case '{case_name}'",
                    ),
                )
            tokens.consume_type(YangTokenType.RBRACE)
        if context.current_parent and isinstance(context.current_parent, YangChoiceStmt):
            context.current_parent.cases.append(case_stmt)
        else:
            self._add_to_parent_or_module(context, case_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return case_stmt

    def parse_choice_mandatory(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse mandatory statement in choice."""
        tokens.consume_type(YangTokenType.MANDATORY)
        _, tt = tokens.consume_oneof([YangTokenType.TRUE, YangTokenType.FALSE])
        if context.current_parent and isinstance(context.current_parent, YangChoiceStmt):
            context.current_parent.mandatory = tt == YangTokenType.TRUE
        tokens.consume_if_type(YangTokenType.SEMICOLON)
    
    def _copy_statement(self, stmt: 'YangStatement') -> 'YangStatement':
        """Create a copy of a statement, handling AST nodes properly."""
        return copy_yang_statement(stmt)

    def _apply_refine(self, stmt: 'YangStatement', refine: 'YangRefineStmt') -> None:
        """Apply refine modifications to a statement."""
        from ..refine_expand import apply_refine_to_node

        apply_refine_to_node(stmt, refine)
