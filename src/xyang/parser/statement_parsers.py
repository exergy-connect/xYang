"""
Statement parsers for YANG statements.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING, TypeVar
from .parser_context import TokenStream, ParserContext, YangTokenType
from ..ast import (
    YangBitStmt,
    YangContainerStmt, YangListStmt, YangLeafStmt,
    YangLeafListStmt, YangTypeStmt, YangMustStmt, YangWhenStmt, YangTypedefStmt,
    YangIdentityStmt,
    YangGroupingStmt, YangUsesStmt, YangAugmentStmt, YangRefineStmt, YangChoiceStmt, YangCaseStmt,
    YangStatementList, YangStatementWithMust,
    YangStatementWithWhen,
)
from ..xpath import XPathParser

from ..refine_expand import apply_refines_by_path, copy_yang_statement

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

    def parse_module(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse module statement."""
        tokens.consume_type(YangTokenType.MODULE)
        module_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        tokens.consume_type(YangTokenType.LBRACE)

        context.module.name = module_name

        # Parse module body
        # Nested parsers (container, list, etc.) handle their own braces
        # So we just need to stop when we see the module's closing brace
        while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
            self._parse_module_statement(tokens, context)

        # Consume the module's closing brace
        tokens.consume_type(YangTokenType.RBRACE)

    def _parse_module_statement(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse a statement in module body."""
        stmt_type = tokens.peek() or ""
        handler = self.registry.get_handler(f"module:{stmt_type}")
        if handler:
            handler(tokens, context)
        else:
            # Unknown statement - raise error instead of silently skipping
            raise tokens._make_error(f"Unknown statement in module: {stmt_type}")

    def parse_submodule(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse submodule statement (YANG 1.1)."""
        tokens.consume_type(YangTokenType.SUBMODULE)
        submodule_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        tokens.consume_type(YangTokenType.LBRACE)
        context.module.name = submodule_name
        while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
            self._parse_submodule_statement(tokens, context)
        tokens.consume_type(YangTokenType.RBRACE)

    def _parse_submodule_statement(self, tokens: TokenStream, context: ParserContext) -> None:
        stmt_type = tokens.peek() or ""
        handler = self.registry.get_handler(f"submodule:{stmt_type}")
        if handler:
            handler(tokens, context)
        else:
            raise tokens._make_error(f"Unknown statement in submodule: {stmt_type}")

    def parse_import_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse import and load the referenced module (RFC 7950)."""
        tokens.consume_type(YangTokenType.IMPORT)
        imported_module_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        if tokens.consume_if_type(YangTokenType.SEMICOLON):
            return
        local_prefix: Optional[str] = None
        revision_date: Optional[str] = None
        if not tokens.consume_if_type(YangTokenType.LBRACE):
            raise tokens._make_error("Expected '{' or ';' after import module name")
        while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
            st = tokens.peek() or ""
            if st == "prefix":
                tokens.consume_type(YangTokenType.PREFIX)
                tt = tokens.peek_type()
                if tt == YangTokenType.STRING:
                    local_prefix = tokens.consume_type(YangTokenType.STRING)
                elif tt == YangTokenType.IDENTIFIER:
                    local_prefix = tokens.consume_type(YangTokenType.IDENTIFIER)
                else:
                    raise tokens._make_error(
                        f"Expected prefix string or identifier, got {tt.name if tt else 'end'}"
                    )
                tokens.consume_if_type(YangTokenType.SEMICOLON)
            elif st == "revision-date":
                tokens.consume_type(YangTokenType.REVISION_DATE)
                revision_date = self._revision_date_argument_string(tokens)
                tokens.consume_if_type(YangTokenType.SEMICOLON)
            elif st == "description":
                self.parse_description_string_only(tokens, context)
            elif st == "reference":
                self.parse_reference_string_only(tokens, context)
            else:
                raise tokens._make_error(f"Unknown statement in import: {st!r}")
        tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        if self._yang_parser is not None and local_prefix:
            self._yang_parser.register_import(
                parent=context.module,
                imported_module_name=imported_module_name,
                local_prefix=local_prefix,
                revision_date=revision_date,
                source_dir=context.source_dir,
                tokens=tokens,
            )

    def parse_include_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse include and merge the submodule into the current module (RFC 7950)."""
        tokens.consume_type(YangTokenType.INCLUDE)
        sub_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        revision_date: Optional[str] = None
        if tokens.consume_if_type(YangTokenType.LBRACE):
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                st = tokens.peek() or ""
                if st == "revision-date":
                    tokens.consume_type(YangTokenType.REVISION_DATE)
                    revision_date = self._revision_date_argument_string(tokens)
                    tokens.consume_if_type(YangTokenType.SEMICOLON)
                else:
                    handler = self.registry.get_handler(f"include:{st}")
                    if handler:
                        handler(tokens, context)
                    else:
                        raise tokens._make_error(f"Unknown statement in include: {st!r}")
            tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        if self._yang_parser is not None:
            self._yang_parser.merge_included_submodule(
                parent=context.module,
                submodule_name=sub_name,
                revision_date=revision_date,
                source_dir=context.source_dir,
                tokens=tokens,
            )

    def parse_prefix_value_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        """Prefix substatement inside import or belongs-to (not module-level prefix)."""
        tokens.consume_type(YangTokenType.PREFIX)
        self._consume_prefix_argument(tokens)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def _revision_date_argument_string(self, tokens: TokenStream) -> str:
        """Read revision-date value; does not consume the trailing semicolon."""
        tt0 = tokens.peek_type()
        if tt0 == YangTokenType.STRING:
            return tokens.consume_type(YangTokenType.STRING)
        chunks: list[str] = []
        while tokens.has_more() and tokens.peek_type() != YangTokenType.SEMICOLON:
            tt = tokens.peek_type()
            if tt in (
                YangTokenType.IDENTIFIER,
                YangTokenType.DOTTED_NUMBER,
                YangTokenType.INTEGER,
            ):
                chunks.append(tokens.consume_type(tt))
            else:
                break
        if not chunks:
            raise tokens._make_error(
                f"Expected revision-date value, got {tt0.name if tt0 else 'end'}"
            )
        return "".join(chunks)

    def parse_revision_date_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse revision-date substatement."""
        tokens.consume_type(YangTokenType.REVISION_DATE)
        self._revision_date_argument_string(tokens)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_description_string_only(self, tokens: TokenStream, context: ParserContext) -> None:
        """Description with no parent field update (e.g. inside import)."""
        tokens.consume_type(YangTokenType.DESCRIPTION)
        tokens.consume_type(YangTokenType.STRING)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_reference_string_only(self, tokens: TokenStream, context: ParserContext) -> None:
        tokens.consume_type(YangTokenType.REFERENCE)
        tokens.consume_type(YangTokenType.STRING)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_feature_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        tokens.consume_type(YangTokenType.FEATURE)
        name = tokens.consume_type(YangTokenType.IDENTIFIER)
        context.module.features.add(name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            holder = SimpleNamespace(if_features=[])
            feat_ctx = context.push_parent(holder)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                st = tokens.peek() or ""
                if st == "if-feature":
                    self.parse_if_feature_stmt(tokens, feat_ctx)
                elif st == "description":
                    self.parse_description_string_only(tokens, feat_ctx)
                elif st == "reference":
                    self.parse_reference_string_only(tokens, feat_ctx)
                else:
                    raise tokens._make_error(
                        f"Unknown statement in feature '{name}': {st!r}"
                    )
            tokens.consume_type(YangTokenType.RBRACE)
            if holder.if_features:
                if name in context.module.feature_if_features:
                    raise tokens._make_error(
                        f"Duplicate if-feature block for feature {name!r}"
                    )
                context.module.feature_if_features[name] = list(holder.if_features)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_if_feature_stmt(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse if-feature; expression is stored on the parent schema node (not evaluated)."""
        tokens.consume_type(YangTokenType.IF_FEATURE)
        expression = self._parse_string_concatenation(tokens)
        parent = context.current_parent
        if parent is not None and hasattr(parent, "if_features"):
            parent.if_features.append(expression)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                st = tokens.peek() or ""
                if st == "description":
                    self.parse_description_string_only(tokens, context)
                elif st == "reference":
                    self.parse_reference_string_only(tokens, context)
                else:
                    raise tokens._make_error(f"Unknown statement in if-feature: {st!r}")
            tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_belongs_to(self, tokens: TokenStream, context: ParserContext) -> None:
        tokens.consume_type(YangTokenType.BELONGS_TO)
        parent_module = tokens.consume_type(YangTokenType.IDENTIFIER)
        context.module.belongs_to_module = parent_module
        tokens.consume_type(YangTokenType.LBRACE)
        while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
            st = tokens.peek() or ""
            handler = self.registry.get_handler(f"belongs-to:{st}")
            if handler:
                handler(tokens, context)
            else:
                raise tokens._make_error(f"Unknown statement in belongs-to: {st!r}")
        tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_augment(self, tokens: TokenStream, context: ParserContext) -> None:
        tokens.consume_type(YangTokenType.AUGMENT)
        path = self._parse_string_concatenation(tokens)
        aug = YangAugmentStmt(name="augment", augment_path=path)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(aug)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                st = tokens.peek() or ""
                handler = self.registry.get_handler(f"augment:{st}")
                if handler:
                    handler(tokens, new_context)
                else:
                    raise tokens._make_error(f"Unknown statement in augment: {st!r}")
            tokens.consume_type(YangTokenType.RBRACE)
        self._add_to_parent_or_module(context, aug)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
    
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
        """Parse prefix statement."""
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
        org = tokens.consume_type(YangTokenType.STRING)
        context.module.organization = org
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_contact(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse contact statement."""
        tokens.consume_type(YangTokenType.CONTACT)
        contact = tokens.consume_type(YangTokenType.STRING)
        context.module.contact = contact
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_description(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse description statement."""
        tokens.consume_type(YangTokenType.DESCRIPTION)
        desc = tokens.consume_type(YangTokenType.STRING)
        if context.current_parent and hasattr(context.current_parent, "description"):
            setattr(context.current_parent, "description", desc)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_revision(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse revision statement."""
        tokens.consume_type(YangTokenType.REVISION)
        tt0 = tokens.peek_type()
        if tt0 == YangTokenType.STRING:
            date = tokens.consume_type(YangTokenType.STRING)
        else:
            chunks: list[str] = []
            while tokens.has_more() and tokens.peek_type() not in (
                YangTokenType.LBRACE,
                YangTokenType.SEMICOLON,
            ):
                tt = tokens.peek_type()
                if tt in (
                    YangTokenType.IDENTIFIER,
                    YangTokenType.DOTTED_NUMBER,
                    YangTokenType.INTEGER,
                ):
                    chunks.append(tokens.consume_type(tt))
                else:
                    break
            date = "".join(chunks)
            if not date:
                raise tokens._make_error(
                    f"Expected revision date, got {tt0.name if tt0 else 'end'}"
                )
        revision = {'date': date, 'description': ''}
        if tokens.consume_if_type(YangTokenType.LBRACE):
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                if tokens.peek_type() == YangTokenType.DESCRIPTION:
                    tokens.consume_type(YangTokenType.DESCRIPTION)
                    revision['description'] = tokens.consume_type(YangTokenType.STRING)
                    tokens.consume_if_type(YangTokenType.SEMICOLON)
                else:
                    raise tokens._make_error(f"Unknown statement in revision: {tokens.peek()}")
            tokens.consume_type(YangTokenType.RBRACE)
        context.module.revisions.append(revision)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
    
    def parse_typedef(self, tokens: TokenStream, context: ParserContext) -> Optional[YangTypedefStmt]:
        """Parse typedef statement."""
        tokens.consume_type(YangTokenType.TYPEDEF)
        typedef_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        typedef_stmt = YangTypedefStmt(name=typedef_name)
        
        if tokens.consume_if('{'):
            new_context = context.push_parent(typedef_stmt)
            while tokens.has_more() and tokens.peek() != '}':
                handler = self.registry.get_handler(f"typedef:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                else:
                    raise tokens._make_error(f"Unknown statement in typedef '{typedef_name}': {tokens.peek()}")
            tokens.consume('}')
        
        context.module.typedefs[typedef_name] = typedef_stmt
        tokens.consume_if(';')
        return None  # Typedefs are stored in module, not returned as statements

    def parse_identity(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse identity statement."""
        tokens.consume_type(YangTokenType.IDENTITY)
        identity_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        identity_stmt = YangIdentityStmt(name=identity_name)
        if tokens.peek_type() == YangTokenType.LBRACE:
            tokens.consume_type(YangTokenType.LBRACE)
            new_context = context.push_parent(identity_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                handler = self.registry.get_handler(f"identity:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                else:
                    raise tokens._make_error(
                        f"Unknown statement in identity '{identity_name}': {tokens.peek()}"
                    )
            tokens.consume_type(YangTokenType.RBRACE)
        context.module.identities[identity_name] = identity_stmt
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_identity_base(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse base substatement inside identity."""
        tokens.consume_type(YangTokenType.BASE)
        base_name = self._consume_qname_from_identifier(tokens)
        parent = context.current_parent
        if isinstance(parent, YangIdentityStmt):
            parent.bases.append(base_name)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_type_base(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse base substatement inside identityref type."""
        tokens.consume_type(YangTokenType.BASE)
        base_name = tokens.consume_type(YangTokenType.IDENTIFIER)
        type_stmt.identityref_bases.append(base_name)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

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
                handler = self.registry.get_handler(f"container:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                else:
                    raise tokens._make_error(f"Unknown statement in container '{container_name}': {tokens.peek()}")
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
                handler = self.registry.get_handler(f"{block_type}:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                else:
                    raise tokens._make_error(
                        f"Unknown statement in {block_type} '{name}': {tokens.peek()}"
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

    def parse_type(self, tokens: TokenStream, context: ParserContext) -> YangTypeStmt:
        """Parse type statement."""
        tokens.consume_type(YangTokenType.TYPE)
        if tokens.peek_type() == YangTokenType.IDENTIFIER:
            type_name = self._consume_qname_from_identifier(tokens)
        else:
            type_name = tokens.consume()
        type_stmt = YangTypeStmt(name=type_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            brace_depth = 1
            type_context = context.push_parent(type_stmt)
            while tokens.has_more() and brace_depth > 0:
                if tokens.peek_type() == YangTokenType.LBRACE:
                    brace_depth += 1
                    tokens.consume_type(YangTokenType.LBRACE)
                elif tokens.peek_type() == YangTokenType.RBRACE:
                    brace_depth -= 1
                    if brace_depth == 0:
                        tokens.consume_type(YangTokenType.RBRACE)
                        break
                    tokens.consume_type(YangTokenType.RBRACE)
                elif brace_depth == 1:
                    handler = self.registry.get_handler(f"type:{tokens.peek()}")
                    if handler:
                        if tokens.peek_type() == YangTokenType.TYPE:
                            handler(tokens, type_context)
                        else:
                            handler(tokens, type_context, type_stmt)
                    else:
                        raise tokens._make_error(f"Unknown statement in type '{type_name}': {tokens.peek()}")
                else:
                    tokens.consume()  # Skip nested braces content
        if type_stmt.name == "enumeration" and not type_stmt.enums:
            raise tokens._make_error(
                'enumeration type requires at least one "enum" statement (RFC 7950)'
            )
        if type_stmt.name == "bits":
            if not type_stmt.bits:
                raise tokens._make_error(
                    'bits type requires at least one "bit" statement (RFC 7950)'
                )
            self._finalize_bits_type(type_stmt, tokens)
        if type_stmt.name == "identityref" and not type_stmt.identityref_bases:
            raise tokens._make_error(
                'identityref type requires at least one "base" statement (RFC 7950)'
            )
        # Assign to parent (use setattr: current_parent is typed as YangStatementList which has no type/types)
        parent = context.current_parent
        if parent:
            if isinstance(parent, YangTypeStmt) and parent.name == 'union':
                self._append_attr_list(parent, 'types', type_stmt)
            elif hasattr(parent, 'type') and not getattr(parent, 'type', None):
                setattr(parent, 'type', type_stmt)
            elif hasattr(parent, 'types'):
                self._append_attr_list(parent, 'types', type_stmt)
            elif hasattr(parent, 'type') and getattr(parent, 'type', None):
                parent_type = getattr(parent, 'type', None)
                if parent_type is not None:
                    self._append_attr_list(parent_type, 'types', type_stmt)
        
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return type_stmt

    def parse_type_pattern(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse pattern constraint."""
        tokens.consume_type(YangTokenType.PATTERN)
        pattern = tokens.consume_type(YangTokenType.STRING)
        type_stmt.pattern = pattern
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
        """Parse enum constraint."""
        tokens.consume_type(YangTokenType.ENUM)
        enum_name = tokens.consume()  # identifier or keyword (e.g. string, boolean)
        type_stmt.enums.append(enum_name)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def _consume_bit_block_description(self, tokens: TokenStream) -> None:
        """Skip a ``description`` substatement inside ``bit { ... }`` (value not stored on AST)."""
        tokens.consume_type(YangTokenType.DESCRIPTION)
        tokens.consume_type(YangTokenType.STRING)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                if tokens.peek_type() == YangTokenType.DESCRIPTION:
                    self._consume_bit_block_description(tokens)
                else:
                    raise tokens._make_error(
                        f"Unknown statement in bit description block: {tokens.peek()!r}"
                    )
            tokens.consume_type(YangTokenType.RBRACE)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_type_bit(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse ``bit`` substatement under ``type bits { ... }`` (RFC 7950 §9.3.4)."""
        tokens.consume_type(YangTokenType.BIT)
        bit_name = tokens.consume()
        explicit_pos: Optional[int] = None
        if tokens.consume_if_type(YangTokenType.LBRACE):
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                pt = tokens.peek_type()
                if pt == YangTokenType.POSITION:
                    tokens.consume_type(YangTokenType.POSITION)
                    if explicit_pos is not None:
                        raise tokens._make_error("Duplicate position in bit statement")
                    explicit_pos = int(tokens.consume_type(YangTokenType.INTEGER))
                    tokens.consume_if_type(YangTokenType.SEMICOLON)
                elif pt == YangTokenType.DESCRIPTION:
                    self._consume_bit_block_description(tokens)
                else:
                    raise tokens._make_error(
                        f"Unknown statement in bit: {tokens.peek()!r} "
                        f"(only position and description allowed)"
                    )
            tokens.consume_type(YangTokenType.RBRACE)
        type_stmt.bits.append(YangBitStmt(name=bit_name, position=explicit_pos))
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def _finalize_bits_type(self, type_stmt: YangTypeStmt, tokens: TokenStream) -> None:
        """Assign implicit bit positions; validate unique names and positions (RFC 7950 §9.3.4).

        Positions are resolved in **declaration order**: an implicit bit uses the largest
        position already assigned at that point (+1), or 0 if none yet.
        """
        seen_names: set[str] = set()
        used_positions: set[int] = set()
        for b in type_stmt.bits:
            if b.name in seen_names:
                raise tokens._make_error(f"Duplicate bit name {b.name!r} in bits type")
            seen_names.add(b.name)
            if b.position is not None:
                p = b.position
                if p < 0:
                    raise tokens._make_error(f"Invalid negative position {p} for bit {b.name!r}")
                if p in used_positions:
                    raise tokens._make_error(
                        f"Duplicate position {p} for bit {b.name!r} in bits type"
                    )
                used_positions.add(p)
            else:
                p = 0 if not used_positions else max(used_positions) + 1
                b.position = p
                used_positions.add(p)

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
        """Parse mandatory in leaf statement."""
        tokens.consume_type(YangTokenType.MANDATORY)
        if context.current_parent and isinstance(context.current_parent, YangLeafStmt):
            _, tt = tokens.consume_oneof([YangTokenType.TRUE, YangTokenType.FALSE])
            context.current_parent.mandatory = tt == YangTokenType.TRUE
        tokens.consume_if_type(YangTokenType.SEMICOLON)
    
    def parse_leaf_default(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse default in leaf statement."""
        tokens.consume_type(YangTokenType.DEFAULT)
        if context.current_parent and isinstance(context.current_parent, YangLeafStmt):
            tt = tokens.peek_type()
            if tt == YangTokenType.STRING:
                context.current_parent.default = tokens.consume_type(YangTokenType.STRING)
            elif tt == YangTokenType.INTEGER:
                context.current_parent.default = tokens.consume_type(YangTokenType.INTEGER)
            elif tt == YangTokenType.IDENTIFIER:
                context.current_parent.default = tokens.consume_type(YangTokenType.IDENTIFIER)
            elif tt == YangTokenType.TRUE:
                tokens.consume_type(YangTokenType.TRUE)
                context.current_parent.default = "true"
            elif tt == YangTokenType.FALSE:
                tokens.consume_type(YangTokenType.FALSE)
                context.current_parent.default = "false"
            else:
                raise tokens._make_error(
                    f"Expected default value (string, integer, identifier, or true/false), "
                    f"got {tt.name if tt else 'end'}"
                )
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
                if tokens.peek_type() == YangTokenType.ERROR_MESSAGE:
                    self.parse_must_error_message(tokens, new_context)
                elif tokens.peek_type() == YangTokenType.DESCRIPTION:
                    self.parse_description(tokens, new_context)
                else:
                    raise tokens._make_error(
                        f"Unknown statement in must: {tokens.peek()!r} "
                        f"(only error-message and description allowed)"
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
                if tokens.peek_type() == YangTokenType.DESCRIPTION:
                    self.parse_description(tokens, new_context)
                else:
                    raise tokens._make_error(
                        f"Unknown statement in when: {tokens.peek()!r} "
                        f"(only description allowed)"
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
                handler = self.registry.get_handler(f"grouping:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                else:
                    pt = tokens.peek_type()
                    if pt == YangTokenType.CONTAINER:
                        self.parse_container(tokens, new_context)
                    elif pt == YangTokenType.LIST:
                        self.parse_list(tokens, new_context)
                    elif pt == YangTokenType.LEAF:
                        self.parse_leaf(tokens, new_context)
                    elif pt == YangTokenType.LEAF_LIST:
                        self.parse_leaf_list(tokens, new_context)
                    elif pt == YangTokenType.USES:
                        self.parse_uses(tokens, new_context)
                    elif pt == YangTokenType.DESCRIPTION:
                        self.parse_description(tokens, new_context)
                    else:
                        raise tokens._make_error(f"Unknown statement in grouping '{grouping_name}': {tokens.peek()}")
            tokens.consume_type(YangTokenType.RBRACE)
        context.module.groupings[grouping_name] = grouping_stmt
        tokens.consume_if_type(YangTokenType.SEMICOLON)
    
    def parse_uses(self, tokens: TokenStream, context: ParserContext) -> Optional[YangUsesStmt]:
        """Parse uses statement.
        Uses statements are stored temporarily and expanded after all groupings
        have been parsed. A YangUsesStmt node is created as a placeholder.
        """
        tokens.consume_type(YangTokenType.USES)
        if tokens.peek_type() == YangTokenType.IDENTIFIER:
            grouping_name = self._consume_qname_from_identifier(tokens)
        else:
            grouping_name = tokens.consume()
        uses_stmt = YangUsesStmt(name="uses", grouping_name=grouping_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(uses_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                handler = self.registry.get_handler(f"uses:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                else:
                    raise tokens._make_error(
                        f"Unknown statement in uses '{grouping_name}': {tokens.peek()}"
                    )
            tokens.consume_type(YangTokenType.RBRACE)
        self._add_to_parent_or_module(context, uses_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return uses_stmt
    
    def parse_refine(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse refine statement (supports descendant paths ``a/b``)."""
        tokens.consume_type(YangTokenType.REFINE)
        parts = [tokens.consume()]
        while tokens.peek_type() == YangTokenType.SLASH:
            tokens.consume_type(YangTokenType.SLASH)
            parts.append(tokens.consume())
        target_path = "/".join(parts)
        refine_stmt = YangRefineStmt(name="refine", target_path=target_path)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(refine_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                handler = self.registry.get_handler(f"refine:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                elif tokens.peek_type() == YangTokenType.MUST:
                    self.parse_must(tokens, new_context)
                elif tokens.peek_type() == YangTokenType.DESCRIPTION:
                    self.parse_description(tokens, new_context)
                elif tokens.peek_type() == YangTokenType.TYPE:
                    self.parse_type(tokens, new_context)
                elif tokens.peek_type() == YangTokenType.DEFAULT:
                    tokens.consume()  # Skip for now
                else:
                    raise tokens._make_error(f"Unknown statement in refine '{target_path}': {tokens.peek()}")
            tokens.consume_type(YangTokenType.RBRACE)
        if context.current_parent and isinstance(context.current_parent, YangUsesStmt):
            context.current_parent.refines.append(refine_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
    
    def parse_choice(self, tokens: TokenStream, context: ParserContext) -> YangChoiceStmt:
        """Parse choice statement."""
        tokens.consume_type(YangTokenType.CHOICE)
        choice_name = tokens.consume()  # identifier or keyword
        choice_stmt = YangChoiceStmt(name=choice_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(choice_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                handler = self.registry.get_handler(f"choice:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                else:
                    raise tokens._make_error(f"Unknown statement in choice '{choice_name}': {tokens.peek()}")
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
                handler = self.registry.get_handler(f"case:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                elif tokens.peek_type() == YangTokenType.LEAF:
                    self.parse_leaf(tokens, new_context)
                elif tokens.peek_type() == YangTokenType.CONTAINER:
                    self.parse_container(tokens, new_context)
                elif tokens.peek_type() == YangTokenType.LIST:
                    self.parse_list(tokens, new_context)
                elif tokens.peek_type() == YangTokenType.LEAF_LIST:
                    self.parse_leaf_list(tokens, new_context)
                elif tokens.peek_type() == YangTokenType.CHOICE:
                    self.parse_choice(tokens, new_context)
                elif tokens.peek_type() == YangTokenType.DESCRIPTION:
                    self.parse_description(tokens, new_context)
                else:
                    raise tokens._make_error(f"Unknown statement in case '{case_name}': {tokens.peek()}")
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

    def parse_refine_mandatory(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse mandatory in refine (RFC 7950 §7.13.2: leaf / choice target)."""
        tokens.consume_type(YangTokenType.MANDATORY)
        _, tt = tokens.consume_oneof([YangTokenType.TRUE, YangTokenType.FALSE])
        parent = context.current_parent
        if isinstance(parent, YangRefineStmt):
            parent.refined_mandatory = tt == YangTokenType.TRUE
        tokens.consume_if_type(YangTokenType.SEMICOLON)
    
    def _expand_uses(
        self,
        grouping: "YangStatement",
        refines: list,
        module: Optional["YangModule"] = None,
    ) -> list:
        """Legacy helper: expand nested ``uses`` inside a grouping (rarely used)."""
        from ..ast import YangUsesStmt

        expanded = []
        for stmt in grouping.statements:
            if isinstance(stmt, YangUsesStmt):
                nested_grouping = module.get_grouping(stmt.grouping_name) if module else None
                if nested_grouping:
                    body = [copy_yang_statement(s) for s in nested_grouping.statements]
                    nested_expanded = self._expand_uses(
                        YangGroupingStmt(name="", statements=body),
                        stmt.refines,
                        module,
                    )
                    expanded.extend(nested_expanded)
            else:
                stmt_copy = self._copy_statement(stmt)
                apply_refines_by_path([stmt_copy], refines)
                expanded.append(stmt_copy)

        return expanded
    
    def _expand_uses_with_statements(
        self,
        statements: list,
        refines: list,
        module: Optional["YangModule"] = None,
    ) -> list:
        """Apply path-based refines to an already-expanded statement list (legacy helper)."""
        apply_refines_by_path(statements, refines)
        return statements
    
    def _copy_statement(self, stmt: 'YangStatement') -> 'YangStatement':
        """Create a copy of a statement, handling AST nodes properly."""
        return copy_yang_statement(stmt)

    def _apply_refine(self, stmt: 'YangStatement', refine: 'YangRefineStmt') -> None:
        """Apply refine modifications to a statement."""
        from ..refine_expand import apply_refine_to_node

        apply_refine_to_node(stmt, refine)