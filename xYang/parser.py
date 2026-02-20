"""
YANG parser implementation (refactored).

Parses YANG module files and builds an in-memory representation.
"""

from pathlib import Path
from typing import Optional

from .module import YangModule
from .tokenizer import YangTokenizer
from .parser_context import ParserContext
from .statement_registry import StatementRegistry
from .statement_parsers import StatementParsers
from .errors import YangSyntaxError


class YangParser:
    """Parser for YANG modules."""
    
    def __init__(self):
        self.tokenizer = YangTokenizer()
        self.registry = StatementRegistry()
        self.parsers = StatementParsers(self.registry)
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all statement handlers."""
        # Module-level statements
        self.registry.register('module', self.parsers.parse_module)
        self.registry.register('module:yang-version', self.parsers.parse_yang_version)
        self.registry.register('module:namespace', self.parsers.parse_namespace)
        self.registry.register('module:prefix', self.parsers.parse_prefix)
        self.registry.register('module:organization', self.parsers.parse_organization)
        self.registry.register('module:contact', self.parsers.parse_contact)
        self.registry.register('module:description', self.parsers.parse_description)
        self.registry.register('module:revision', self.parsers.parse_revision)
        self.registry.register('module:typedef', self.parsers.parse_typedef)
        self.registry.register('module:container', self.parsers.parse_container)
        self.registry.register('module:list', self.parsers.parse_list)
        self.registry.register('module:leaf', self.parsers.parse_leaf)
        self.registry.register('module:leaf-list', self.parsers.parse_leaf_list)
        
        # Container body statements
        self.registry.register('container:description', self.parsers.parse_description)
        self.registry.register('container:presence', self.parsers.parse_presence)
        self.registry.register('container:when', self.parsers.parse_when)
        self.registry.register('container:must', self.parsers.parse_must)
        self.registry.register('container:leaf', self.parsers.parse_leaf)
        self.registry.register('container:container', self.parsers.parse_container)
        self.registry.register('container:list', self.parsers.parse_list)
        self.registry.register('container:leaf-list', self.parsers.parse_leaf_list)
        
        # List body statements
        self.registry.register('list:key', self.parsers.parse_list_key)
        self.registry.register('list:min-elements', self.parsers.parse_list_min_elements)
        self.registry.register('list:max-elements', self.parsers.parse_list_max_elements)
        self.registry.register('list:description', self.parsers.parse_description)
        self.registry.register('list:when', self.parsers.parse_when)
        self.registry.register('list:leaf', self.parsers.parse_leaf)
        self.registry.register('list:container', self.parsers.parse_container)
        self.registry.register('list:list', self.parsers.parse_list)
        self.registry.register('list:leaf-list', self.parsers.parse_leaf_list)
        self.registry.register('list:must', self.parsers.parse_must)
        
        # Leaf body statements
        self.registry.register('leaf:type', self.parsers.parse_type)
        self.registry.register('leaf:mandatory', self.parsers.parse_leaf_mandatory)
        self.registry.register('leaf:default', self.parsers.parse_leaf_default)
        self.registry.register('leaf:description', self.parsers.parse_description)
        self.registry.register('leaf:must', self.parsers.parse_leaf_must)
        self.registry.register('leaf:when', self.parsers.parse_when)
        
        # Leaf-list body statements
        self.registry.register('leaf-list:type', self.parsers.parse_leaf_list_type)
        self.registry.register('leaf-list:min-elements', self.parsers.parse_leaf_list_min_elements)
        self.registry.register('leaf-list:max-elements', self.parsers.parse_leaf_list_max_elements)
        self.registry.register('leaf-list:description', self.parsers.parse_description)
        self.registry.register('leaf-list:must', self.parsers.parse_leaf_list_must)
        
        # Typedef body statements
        self.registry.register('typedef:type', self.parsers.parse_type)
        self.registry.register('typedef:description', self.parsers.parse_description)
        
        # Type constraint statements
        self.registry.register('type:pattern', self.parsers.parse_type_pattern)
        self.registry.register('type:length', self.parsers.parse_type_length)
        self.registry.register('type:range', self.parsers.parse_type_range)
        self.registry.register('type:fraction-digits', self.parsers.parse_type_fraction_digits)
        self.registry.register('type:enum', self.parsers.parse_type_enum)
        self.registry.register('type:path', self.parsers.parse_type_path)
        self.registry.register('type:require-instance', self.parsers.parse_type_require_instance)
        
        # Must body statements
        self.registry.register('must:error-message', self.parsers.parse_must_error_message)
        self.registry.register('must:description', self.parsers.parse_description)
    
    def parse_file(self, file_path: Path) -> YangModule:
        """Parse a YANG file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return self.parse_string(content, filename=str(file_path))
    
    def parse_string(self, content: str, filename: Optional[str] = None) -> YangModule:
        """
        Parse YANG content from a string.
        
        Args:
            content: YANG file content
            filename: Optional filename for error reporting
            
        Returns:
            Parsed YangModule
        """
        # Create fresh module
        module = YangModule()
        
        # Tokenize
        tokens = self.tokenizer.tokenize(content, filename)
        
        # Check for module statement
        if not tokens.has_more() or tokens.peek() != 'module':
            raise tokens._make_error("Expected 'module' statement at start of file")
        
        # Create context
        context = ParserContext(module=module)
        
        # Parse module
        self.parsers.parse_module(tokens, context)
        
        # Ensure we consumed all tokens
        # After parsing, there should be no more tokens (except possibly trailing empty lines)
        # The tokenizer skips whitespace, so if there are remaining tokens, they're real tokens
        if tokens.has_more():
            # Check if the remaining token is just a closing brace (might be a parsing issue)
            remaining = tokens.tokens[tokens.index:]
            if len(remaining) == 1 and remaining[0] == '}':
                # Single trailing closing brace - likely the module's closing brace wasn't consumed
                # Try to consume it and see if that resolves the issue
                tokens.consume('}')
                # If there are still more tokens after this, it's a real error
                if tokens.has_more():
                    raise tokens._make_error(f"Unexpected tokens after module: {tokens.peek()}")
            else:
                raise tokens._make_error(f"Unexpected tokens after module: {tokens.peek()}")
        
        return module


def parse_yang_file(file_path: str) -> YangModule:
    """Parse a YANG file and return a YangModule."""
    parser = YangParser()
    return parser.parse_file(Path(file_path))


def parse_yang_string(content: str) -> YangModule:
    """Parse YANG content from a string and return a YangModule."""
    parser = YangParser()
    return parser.parse_string(content)