"""
Statement parsers for YANG statements.
"""

from typing import Optional, TYPE_CHECKING
from .parser_context import TokenStream, ParserContext, YangTokenType
from .ast import (
    YangContainerStmt, YangListStmt, YangLeafStmt,
    YangLeafListStmt, YangTypeStmt, YangMustStmt, YangWhenStmt, YangTypedefStmt,
    YangGroupingStmt, YangUsesStmt, YangRefineStmt, YangChoiceStmt, YangCaseStmt,
    YangStatementWithMust,
)
from .xpath.validator import XPathValidator

if TYPE_CHECKING:
    from .statement_registry import StatementRegistry
    from .ast import YangStatement
    from .module import YangModule


class StatementParsers:
    """Collection of statement parsing methods."""
    
    def __init__(self, registry):
        self.registry = registry
        self.xpath_validator = XPathValidator()

    def _add_to_parent_or_module(self, context: ParserContext, stmt: 'YangStatement') -> None:
        """Add statement to current_parent.statements (module or nested statement)."""
        context.current_parent.statements.append(stmt)

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
        version = tokens.consume_type(YangTokenType.IDENTIFIER)
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
        if hasattr(context.current_parent, 'description'):
            context.current_parent.description = desc
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

    def parse_list(self, tokens: TokenStream, context: ParserContext) -> YangListStmt:
        """Parse list statement."""
        tokens.consume_type(YangTokenType.LIST)
        list_name = tokens.consume()  # identifier or keyword
        list_stmt = YangListStmt(name=list_name)
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(list_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                handler = self.registry.get_handler(f"list:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                else:
                    raise tokens._make_error(f"Unknown statement in list '{list_name}': {tokens.peek()}")
            tokens.consume_type(YangTokenType.RBRACE)
        self._add_to_parent_or_module(context, list_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return list_stmt

    def parse_leaf(self, tokens: TokenStream, context: ParserContext) -> YangLeafStmt:
        """Parse leaf statement."""
        tokens.consume_type(YangTokenType.LEAF)
        leaf_name = tokens.consume()  # identifier or keyword (e.g. type)
        leaf_stmt = YangLeafStmt(name=leaf_name)
        
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(leaf_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                handler = self.registry.get_handler(f"leaf:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                else:
                    raise tokens._make_error(f"Unknown statement in leaf '{leaf_name}': {tokens.peek()}")
            tokens.consume_type(YangTokenType.RBRACE)
        self._add_to_parent_or_module(context, leaf_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return leaf_stmt

    def parse_leaf_list(self, tokens: TokenStream, context: ParserContext) -> YangLeafListStmt:
        """Parse leaf-list statement."""
        tokens.consume_type(YangTokenType.LEAF_LIST)
        leaf_list_name = tokens.consume()  # identifier or keyword
        leaf_list_stmt = YangLeafListStmt(name=leaf_list_name)
        
        if tokens.consume_if_type(YangTokenType.LBRACE):
            new_context = context.push_parent(leaf_list_stmt)
            while tokens.has_more() and tokens.peek_type() != YangTokenType.RBRACE:
                handler = self.registry.get_handler(f"leaf-list:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                else:
                    raise tokens._make_error(f"Unknown statement in leaf-list '{leaf_list_name}': {tokens.peek()}")
            tokens.consume_type(YangTokenType.RBRACE)
        self._add_to_parent_or_module(context, leaf_list_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return leaf_list_stmt

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
        # Assign to parent
        if context.current_parent:
            # Check if parent is a union type statement - add nested types to union.types
            if isinstance(context.current_parent, YangTypeStmt) and context.current_parent.name == 'union':
                if not hasattr(context.current_parent, 'types'):
                    context.current_parent.types = []
                context.current_parent.types.append(type_stmt)
                # Debug: print what we're adding
                # print(f"DEBUG: Adding {type_stmt.name} to union.types (now has {len(context.current_parent.types)} types)")
            elif hasattr(context.current_parent, 'type') and not context.current_parent.type:
                context.current_parent.type = type_stmt
            elif hasattr(context.current_parent, 'types'):
                if not context.current_parent.types:
                    context.current_parent.types = []
                context.current_parent.types.append(type_stmt)
            elif hasattr(context.current_parent, 'type') and context.current_parent.type:
                # For union types nested in other structures, add to types list
                if not hasattr(type_stmt, 'types'):
                    type_stmt.types = []
                if not hasattr(context.current_parent.type, 'types'):
                    context.current_parent.type.types = []
                context.current_parent.type.types.append(type_stmt)
        
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
        """Parse path constraint (for leafref)."""
        tokens.consume_type(YangTokenType.PATH)
        path = tokens.consume_type(YangTokenType.STRING)
        type_stmt.path = path
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

    def parse_list_min_elements(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse min-elements in list statement."""
        tokens.consume_type(YangTokenType.MIN_ELEMENTS)
        if context.current_parent and isinstance(context.current_parent, YangListStmt):
            context.current_parent.min_elements = int(tokens.consume_type(YangTokenType.INTEGER))
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_list_max_elements(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse max-elements in list statement."""
        tokens.consume_type(YangTokenType.MAX_ELEMENTS)
        if context.current_parent and isinstance(context.current_parent, YangListStmt):
            context.current_parent.max_elements = int(tokens.consume_type(YangTokenType.INTEGER))
        tokens.consume_if_type(YangTokenType.SEMICOLON)
    
    def parse_list_must(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse must in list statement."""
        must_stmt = self.parse_must(tokens, context)
        if context.current_parent and isinstance(context.current_parent, YangListStmt):
            if not hasattr(context.current_parent, 'must_statements'):
                context.current_parent.must_statements = []
            context.current_parent.must_statements.append(must_stmt)
    
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
    
    def parse_leaf_must(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse must in leaf statement."""
        must_stmt = self.parse_must(tokens, context)
        if context.current_parent and isinstance(context.current_parent, YangLeafStmt):
            context.current_parent.must_statements.append(must_stmt)
    
    def parse_leaf_list_min_elements(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse min-elements in leaf-list statement."""
        tokens.consume_type(YangTokenType.MIN_ELEMENTS)
        if context.current_parent and isinstance(context.current_parent, YangLeafListStmt):
            context.current_parent.min_elements = int(tokens.consume_type(YangTokenType.INTEGER))
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_leaf_list_max_elements(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse max-elements in leaf-list statement."""
        tokens.consume_type(YangTokenType.MAX_ELEMENTS)
        if context.current_parent and isinstance(context.current_parent, YangLeafListStmt):
            context.current_parent.max_elements = int(tokens.consume_type(YangTokenType.INTEGER))
        tokens.consume_if_type(YangTokenType.SEMICOLON)
    
    def parse_leaf_list_type(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse type in leaf-list statement."""
        # parse_type will assign to current_parent automatically
        self.parse_type(tokens, context)
    
    def parse_leaf_list_must(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse must in leaf-list statement."""
        must_stmt = self.parse_must(tokens, context)
        if context.current_parent and isinstance(context.current_parent, YangLeafListStmt):
            if not hasattr(context.current_parent, 'must_statements'):
                context.current_parent.must_statements = []
            context.current_parent.must_statements.append(must_stmt)
    
    def parse_presence(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse presence statement for container."""
        tokens.consume_type(YangTokenType.PRESENCE)
        if context.current_parent and isinstance(context.current_parent, YangContainerStmt):
            context.current_parent.presence = tokens.consume_type(YangTokenType.STRING)
        tokens.consume_if_type(YangTokenType.SEMICOLON)

    def parse_must(self, tokens: TokenStream, context: ParserContext) -> YangMustStmt:
        """Parse must statement. Argument is one or more string tokens (YANG allows + concatenation)."""
        tokens.consume_type(YangTokenType.MUST)
        parts = [tokens.consume_type(YangTokenType.STRING)]
        while tokens.peek_type() == YangTokenType.PLUS:
            tokens.consume_type(YangTokenType.PLUS)
            parts.append(tokens.consume_type(YangTokenType.STRING))
        expression = ''.join(parts)

        ast = self.xpath_validator.validate(expression)
        
        must_stmt = YangMustStmt(expression=expression, ast=ast)
        
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
        """Parse when statement."""
        tokens.consume_type(YangTokenType.WHEN)
        expr_parts = []
        # When expression is typically one STRING token or multiple tokens until ; or {
        while tokens.has_more() and tokens.peek_type() not in (YangTokenType.SEMICOLON, YangTokenType.LBRACE):
            expr_parts.append(tokens.consume())
        condition = ' '.join(expr_parts)
        ast = self.xpath_validator.validate(condition)
        when_stmt = YangWhenStmt(condition=condition, ast=ast)
        if context.current_parent:
            if hasattr(context.current_parent, 'when'):
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
                if tokens.peek_type() == YangTokenType.REFINE:
                    self.parse_refine(tokens, new_context)
                elif tokens.peek_type() == YangTokenType.DESCRIPTION:
                    self.parse_description(tokens, new_context)
                else:
                    raise tokens._make_error(f"Unknown statement in uses '{grouping_name}': {tokens.peek()}")
            tokens.consume_type(YangTokenType.RBRACE)
        if context.current_parent:
            context.current_parent.statements.append(uses_stmt)
        tokens.consume_if_type(YangTokenType.SEMICOLON)
        return uses_stmt
    
    def parse_refine(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse refine statement."""
        tokens.consume_type(YangTokenType.REFINE)
        target_path = tokens.consume()  # identifier or keyword (e.g. type)
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
    
    def _expand_uses(self, grouping: 'YangStatement', refines: list, module: 'YangModule' = None) -> list:
        """Expand a uses statement by copying statements from grouping and applying refines.
        
        Recursively expands nested uses statements within the grouping.
        """
        from .ast import YangUsesStmt
        
        expanded = []
        for stmt in grouping.statements:
            # If this statement is itself a uses statement, recursively expand it
            if isinstance(stmt, YangUsesStmt):
                nested_grouping = module.get_grouping(stmt.grouping_name) if module else None
                if nested_grouping:
                    # Recursively expand the nested uses statement
                    nested_expanded = self._expand_uses(nested_grouping, stmt.refines, module)
                    expanded.extend(nested_expanded)
                else:
                    # Grouping not found - skip or log warning
                    pass
            else:
                # Create a shallow copy of the statement
                stmt_copy = self._copy_statement(stmt)
                
                # Apply refines if any match this statement
                for refine in refines:
                    if refine.target_path == stmt.name:
                        # Apply refine modifications
                        self._apply_refine(stmt_copy, refine)
                
                expanded.append(stmt_copy)
        
        return expanded
    
    def _expand_uses_with_statements(self, statements, refines: list, module: 'YangModule' = None) -> list:
        """Expand uses statements from a list of already-expanded statements.
        
        This is used when expanding uses statements that reference groupings
        whose uses statements have already been expanded.
        """
        expanded = []
        for stmt in statements:
            # Create a shallow copy of the statement
            stmt_copy = self._copy_statement(stmt)
            
            # Apply refines if any match this statement
            for refine in refines:
                if refine.target_path == stmt.name:
                    # Apply refine modifications
                    self._apply_refine(stmt_copy, refine)
            
            expanded.append(stmt_copy)
        
        return expanded
    
    def _copy_statement(self, stmt: 'YangStatement') -> 'YangStatement':
        """Create a copy of a statement, handling AST nodes properly."""
        from .ast import (
            YangContainerStmt, YangListStmt, YangLeafStmt, YangLeafListStmt,
            YangTypeStmt, YangMustStmt, YangWhenStmt, YangChoiceStmt, YangCaseStmt
        )
        
        # Copy child statements recursively
        copied_statements = [self._copy_statement(s) for s in stmt.statements]
        
        if isinstance(stmt, YangContainerStmt):
            return YangContainerStmt(
                name=stmt.name,
                description=stmt.description,
                statements=copied_statements,
                presence=stmt.presence,
                when=stmt.when,  # When statements contain AST, but we'll keep the reference
                must_statements=stmt.must_statements[:] if stmt.must_statements else []
            )
        elif isinstance(stmt, YangListStmt):
            return YangListStmt(
                name=stmt.name,
                description=stmt.description,
                statements=copied_statements,
                key=stmt.key,
                min_elements=stmt.min_elements,
                max_elements=stmt.max_elements,
                must_statements=stmt.must_statements[:] if stmt.must_statements else [],
                when=stmt.when
            )
        elif isinstance(stmt, YangLeafStmt):
            # Copy must_statements list
            must_statements = list(stmt.must_statements) if stmt.must_statements else []
            return YangLeafStmt(
                name=stmt.name,
                description=stmt.description,
                statements=copied_statements,
                type=stmt.type,  # TypeStmt doesn't need deep copy
                mandatory=stmt.mandatory,
                default=stmt.default,
                must_statements=must_statements,
                when=stmt.when
            )
        elif isinstance(stmt, YangLeafListStmt):
            return YangLeafListStmt(
                name=stmt.name,
                description=stmt.description,
                statements=copied_statements,
                type=stmt.type,
                min_elements=stmt.min_elements,
                max_elements=stmt.max_elements,
                must_statements=stmt.must_statements[:] if stmt.must_statements else []
            )
        elif isinstance(stmt, YangChoiceStmt):
            # Copy cases recursively
            copied_cases = [self._copy_statement(c) for c in stmt.cases]
            return YangChoiceStmt(
                name=stmt.name,
                description=stmt.description,
                statements=copied_statements,
                mandatory=stmt.mandatory,
                cases=copied_cases
            )
        elif isinstance(stmt, YangCaseStmt):
            return YangCaseStmt(
                name=stmt.name,
                description=stmt.description,
                statements=copied_statements
            )
        else:
            # Generic statement copy
            new_stmt = type(stmt)(name=stmt.name, description=stmt.description, statements=copied_statements)
            # Copy other attributes if they exist
            for attr in ['type', 'mandatory', 'default', 'key', 'presence', 'when',
                        'min_elements', 'max_elements', 'must_statements']:
                if hasattr(stmt, attr):
                    setattr(new_stmt, attr, getattr(stmt, attr))
            return new_stmt
    
    def _apply_refine(self, stmt: 'YangStatement', refine: 'YangRefineStmt') -> None:
        """Apply refine modifications to a statement."""
        from .ast import YangLeafStmt, YangContainerStmt, YangListStmt
        
        # Apply refined type when target is a leaf
        if getattr(refine, 'type', None) is not None and isinstance(stmt, YangLeafStmt):
            stmt.type = refine.type
        
        # Apply must statements from refine
        for refine_stmt in refine.must_statements:
            if not hasattr(stmt, 'must_statements'):
                stmt.must_statements = []
            if stmt.must_statements is None:
                stmt.must_statements = []
            stmt.must_statements.append(refine_stmt)