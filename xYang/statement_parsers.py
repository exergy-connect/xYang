"""
Statement parsers for YANG statements.
"""

from typing import Optional, TYPE_CHECKING
from .parser_context import TokenStream, ParserContext
from .ast import (
    YangContainerStmt, YangListStmt, YangLeafStmt,
    YangLeafListStmt, YangTypeStmt, YangMustStmt, YangWhenStmt, YangTypedefStmt
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
                    tokens.consume()  # Skip unknown
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
                    tokens.consume()  # Skip unknown
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
                    tokens.consume()  # Skip unknown
            
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
                    tokens.consume()  # Skip unknown
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
                    tokens.consume()  # Skip unknown
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
                    tokens.consume()  # Skip unknown
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
                        handler(tokens, type_context, type_stmt)
                    else:
                        tokens.consume()
                else:
                    tokens.consume()
        
        # Assign to parent
        if context.current_parent:
            if hasattr(context.current_parent, 'type') and not context.current_parent.type:
                context.current_parent.type = type_stmt
            elif hasattr(context.current_parent, 'types'):
                if not context.current_parent.types:
                    context.current_parent.types = []
                context.current_parent.types.append(type_stmt)
            elif hasattr(context.current_parent, 'type') and context.current_parent.type:
                # For union types, add to types list
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
        while tokens.has_more() and tokens.peek() not in (';', '{'):
            token = tokens.consume()
            expr_parts.append(token)
            # Safety check: if we've consumed a lot of tokens without finding ';' or '{',
            # something might be wrong, but continue anyway
        
        expression = ' '.join(expr_parts) if expr_parts else ''
        
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
        if context.current_parent:
            if isinstance(context.current_parent, YangLeafStmt):
                context.current_parent.must_statements.append(must_stmt)
            elif isinstance(context.current_parent, (YangListStmt, YangContainerStmt)):
                if not hasattr(context.current_parent, 'must_statements'):
                    context.current_parent.must_statements = []
                context.current_parent.must_statements.append(must_stmt)
            elif isinstance(context.current_parent, YangLeafListStmt):
                if not hasattr(context.current_parent, 'must_statements'):
                    context.current_parent.must_statements = []
                context.current_parent.must_statements.append(must_stmt)
        
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