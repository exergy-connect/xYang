"""
Statement parsers for YANG statements.
"""

from typing import Optional, TYPE_CHECKING, TypeVar
from .parser_context import TokenStream, ParserContext, YangTokenType
from ..ast import (
    YangContainerStmt, YangListStmt, YangLeafStmt,
    YangLeafListStmt, YangTypeStmt, YangMustStmt, YangWhenStmt, YangTypedefStmt,
    YangGroupingStmt, YangUsesStmt, YangRefineStmt, YangChoiceStmt, YangCaseStmt,
    YangStatementList, YangStatementWithMust,
    YangStatementWithWhen,
)
from ..xpath import XPathParser
from types import SimpleNamespace

from ..refine_expand import apply_refines_by_path, copy_yang_statement

if TYPE_CHECKING:
    from .statement_registry import StatementRegistry
    from ..ast import YangStatement
    from ..module import YangModule

# Generic statement type used for blocks like container/list/leaf/leaf-list.
# These concrete statement classes all inherit from YangStatement, so bind
# the type variable to YangStatement (not YangStatementList) to satisfy
# type checkers when passing instances to _add_to_parent_or_module.
_StatementT = TypeVar("_StatementT", bound="YangStatement")


class StatementParsers:
    """Collection of statement parsing methods."""
    
    def __init__(self, registry):
        self.registry = registry

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
        prefix = tokens.consume_type(YangTokenType.STRING)
        context.module.prefix = prefix
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
        date = tokens.consume().strip('"\'')
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
        type_name = tokens.consume()  # identifier (typedef) or type keyword (leafref, string, etc.)
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
        """Parse when statement. Argument is string (with optional + concatenation). Uses xpath."""
        tokens.consume_type(YangTokenType.WHEN)
        condition = self._parse_string_concatenation(tokens)
        when_stmt = YangWhenStmt(condition=condition)
        if context.current_parent and isinstance(context.current_parent, YangStatementWithWhen):
            context.current_parent.when = when_stmt
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
        grouping_name = tokens.consume_type(YangTokenType.IDENTIFIER)
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
                        SimpleNamespace(statements=body), stmt.refines, module
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