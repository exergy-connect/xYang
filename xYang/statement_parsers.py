"""
Statement parsers for YANG statements.
"""

from typing import Optional, TYPE_CHECKING
from .parser_context import TokenStream, ParserContext
from .ast import (
    YangContainerStmt, YangListStmt, YangLeafStmt,
    YangLeafListStmt, YangTypeStmt, YangMustStmt, YangWhenStmt, YangTypedefStmt,
    YangGroupingStmt, YangUsesStmt, YangRefineStmt, YangChoiceStmt, YangCaseStmt
)
from .xpath.validator import XPathValidator

if TYPE_CHECKING:
    from .statement_registry import StatementRegistry


class StatementParsers:
    """Collection of statement parsing methods."""
    
    def __init__(self, registry):
        self.registry = registry
        self.xpath_validator = XPathValidator()
    
    def parse_module(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse module statement."""
        tokens.consume('module')
        module_name = tokens.consume()
        tokens.consume('{')
        
        context.module.name = module_name
        
        # Parse module body
        # Nested parsers (container, list, etc.) handle their own braces
        # So we just need to stop when we see the module's closing brace
        while tokens.has_more() and tokens.peek() != '}':
            self._parse_module_statement(tokens, context)
        
        # Consume the module's closing brace
        tokens.consume('}')
    
    def _parse_module_statement(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse a statement in module body."""
        stmt_type = tokens.peek()
        handler = self.registry.get_handler(f"module:{stmt_type}")
        if handler:
            handler(tokens, context)
        else:
            # Unknown statement - raise error instead of silently skipping
            raise tokens._make_error(f"Unknown statement in module: {stmt_type}")
    
    def parse_yang_version(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse yang-version statement."""
        tokens.consume('yang-version')
        version = tokens.consume()
        context.module.yang_version = version
        tokens.consume_if(';')
    
    def parse_namespace(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse namespace statement."""
        tokens.consume('namespace')
        namespace = tokens.consume().strip('"\'')
        context.module.namespace = namespace
        tokens.consume_if(';')
    
    def parse_prefix(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse prefix statement."""
        tokens.consume('prefix')
        prefix = tokens.consume().strip('"\'')
        context.module.prefix = prefix
        tokens.consume_if(';')
    
    def parse_organization(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse organization statement."""
        tokens.consume('organization')
        org = tokens.consume().strip('"\'')
        context.module.organization = org
        tokens.consume_if(';')
    
    def parse_contact(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse contact statement."""
        tokens.consume('contact')
        contact = tokens.consume().strip('"\'')
        context.module.contact = contact
        tokens.consume_if(';')
    
    def parse_description(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse description statement."""
        tokens.consume('description')
        desc = tokens.consume().strip('"\'')
        
        if context.current_parent:
            context.current_parent.description = desc
        else:
            context.module.description = desc
        
        tokens.consume_if(';')
    
    def parse_revision(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse revision statement."""
        tokens.consume('revision')
        date = tokens.consume().strip('"\'')
        revision = {'date': date, 'description': ''}
        
        if tokens.consume_if('{'):
            while tokens.has_more() and tokens.peek() != '}':
                if tokens.peek() == 'description':
                    tokens.consume('description')
                    revision['description'] = tokens.consume().strip('"\'')
                    tokens.consume_if(';')
                else:
                    raise tokens._make_error(f"Unknown statement in revision: {tokens.peek()}")
            tokens.consume('}')
        
        context.module.revisions.append(revision)
        tokens.consume_if(';')
    
    def parse_typedef(self, tokens: TokenStream, context: ParserContext) -> Optional[YangTypedefStmt]:
        """Parse typedef statement."""
        tokens.consume('typedef')
        typedef_name = tokens.consume()
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
        tokens.consume('container')
        container_name = tokens.consume()
        container_stmt = YangContainerStmt(name=container_name)
        
        if tokens.consume_if('{'):
            new_context = context.push_parent(container_stmt)
            prev_index = -1
            while tokens.has_more() and tokens.peek() != '}':
                # Safety check to prevent infinite loops
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
            
            # Consume the container's closing brace
            if tokens.has_more() and tokens.peek() == '}':
                tokens.consume('}')
        
        # Add to parent if provided, otherwise to module
        if context.current_parent:
            if not hasattr(context.current_parent, 'statements'):
                context.current_parent.statements = []
            context.current_parent.statements.append(container_stmt)
        else:
            if not hasattr(context.module, 'statements'):
                context.module.statements = []
            context.module.statements.append(container_stmt)
        
        tokens.consume_if(';')
        return container_stmt
    
    def parse_list(self, tokens: TokenStream, context: ParserContext) -> YangListStmt:
        """Parse list statement."""
        tokens.consume('list')
        list_name = tokens.consume()
        list_stmt = YangListStmt(name=list_name)
        
        if tokens.consume_if('{'):
            new_context = context.push_parent(list_stmt)
            while tokens.has_more() and tokens.peek() != '}':
                handler = self.registry.get_handler(f"list:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                else:
                    raise tokens._make_error(f"Unknown statement in list '{list_name}': {tokens.peek()}")
            tokens.consume('}')
        
        # Add to parent if provided, otherwise to module
        if context.current_parent:
            if not hasattr(context.current_parent, 'statements'):
                context.current_parent.statements = []
            context.current_parent.statements.append(list_stmt)
        else:
            if not hasattr(context.module, 'statements'):
                context.module.statements = []
            context.module.statements.append(list_stmt)
        
        tokens.consume_if(';')
        return list_stmt
    
    def parse_leaf(self, tokens: TokenStream, context: ParserContext) -> YangLeafStmt:
        """Parse leaf statement."""
        tokens.consume('leaf')
        leaf_name = tokens.consume()
        leaf_stmt = YangLeafStmt(name=leaf_name)
        
        if tokens.consume_if('{'):
            new_context = context.push_parent(leaf_stmt)
            while tokens.has_more() and tokens.peek() != '}':
                handler = self.registry.get_handler(f"leaf:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                else:
                    raise tokens._make_error(f"Unknown statement in leaf '{leaf_name}': {tokens.peek()}")
            tokens.consume('}')
        
        # Add to parent if provided, otherwise to module
        if context.current_parent:
            if not hasattr(context.current_parent, 'statements'):
                context.current_parent.statements = []
            context.current_parent.statements.append(leaf_stmt)
        else:
            if not hasattr(context.module, 'statements'):
                context.module.statements = []
            context.module.statements.append(leaf_stmt)
        
        tokens.consume_if(';')
        return leaf_stmt
    
    def parse_leaf_list(self, tokens: TokenStream, context: ParserContext) -> YangLeafListStmt:
        """Parse leaf-list statement."""
        tokens.consume('leaf-list')
        leaf_list_name = tokens.consume()
        leaf_list_stmt = YangLeafListStmt(name=leaf_list_name)
        
        if tokens.consume_if('{'):
            new_context = context.push_parent(leaf_list_stmt)
            while tokens.has_more() and tokens.peek() != '}':
                handler = self.registry.get_handler(f"leaf-list:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                else:
                    raise tokens._make_error(f"Unknown statement in leaf-list '{leaf_list_name}': {tokens.peek()}")
            tokens.consume('}')
        
        # Add to parent if provided, otherwise to module
        if context.current_parent:
            if not hasattr(context.current_parent, 'statements'):
                context.current_parent.statements = []
            context.current_parent.statements.append(leaf_list_stmt)
        else:
            if not hasattr(context.module, 'statements'):
                context.module.statements = []
            context.module.statements.append(leaf_list_stmt)
        
        tokens.consume_if(';')
        return leaf_list_stmt
    
    def parse_type(self, tokens: TokenStream, context: ParserContext) -> YangTypeStmt:
        """Parse type statement."""
        tokens.consume('type')
        type_name = tokens.consume()
        type_stmt = YangTypeStmt(name=type_name)
        
        if tokens.consume_if('{'):
            brace_depth = 1
            type_context = context.push_parent(type_stmt)
            while tokens.has_more() and brace_depth > 0:
                if tokens.peek() == '{':
                    brace_depth += 1
                    tokens.consume()
                elif tokens.peek() == '}':
                    brace_depth -= 1
                    if brace_depth == 0:
                        tokens.consume()
                        break
                    tokens.consume()
                elif brace_depth == 1:
                    handler = self.registry.get_handler(f"type:{tokens.peek()}")
                    if handler:
                        # Type constraint handlers take type_stmt as third parameter
                        # But parse_type (for union nested types) only takes (tokens, context)
                        if tokens.peek() == 'type':
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
        
        tokens.consume_if(';')
        return type_stmt
    
    def parse_type_pattern(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse pattern constraint."""
        tokens.consume('pattern')
        pattern = tokens.consume().strip('"\'')
        type_stmt.pattern = pattern
        tokens.consume_if(';')
    
    def parse_type_length(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse length constraint."""
        tokens.consume('length')
        length = tokens.consume().strip('"\'')
        type_stmt.length = length
        tokens.consume_if(';')
    
    def parse_type_range(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse range constraint."""
        tokens.consume('range')
        range_val = tokens.consume().strip('"\'')
        type_stmt.range = range_val
        tokens.consume_if(';')
    
    def parse_type_fraction_digits(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse fraction-digits constraint."""
        tokens.consume('fraction-digits')
        type_stmt.fraction_digits = int(tokens.consume())
        tokens.consume_if(';')
    
    def parse_type_enum(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse enum constraint."""
        tokens.consume('enum')
        enum_name = tokens.consume()
        type_stmt.enums.append(enum_name)
        tokens.consume_if(';')
    
    def parse_type_path(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse path constraint (for leafref)."""
        tokens.consume('path')
        path = tokens.consume().strip('"\'')
        type_stmt.path = path
        tokens.consume_if(';')
    
    def parse_type_require_instance(self, tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt) -> None:
        """Parse require-instance constraint (for leafref)."""
        tokens.consume('require-instance')
        require_instance = tokens.consume().strip('"\'')
        type_stmt.require_instance = require_instance == 'true'
        tokens.consume_if(';')
    
    def parse_list_key(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse key in list statement."""
        tokens.consume('key')
        if context.current_parent and isinstance(context.current_parent, YangListStmt):
            context.current_parent.key = tokens.consume().strip('"\'')
        tokens.consume_if(';')
    
    def parse_list_min_elements(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse min-elements in list statement."""
        tokens.consume('min-elements')
        if context.current_parent and isinstance(context.current_parent, YangListStmt):
            context.current_parent.min_elements = int(tokens.consume())
        tokens.consume_if(';')
    
    def parse_list_max_elements(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse max-elements in list statement."""
        tokens.consume('max-elements')
        if context.current_parent and isinstance(context.current_parent, YangListStmt):
            context.current_parent.max_elements = int(tokens.consume())
        tokens.consume_if(';')
    
    def parse_list_must(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse must in list statement."""
        must_stmt = self.parse_must(tokens, context)
        if context.current_parent and isinstance(context.current_parent, YangListStmt):
            if not hasattr(context.current_parent, 'must_statements'):
                context.current_parent.must_statements = []
            context.current_parent.must_statements.append(must_stmt)
    
    def parse_leaf_mandatory(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse mandatory in leaf statement."""
        tokens.consume('mandatory')
        if context.current_parent and isinstance(context.current_parent, YangLeafStmt):
            mandatory_val = tokens.consume()
            context.current_parent.mandatory = mandatory_val == 'true'
        tokens.consume_if(';')
    
    def parse_leaf_default(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse default in leaf statement."""
        tokens.consume('default')
        if context.current_parent and isinstance(context.current_parent, YangLeafStmt):
            context.current_parent.default = tokens.consume().strip('"\'')
        tokens.consume_if(';')
    
    def parse_leaf_must(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse must in leaf statement."""
        must_stmt = self.parse_must(tokens, context)
        if context.current_parent and isinstance(context.current_parent, YangLeafStmt):
            context.current_parent.must_statements.append(must_stmt)
    
    def parse_leaf_list_min_elements(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse min-elements in leaf-list statement."""
        tokens.consume('min-elements')
        if context.current_parent and isinstance(context.current_parent, YangLeafListStmt):
            context.current_parent.min_elements = int(tokens.consume())
        tokens.consume_if(';')
    
    def parse_leaf_list_max_elements(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse max-elements in leaf-list statement."""
        tokens.consume('max-elements')
        if context.current_parent and isinstance(context.current_parent, YangLeafListStmt):
            context.current_parent.max_elements = int(tokens.consume())
        tokens.consume_if(';')
    
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
        tokens.consume('presence')
        if context.current_parent and isinstance(context.current_parent, YangContainerStmt):
            context.current_parent.presence = tokens.consume().strip('"\'')
        tokens.consume_if(';')
    
    def parse_must(self, tokens: TokenStream, context: ParserContext) -> YangMustStmt:
        """Parse must statement."""
        tokens.consume('must')
        expr_parts = []
        
        # The tokenizer removes quotes from tokens, so we won't see quotes here.
        # The expression should be tokenized as one or more tokens.
        # Consume tokens until we hit ';' or '{' (which indicates the start of the must body)
        # Note: The expression itself should not contain ';' or '{', so this is safe
        # Handle string concatenation with + operator - preserve + as separate token
        while tokens.has_more() and tokens.peek() not in (';', '{'):
            token = tokens.consume()
            expr_parts.append(token)
            # Safety check: if we've consumed a lot of tokens without finding ';' or '{',
            # something might be wrong, but continue anyway
        
        # Join tokens, handling + operator for string concatenation
        # In YANG, string concatenation with + happens at parse time
        # We need to concatenate the strings directly, not pass + to XPath
        expression_parts = []
        i = 0
        while i < len(expr_parts):
            part = expr_parts[i]
            if part == '+':
                # String concatenation: skip the + and concatenate previous and next strings
                if i + 1 < len(expr_parts):
                    # Concatenate the last part with the next part
                    if expression_parts:
                        # Get last part (may be a string with trailing space)
                        last_part = expression_parts[-1]
                        next_part = expr_parts[i + 1]
                        # Concatenate directly (preserving any spaces in the strings)
                        expression_parts[-1] = last_part + next_part
                    else:
                        # + at the start - just skip it and take next part
                        expression_parts.append(expr_parts[i + 1])
                    i += 2  # Skip both + and next token
                    continue
            else:
                # Normal token - add space before if not first and previous wasn't +
                if expression_parts and expression_parts[-1] != '+':
                    expression_parts.append(' ')
                expression_parts.append(part)
            i += 1
        expression = ''.join(expression_parts).strip()
        
        # Validate XPath expression at parse time and get parsed AST
        ast = self.xpath_validator.validate(expression)
        
        must_stmt = YangMustStmt(expression=expression, ast=ast)
        
        if tokens.consume_if('{'):
            new_context = context.push_parent(must_stmt)
            while tokens.has_more() and tokens.peek() != '}':
                handler = self.registry.get_handler(f"must:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                else:
                    tokens.consume()
            tokens.consume('}')
        
        # Add to appropriate parent
        # Note: For list statements, parse_list_must handles adding to must_statements
        # So we only add here if not called from parse_list_must
        if context.current_parent:
            if isinstance(context.current_parent, YangLeafStmt):
                context.current_parent.must_statements.append(must_stmt)
            elif isinstance(context.current_parent, YangContainerStmt):
                if not hasattr(context.current_parent, 'must_statements'):
                    context.current_parent.must_statements = []
                context.current_parent.must_statements.append(must_stmt)
            elif isinstance(context.current_parent, YangLeafListStmt):
                if not hasattr(context.current_parent, 'must_statements'):
                    context.current_parent.must_statements = []
                context.current_parent.must_statements.append(must_stmt)
            elif isinstance(context.current_parent, YangRefineStmt):
                # Must statements in refine are stored in statements list
                context.current_parent.statements.append(must_stmt)
            # For YangListStmt, parse_list_must handles adding to must_statements
            # Don't add here to avoid duplication
        
        # Consume semicolon if present (optional for must statements in containers/lists)
        tokens.consume_if(';')
        return must_stmt
    
    def parse_must_error_message(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse error-message in must statement."""
        tokens.consume('error-message')
        if context.current_parent and isinstance(context.current_parent, YangMustStmt):
            context.current_parent.error_message = tokens.consume().strip('"\'')
        tokens.consume_if(';')
    
    def parse_when(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse when statement."""
        tokens.consume('when')
        expr_parts = []
        
        if tokens.peek() in ('"', "'"):
            quote = tokens.consume()
            while tokens.has_more() and tokens.peek() != quote:
                expr_parts.append(tokens.consume())
            tokens.consume(quote)
        else:
            while tokens.has_more() and tokens.peek() not in (';', '{'):
                expr_parts.append(tokens.consume())
        
        condition = ' '.join(expr_parts)
        
        # Validate XPath expression at parse time and get parsed AST
        ast = self.xpath_validator.validate(condition)
        
        when_stmt = YangWhenStmt(condition=condition, ast=ast)
        
        # Store in parent statement
        if context.current_parent:
            if hasattr(context.current_parent, 'when'):
                context.current_parent.when = when_stmt
        
        tokens.consume_if(';')
    
    def parse_grouping(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse grouping statement."""
        tokens.consume('grouping')
        grouping_name = tokens.consume()
        grouping_stmt = YangGroupingStmt(name=grouping_name)
        
        if tokens.consume_if('{'):
            new_context = context.push_parent(grouping_stmt)
            while tokens.has_more() and tokens.peek() != '}':
                # Parse any statement that can appear in a grouping
                handler = self.registry.get_handler(f"grouping:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                else:
                    # Try generic handlers for common statements
                    if tokens.peek() == 'container':
                        self.parse_container(tokens, new_context)
                    elif tokens.peek() == 'list':
                        self.parse_list(tokens, new_context)
                    elif tokens.peek() == 'leaf':
                        self.parse_leaf(tokens, new_context)
                    elif tokens.peek() == 'leaf-list':
                        self.parse_leaf_list(tokens, new_context)
                    elif tokens.peek() == 'uses':
                        self.parse_uses(tokens, new_context)
                    elif tokens.peek() == 'description':
                        self.parse_description(tokens, new_context)
                    else:
                        raise tokens._make_error(f"Unknown statement in grouping '{grouping_name}': {tokens.peek()}")
            tokens.consume('}')
        
        # Store grouping in module
        context.module.groupings[grouping_name] = grouping_stmt
        tokens.consume_if(';')
    
    def parse_uses(self, tokens: TokenStream, context: ParserContext) -> Optional[YangUsesStmt]:
        """Parse uses statement.
        
        Uses statements are stored temporarily and expanded after all groupings
        have been parsed. A YangUsesStmt node is created as a placeholder.
        """
        tokens.consume('uses')
        grouping_name = tokens.consume()
        uses_stmt = YangUsesStmt(name="uses", grouping_name=grouping_name)
        
        if tokens.consume_if('{'):
            new_context = context.push_parent(uses_stmt)
            while tokens.has_more() and tokens.peek() != '}':
                if tokens.peek() == 'refine':
                    self.parse_refine(tokens, new_context)
                elif tokens.peek() == 'description':
                    self.parse_description(tokens, new_context)
                else:
                    raise tokens._make_error(f"Unknown statement in uses '{grouping_name}': {tokens.peek()}")
            tokens.consume('}')
        
        # Store the uses statement temporarily - it will be expanded later
        if context.current_parent:
            context.current_parent.statements.append(uses_stmt)
        
        tokens.consume_if(';')
        return uses_stmt
    
    def parse_refine(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse refine statement."""
        tokens.consume('refine')
        target_path = tokens.consume()
        refine_stmt = YangRefineStmt(name="refine", target_path=target_path)
        
        if tokens.consume_if('{'):
            new_context = context.push_parent(refine_stmt)
            while tokens.has_more() and tokens.peek() != '}':
                # Refine can contain must, description, default, etc.
                handler = self.registry.get_handler(f"refine:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                elif tokens.peek() == 'must':
                    self.parse_must(tokens, new_context)
                elif tokens.peek() == 'description':
                    self.parse_description(tokens, new_context)
                elif tokens.peek() == 'type':
                    self.parse_type(tokens, new_context)
                elif tokens.peek() == 'default':
                    if hasattr(context.current_parent, 'parent') and context.current_parent.parent:
                        # Try to find the target node and add default
                        pass
                    tokens.consume()  # Skip for now
                else:
                    raise tokens._make_error(f"Unknown statement in refine '{target_path}': {tokens.peek()}")
            tokens.consume('}')
        
        # Add refine to uses statement
        if context.current_parent and isinstance(context.current_parent, YangUsesStmt):
            context.current_parent.refines.append(refine_stmt)
        
        tokens.consume_if(';')
    
    def parse_choice(self, tokens: TokenStream, context: ParserContext) -> YangChoiceStmt:
        """Parse choice statement."""
        tokens.consume('choice')
        choice_name = tokens.consume()
        choice_stmt = YangChoiceStmt(name=choice_name)
        
        if tokens.consume_if('{'):
            new_context = context.push_parent(choice_stmt)
            while tokens.has_more() and tokens.peek() != '}':
                handler = self.registry.get_handler(f"choice:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                else:
                    raise tokens._make_error(f"Unknown statement in choice '{choice_name}': {tokens.peek()}")
            tokens.consume('}')
        
        # Add to parent if provided, otherwise to module
        if context.current_parent:
            if not hasattr(context.current_parent, 'statements'):
                context.current_parent.statements = []
            context.current_parent.statements.append(choice_stmt)
        else:
            if not hasattr(context.module, 'statements'):
                context.module.statements = []
            context.module.statements.append(choice_stmt)
        
        tokens.consume_if(';')
        return choice_stmt
    
    def parse_case(self, tokens: TokenStream, context: ParserContext) -> YangCaseStmt:
        """Parse case statement."""
        tokens.consume('case')
        case_name = tokens.consume()
        case_stmt = YangCaseStmt(name=case_name)
        
        if tokens.consume_if('{'):
            new_context = context.push_parent(case_stmt)
            while tokens.has_more() and tokens.peek() != '}':
                # Case can contain leaf, container, list, leaf-list, choice, etc.
                handler = self.registry.get_handler(f"case:{tokens.peek()}")
                if handler:
                    handler(tokens, new_context)
                elif tokens.peek() == 'leaf':
                    self.parse_leaf(tokens, new_context)
                elif tokens.peek() == 'container':
                    self.parse_container(tokens, new_context)
                elif tokens.peek() == 'list':
                    self.parse_list(tokens, new_context)
                elif tokens.peek() == 'leaf-list':
                    self.parse_leaf_list(tokens, new_context)
                elif tokens.peek() == 'choice':
                    self.parse_choice(tokens, new_context)
                elif tokens.peek() == 'description':
                    self.parse_description(tokens, new_context)
                else:
                    raise tokens._make_error(f"Unknown statement in case '{case_name}': {tokens.peek()}")
            tokens.consume('}')
        
        # Add case to parent choice
        if context.current_parent and isinstance(context.current_parent, YangChoiceStmt):
            context.current_parent.cases.append(case_stmt)
        elif context.current_parent:
            if not hasattr(context.current_parent, 'statements'):
                context.current_parent.statements = []
            context.current_parent.statements.append(case_stmt)
        else:
            if not hasattr(context.module, 'statements'):
                context.module.statements = []
            context.module.statements.append(case_stmt)
        
        tokens.consume_if(';')
        return case_stmt
    
    def parse_choice_mandatory(self, tokens: TokenStream, context: ParserContext) -> None:
        """Parse mandatory statement in choice."""
        tokens.consume('mandatory')
        mandatory_val = tokens.consume()
        if context.current_parent and isinstance(context.current_parent, YangChoiceStmt):
            context.current_parent.mandatory = (mandatory_val.lower() == 'true')
        tokens.consume_if(';')
    
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
        from .ast import YangMustStmt, YangLeafStmt, YangContainerStmt, YangListStmt
        
        # Apply refined type when target is a leaf
        if getattr(refine, 'type', None) is not None and isinstance(stmt, YangLeafStmt):
            stmt.type = refine.type
        
        # Apply must statements from refine
        for refine_stmt in refine.statements:
            if isinstance(refine_stmt, YangMustStmt):
                # Initialize must_statements if it doesn't exist
                if not hasattr(stmt, 'must_statements'):
                    stmt.must_statements = []
                if stmt.must_statements is None:
                    stmt.must_statements = []
                # Add the must statement from refine
                stmt.must_statements.append(refine_stmt)
            # Apply other refine modifications (default, description, etc.)
            # This is a simplified implementation