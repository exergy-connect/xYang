"""
YANG parser implementation.

Parses YANG module files and builds an in-memory representation.
"""

from typing import List, Optional, Any, Tuple, Union
from pathlib import Path

from .module import YangModule
from .ast import (
    YangStatement, YangContainerStmt, YangListStmt, YangLeafStmt,
    YangLeafListStmt, YangTypeStmt, YangMustStmt, YangWhenStmt, YangTypedefStmt
)
from .errors import YangSyntaxError


class YangParser:
    """Parser for YANG modules."""

    def __init__(self):
        self.current_module: Optional[YangModule] = None
        self.line_num = 0
        self.lines: List[str] = []
        self.token_positions: List[Tuple[int, int]] = []  # (line_num, char_pos) for each token
        self.filename: Optional[str] = None
        
        # Module parse handlers - created once per instance
        self._module_parse_handlers: dict[str, Any] = {
            'description': self._parse_description,
            'container': self._parse_container,
            'list': self._parse_list,
            'leaf': self._parse_leaf,
            'typedef': self._parse_typedef,
            'revision': self._parse_revision,
            'leaf-list': self._parse_leaf_list,
            'yang-version': self._parse_yang_version,
            'namespace': self._parse_namespace,
            'prefix': self._parse_prefix,
            'organization': self._parse_organization,
            'contact': self._parse_contact,
        }
        
        # Type constraint parse handlers - created once per instance
        self._type_constraint_handlers: dict[str, Any] = {
            'pattern': self._parse_type_pattern,
            'length': self._parse_type_length,
            'range': self._parse_type_range,
            'fraction-digits': self._parse_type_fraction_digits,
            'enum': self._parse_type_enum,
            'path': self._parse_type_path,
            'require-instance': self._parse_type_require_instance,
            'type': self._parse_type_nested,
        }
        
        # Container body parse handlers - created once per instance
        self._container_body_handlers: dict[str, Any] = {
            'description': self._parse_description_with_parent,
            'presence': self._parse_presence,
            'when': self._parse_when,
            'leaf': self._parse_leaf,
            'container': self._parse_container,
            'list': self._parse_list,
            'leaf-list': self._parse_leaf_list,
        }
        
        # Revision body parse handlers - created once per instance
        self._revision_body_handlers: dict[str, Any] = {
            'description': self._parse_revision_description,
        }
        
        # Typedef body parse handlers - created once per instance
        self._typedef_body_handlers: dict[str, Any] = {
            'type': self._parse_typedef_type,
            'description': self._parse_description_with_parent,
        }
        
        # List body parse handlers - created once per instance
        self._list_body_handlers: dict[str, Any] = {
            'key': self._parse_list_key,
            'min-elements': self._parse_list_min_elements,
            'max-elements': self._parse_list_max_elements,
            'description': self._parse_description_with_parent,
            'when': self._parse_when,
            'leaf': self._parse_leaf,
            'container': self._parse_container,
            'list': self._parse_list,
            'leaf-list': self._parse_leaf_list,
            'must': self._parse_list_must,
        }
        
        # Leaf body parse handlers - created once per instance
        self._leaf_body_handlers: dict[str, Any] = {
            'type': self._parse_leaf_type,
            'mandatory': self._parse_leaf_mandatory,
            'default': self._parse_leaf_default,
            'description': self._parse_description_with_parent,
            'must': self._parse_leaf_must,
            'when': self._parse_when,
        }
        
        # Leaf-list body parse handlers - created once per instance
        self._leaf_list_body_handlers: dict[str, Any] = {
            'type': self._parse_leaf_list_type,
            'min-elements': self._parse_leaf_list_min_elements,
            'max-elements': self._parse_leaf_list_max_elements,
            'description': self._parse_description_with_parent,
            'must': self._parse_leaf_list_must,
        }
        
        # Must body parse handlers - created once per instance
        self._must_body_handlers: dict[str, Any] = {
            'error-message': self._parse_must_error_message,
            'description': self._parse_description_with_parent,
        }

    def parse_file(self, file_path: Path) -> YangModule:
        """Parse a YANG file."""
        self.filename = str(file_path)
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return self.parse_string(content)

    def parse_string(self, content: str) -> YangModule:
        """Parse YANG content from a string."""
        self.lines = content.split('\n')
        self.line_num = 0

        # Remove comments and normalize whitespace - optimized
        # Use list comprehension for better performance
        cleaned_lines = []
        for line in self.lines:
            # Remove single-line comments
            comment_idx = line.find('//')
            if comment_idx >= 0:
                line = line[:comment_idx]
            cleaned_lines.append(line.rstrip())

        content = '\n'.join(cleaned_lines)

        # Tokenize
        tokens = self._tokenize(content)

        # Parse module
        if not tokens or tokens[0] != 'module':
            raise self._make_error("Expected 'module' statement at start of file", 0)

        self.current_module = YangModule()
        self._parse_module(tokens, 0)

        return self.current_module

    def _tokenize(self, content: str) -> List[str]:
        """Tokenize YANG content - optimized version."""
        tokens = []
        self.token_positions = []
        i = 0
        content_len = len(content)
        special_chars = {'{', '}', ';', '=', '+'}
        
        # Build line map for position tracking
        line_map = [0]  # Character position of start of each line
        for j, char in enumerate(content):
            if char == '\n':
                line_map.append(j + 1)

        def get_line_num(pos: int) -> int:
            """Get line number (1-indexed) for character position."""
            for line_idx, line_start in enumerate(line_map):
                if line_start > pos:
                    return line_idx
            return len(line_map)

        while i < content_len:
            # Skip whitespace more efficiently
            if content[i].isspace():
                i += 1
                continue

            char = content[i]

            # String literals (quoted)
            if char in ('"', "'"):
                quote = char
                token_start = i
                i += 1
                start = i
                # Use find() for better performance on long strings
                while i < content_len:
                    if content[i] == quote:
                        break
                    if content[i] == '\\' and i + 1 < content_len:
                        i += 2  # Skip escaped character
                    else:
                        i += 1
                line_num = get_line_num(token_start)
                char_pos = token_start - line_map[line_num - 1] if line_num > 0 else 0
                tokens.append(content[start:i])
                self.token_positions.append((line_num, char_pos))
                i += 1
                continue

            # Identifiers and keywords
            if char.isalnum() or char in ('_', '-', '.'):
                token_start = i
                start = i
                i += 1
                while i < content_len:
                    c = content[i]
                    if not (c.isalnum() or c in ('_', '-', '.')):
                        break
                    i += 1
                line_num = get_line_num(token_start)
                char_pos = token_start - line_map[line_num - 1] if line_num > 0 else 0
                tokens.append(content[start:i])
                self.token_positions.append((line_num, char_pos))
                continue

            # Special characters
            if char in special_chars:
                token_start = i
                line_num = get_line_num(token_start)
                char_pos = token_start - line_map[line_num - 1] if line_num > 0 else 0
                tokens.append(char)
                self.token_positions.append((line_num, char_pos))
                i += 1
                continue

            i += 1

        return tokens

    def _make_error(self, message: str, token_pos: int, context_lines: int = 3) -> YangSyntaxError:
        """Create a syntax error with line number and context."""
        if token_pos < len(self.token_positions):
            line_num, char_pos = self.token_positions[token_pos]
        else:
            line_num = len(self.lines)
            char_pos = 0

        # Get context lines
        context = []
        start_line = max(1, line_num - context_lines)
        end_line = min(len(self.lines), line_num + context_lines)
        
        for ctx_line_num in range(start_line, end_line + 1):
            if ctx_line_num <= len(self.lines):
                context.append((ctx_line_num, self.lines[ctx_line_num - 1]))

        line = self.lines[line_num - 1] if line_num <= len(self.lines) else ""

        return YangSyntaxError(
            message=message,
            line_num=line_num,
            line=line,
            context_lines=context,
            filename=self.filename
        )

    def _parse_module(self, tokens: List[str], pos: int) -> int:
        """Parse module statement."""
        if tokens[pos] != 'module':
            raise self._make_error(f"Expected 'module' at position {pos}", pos)

        pos += 1
        if pos >= len(tokens):
            raise self._make_error("Unexpected end of file after 'module'", pos - 1)
        
        module_name = tokens[pos]
        pos += 1

        if pos >= len(tokens):
            raise self._make_error(f"Unexpected end of file after module name '{module_name}'", pos - 1)
        
        if tokens[pos] != '{':
            raise self._make_error(f"Expected '{{' after module name '{module_name}'", pos)
        pos += 1

        self.current_module.name = module_name

        # Parse module body
        # Use dict lookup for O(1) token dispatch (created once per instance)
        while pos < len(tokens) and tokens[pos] != '}':
            handler = self._module_parse_handlers.get(tokens[pos])
            if handler:
                pos = handler(tokens, pos)
            else:
                pos += 1  # Skip unknown statements for now

        return pos + 1

    def _parse_yang_version(self, tokens: List[str], pos: int) -> int:
        """Parse yang-version statement."""
        pos += 1
        if pos < len(tokens):
            version = tokens[pos]
            self.current_module.yang_version = version
            pos += 1
        if pos < len(tokens) and tokens[pos] == ';':
            pos += 1
        return pos

    def _parse_namespace(self, tokens: List[str], pos: int) -> int:
        """Parse namespace statement."""
        pos += 1
        if pos < len(tokens):
            namespace = tokens[pos].strip('"\'')
            self.current_module.namespace = namespace
            pos += 1
        if pos < len(tokens) and tokens[pos] == ';':
            pos += 1
        return pos

    def _parse_prefix(self, tokens: List[str], pos: int) -> int:
        """Parse prefix statement."""
        pos += 1
        if pos < len(tokens):
            prefix = tokens[pos].strip('"\'')
            self.current_module.prefix = prefix
            pos += 1
        if pos < len(tokens) and tokens[pos] == ';':
            pos += 1
        return pos

    def _parse_organization(self, tokens: List[str], pos: int) -> int:
        """Parse organization statement."""
        pos += 1
        if pos < len(tokens):
            org = tokens[pos].strip('"\'')
            self.current_module.organization = org
            pos += 1
        if pos < len(tokens) and tokens[pos] == ';':
            pos += 1
        return pos

    def _parse_contact(self, tokens: List[str], pos: int) -> int:
        """Parse contact statement."""
        pos += 1
        if pos < len(tokens):
            contact = tokens[pos].strip('"\'')
            self.current_module.contact = contact
            pos += 1
        if pos < len(tokens) and tokens[pos] == ';':
            pos += 1
        return pos

    def _parse_description(self, tokens: List[str], pos: int, parent: Optional[Any] = None) -> int:
        """Parse description statement."""
        if pos >= len(tokens) or tokens[pos] != 'description':
            return pos
        pos += 1  # Skip 'description' keyword
        
        if pos < len(tokens):
            # The tokenizer handles quoted strings, so the description is a single token
            desc = tokens[pos].strip('"\'')
            # Store description in parent if provided
            if parent:
                parent.description = desc
            elif self.current_module:
                # For module-level descriptions
                self.current_module.description = desc
            pos += 1  # Skip description value
        
        # Skip semicolon if present
        if pos < len(tokens) and tokens[pos] == ';':
            pos += 1
        return pos

    def _parse_revision(self, tokens: List[str], pos: int) -> int:
        """Parse revision statement."""
        pos += 1
        if pos < len(tokens):
            date = tokens[pos].strip('"\'')
            revision = {'date': date, 'description': ''}
            pos += 1

            if pos < len(tokens) and tokens[pos] == '{':
                pos += 1
                while pos < len(tokens) and tokens[pos] != '}':
                    if tokens[pos] == 'description':
                        pos += 1
                        if pos < len(tokens):
                            revision['description'] = tokens[pos].strip('"\'')
                            pos += 1
                    else:
                        pos += 1
                if pos < len(tokens) and tokens[pos] == '}':
                    pos += 1

            self.current_module.revisions.append(revision)

        if pos < len(tokens) and tokens[pos] == ';':
            pos += 1
        return pos

    def _parse_typedef(self, tokens: List[str], pos: int) -> int:
        """Parse typedef statement."""
        pos += 1
        if pos >= len(tokens):
            return pos

        typedef_name = tokens[pos]
        pos += 1

        if pos < len(tokens) and tokens[pos] == '{':
            pos += 1
            typedef_stmt = YangTypedefStmt(name=typedef_name)

            while pos < len(tokens) and tokens[pos] != '}':
                handler = self._typedef_body_handlers.get(tokens[pos])
                if handler:
                    pos = handler(tokens, pos, typedef_stmt)
                else:
                    pos += 1

            if pos < len(tokens) and tokens[pos] == '}':
                pos += 1

            self.current_module.typedefs[typedef_name] = typedef_stmt

        if pos < len(tokens) and tokens[pos] == ';':
            pos += 1
        return pos

    def _parse_type(self, tokens: List[str], pos: int, parent: Any) -> int:
        """Parse type statement."""
        pos += 1
        if pos >= len(tokens):
            return pos

        type_name = tokens[pos]
        pos += 1

        type_stmt = YangTypeStmt(name=type_name)

        if pos < len(tokens) and tokens[pos] == '{':
            pos += 1
            brace_depth = 1  # Track nested braces for union types
            while pos < len(tokens) and brace_depth > 0:
                if tokens[pos] == '{':
                    brace_depth += 1
                elif tokens[pos] == '}':
                    brace_depth -= 1
                    if brace_depth == 0:
                        break
                
                if brace_depth == 1:  # Only process at the current level
                    handler = self._type_constraint_handlers.get(tokens[pos])
                    if handler:
                        pos = handler(tokens, pos, type_stmt)
                    else:
                        pos += 1
                else:
                    pos += 1

            if pos < len(tokens) and tokens[pos] == '}':
                pos += 1

        if hasattr(parent, 'type') and not parent.type:
            parent.type = type_stmt
        elif hasattr(parent, 'types'):
            if not hasattr(parent, 'types') or parent.types is None:
                parent.types = []
            parent.types.append(type_stmt)
        elif hasattr(parent, 'type'):
            # For union types, add to types list
            if not hasattr(type_stmt, 'types'):
                type_stmt.types = []
            if not hasattr(parent.type, 'types'):
                parent.type.types = []
            parent.type.types.append(type_stmt)

        if pos < len(tokens) and tokens[pos] == ';':
            pos += 1
        return pos

    def _parse_type_pattern(self, tokens: List[str], pos: int, type_stmt: Any) -> int:
        """Parse pattern constraint."""
        pos += 1
        if pos < len(tokens):
            pattern = tokens[pos].strip('"\'')
            type_stmt.pattern = pattern
            pos += 1
        return pos

    def _parse_type_length(self, tokens: List[str], pos: int, type_stmt: Any) -> int:
        """Parse length constraint."""
        pos += 1
        if pos < len(tokens):
            length = tokens[pos].strip('"\'')
            type_stmt.length = length
            pos += 1
        return pos

    def _parse_type_range(self, tokens: List[str], pos: int, type_stmt: Any) -> int:
        """Parse range constraint."""
        pos += 1
        if pos < len(tokens):
            range_val = tokens[pos].strip('"\'')
            type_stmt.range = range_val
            pos += 1
        return pos

    def _parse_type_fraction_digits(self, tokens: List[str], pos: int, type_stmt: Any) -> int:
        """Parse fraction-digits constraint."""
        pos += 1
        if pos < len(tokens):
            type_stmt.fraction_digits = int(tokens[pos])
            pos += 1
        return pos

    def _parse_type_enum(self, tokens: List[str], pos: int, type_stmt: Any) -> int:
        """Parse enum constraint."""
        pos += 1
        enum_name = tokens[pos] if pos < len(tokens) else None
        if enum_name:
            type_stmt.enums.append(enum_name)
            pos += 1
        return pos

    def _parse_type_path(self, tokens: List[str], pos: int, type_stmt: Any) -> int:
        """Parse path constraint (for leafref)."""
        pos += 1
        if pos < len(tokens):
            path = tokens[pos].strip('"\'')
            type_stmt.path = path
            pos += 1
        return pos

    def _parse_type_require_instance(self, tokens: List[str], pos: int, type_stmt: Any) -> int:
        """Parse require-instance constraint (for leafref)."""
        pos += 1
        if pos < len(tokens):
            require_instance = tokens[pos].strip('"\'')
            type_stmt.require_instance = require_instance == 'true'
            pos += 1
        return pos

    def _parse_type_nested(self, tokens: List[str], pos: int, type_stmt: Any) -> int:
        """Parse nested type statement (for union types)."""
        # Handle nested type statements (for union types)
        nested_type_stmt = YangTypeStmt(name="")
        new_pos = self._parse_type(tokens, pos, nested_type_stmt)
        if not hasattr(type_stmt, 'types'):
            type_stmt.types = []
        type_stmt.types.append(nested_type_stmt)
        return new_pos  # Return the new position after parsing the nested type

    def _parse_description_with_parent(self, tokens: List[str], pos: int, parent: Any) -> int:
        """Wrapper for _parse_description that accepts parent parameter."""
        return self._parse_description(tokens, pos, parent)

    def _parse_revision_description(self, tokens: List[str], pos: int, revision: dict) -> int:
        """Parse description in revision statement."""
        pos += 1
        if pos < len(tokens):
            revision['description'] = tokens[pos].strip('"\'')
            pos += 1
        return pos

    def _parse_typedef_type(self, tokens: List[str], pos: int, typedef_stmt: Any) -> int:
        """Parse type in typedef statement."""
        return self._parse_type(tokens, pos, typedef_stmt)

    def _parse_list_key(self, tokens: List[str], pos: int, list_stmt: Any) -> int:
        """Parse key in list statement."""
        pos += 1
        if pos < len(tokens):
            list_stmt.key = tokens[pos].strip('"\'')
            pos += 1
        return pos

    def _parse_list_min_elements(self, tokens: List[str], pos: int, list_stmt: Any) -> int:
        """Parse min-elements in list statement."""
        pos += 1
        if pos < len(tokens):
            list_stmt.min_elements = int(tokens[pos])
            pos += 1
        return pos

    def _parse_list_max_elements(self, tokens: List[str], pos: int, list_stmt: Any) -> int:
        """Parse max-elements in list statement."""
        pos += 1
        if pos < len(tokens):
            list_stmt.max_elements = int(tokens[pos])
            pos += 1
        return pos

    def _parse_list_must(self, tokens: List[str], pos: int, list_stmt: Any) -> int:
        """Parse must in list statement."""
        must_stmt = YangMustStmt(expression="")
        pos = self._parse_must(tokens, pos)
        if not hasattr(list_stmt, 'must_statements'):
            list_stmt.must_statements = []
        list_stmt.must_statements.append(must_stmt)
        return pos

    def _parse_leaf_type(self, tokens: List[str], pos: int, leaf_stmt: Any) -> int:
        """Parse type in leaf statement."""
        return self._parse_type(tokens, pos, leaf_stmt)

    def _parse_leaf_mandatory(self, tokens: List[str], pos: int, leaf_stmt: Any) -> int:
        """Parse mandatory in leaf statement."""
        pos += 1
        if pos < len(tokens):
            mandatory_val = tokens[pos]
            leaf_stmt.mandatory = mandatory_val == 'true'
            pos += 1
        return pos

    def _parse_leaf_default(self, tokens: List[str], pos: int, leaf_stmt: Any) -> int:
        """Parse default in leaf statement."""
        pos += 1
        if pos < len(tokens):
            leaf_stmt.default = tokens[pos].strip('"\'')
            pos += 1
        return pos

    def _parse_leaf_must(self, tokens: List[str], pos: int, leaf_stmt: Any) -> int:
        """Parse must in leaf statement."""
        must_stmt = YangMustStmt(expression="")
        pos = self._parse_must(tokens, pos)
        leaf_stmt.must_statements.append(must_stmt)
        return pos

    def _parse_leaf_list_type(self, tokens: List[str], pos: int, leaf_list_stmt: Any) -> int:
        """Parse type in leaf-list statement."""
        return self._parse_type(tokens, pos, leaf_list_stmt)

    def _parse_leaf_list_min_elements(self, tokens: List[str], pos: int, leaf_list_stmt: Any) -> int:
        """Parse min-elements in leaf-list statement."""
        pos += 1
        if pos < len(tokens):
            leaf_list_stmt.min_elements = int(tokens[pos])
            pos += 1
        return pos

    def _parse_leaf_list_max_elements(self, tokens: List[str], pos: int, leaf_list_stmt: Any) -> int:
        """Parse max-elements in leaf-list statement."""
        pos += 1
        if pos < len(tokens):
            leaf_list_stmt.max_elements = int(tokens[pos])
            pos += 1
        return pos

    def _parse_leaf_list_must(self, tokens: List[str], pos: int, leaf_list_stmt: Any) -> int:
        """Parse must in leaf-list statement."""
        return self._parse_must(tokens, pos)

    def _parse_must_error_message(self, tokens: List[str], pos: int, must_stmt: Any) -> int:
        """Parse error-message in must statement."""
        pos += 1
        if pos < len(tokens):
            must_stmt.error_message = tokens[pos].strip('"\'')
            pos += 1
        return pos

    def _parse_presence(self, tokens: List[str], pos: int, parent: Any) -> int:
        """Parse presence statement for container."""
        pos += 1
        if pos < len(tokens):
            parent.presence = tokens[pos].strip('"\'')
            pos += 1
        return pos

    def _parse_container(self, tokens: List[str], pos: int, parent: Optional[YangStatement] = None) -> int:
        """Parse container statement."""
        pos += 1
        if pos >= len(tokens):
            return pos

        container_name = tokens[pos]
        pos += 1

        container_stmt = YangContainerStmt(name=container_name)

        if pos < len(tokens) and tokens[pos] == '{':
            pos += 1
            prev_pos = -1
            while pos < len(tokens) and tokens[pos] != '}':
                # Safety check to prevent infinite loops
                if pos == prev_pos:
                    raise self._make_error(f"Infinite loop detected at position {pos}, token: {tokens[pos] if pos < len(tokens) else 'EOF'}", pos)
                prev_pos = pos
                handler = self._container_body_handlers.get(tokens[pos])
                if handler:
                    new_pos = handler(tokens, pos, container_stmt)
                    if new_pos <= pos:
                        raise self._make_error(f"Handler for '{tokens[pos]}' did not advance position (was {pos}, now {new_pos})", pos)
                    pos = new_pos
                else:
                    pos += 1

            if pos < len(tokens) and tokens[pos] == '}':
                pos += 1

        # Add to parent if provided, otherwise to module
        if parent:
            if not hasattr(parent, 'statements'):
                parent.statements = []
            parent.statements.append(container_stmt)
        else:
            if not hasattr(self.current_module, 'statements'):
                self.current_module.statements = []
            self.current_module.statements.append(container_stmt)

        if pos < len(tokens) and tokens[pos] == ';':
            pos += 1
        return pos

    def _parse_list(self, tokens: List[str], pos: int, parent: Optional[YangStatement] = None) -> int:
        """Parse list statement."""
        pos += 1
        if pos >= len(tokens):
            return pos

        list_name = tokens[pos]
        pos += 1

        list_stmt = YangListStmt(name=list_name)

        if pos < len(tokens) and tokens[pos] == '{':
            pos += 1
            while pos < len(tokens) and tokens[pos] != '}':
                handler = self._list_body_handlers.get(tokens[pos])
                if handler:
                    pos = handler(tokens, pos, list_stmt)
                else:
                    pos += 1

            if pos < len(tokens) and tokens[pos] == '}':
                pos += 1

        # Add to parent if provided, otherwise to module
        if parent:
            if not hasattr(parent, 'statements'):
                parent.statements = []
            parent.statements.append(list_stmt)
        else:
            if not hasattr(self.current_module, 'statements'):
                self.current_module.statements = []
            self.current_module.statements.append(list_stmt)

        if pos < len(tokens) and tokens[pos] == ';':
            pos += 1
        return pos

    def _parse_leaf(self, tokens: List[str], pos: int, parent: Optional[YangStatement] = None) -> int:
        """Parse leaf statement."""
        pos += 1
        if pos >= len(tokens):
            return pos

        leaf_name = tokens[pos]
        pos += 1

        leaf_stmt = YangLeafStmt(name=leaf_name)

        if pos < len(tokens) and tokens[pos] == '{':
            pos += 1
            while pos < len(tokens) and tokens[pos] != '}':
                handler = self._leaf_body_handlers.get(tokens[pos])
                if handler:
                    pos = handler(tokens, pos, leaf_stmt)
                else:
                    pos += 1

            if pos < len(tokens) and tokens[pos] == '}':
                pos += 1

        # Add to parent if provided, otherwise to module
        if parent:
            if not hasattr(parent, 'statements'):
                parent.statements = []
            parent.statements.append(leaf_stmt)
        else:
            if not hasattr(self.current_module, 'statements'):
                self.current_module.statements = []
            self.current_module.statements.append(leaf_stmt)

        if pos < len(tokens) and tokens[pos] == ';':
            pos += 1
        return pos

    def _parse_leaf_list(self, tokens: List[str], pos: int, parent: Optional[YangStatement] = None) -> int:
        """Parse leaf-list statement."""
        pos += 1
        if pos >= len(tokens):
            return pos

        leaf_list_name = tokens[pos]
        pos += 1

        leaf_list_stmt = YangLeafListStmt(name=leaf_list_name)

        if pos < len(tokens) and tokens[pos] == '{':
            pos += 1
            while pos < len(tokens) and tokens[pos] != '}':
                handler = self._leaf_list_body_handlers.get(tokens[pos])
                if handler:
                    pos = handler(tokens, pos, leaf_list_stmt)
                else:
                    pos += 1

            if pos < len(tokens) and tokens[pos] == '}':
                pos += 1

        # Add to parent if provided, otherwise to module
        if parent:
            if not hasattr(parent, 'statements'):
                parent.statements = []
            parent.statements.append(leaf_list_stmt)
        else:
            if not hasattr(self.current_module, 'statements'):
                self.current_module.statements = []
            self.current_module.statements.append(leaf_list_stmt)

        if pos < len(tokens) and tokens[pos] == ';':
            pos += 1
        return pos

    def _parse_must(self, tokens: List[str], pos: int) -> int:
        """Parse must statement."""
        pos += 1
        if pos >= len(tokens):
            return pos

        # Extract XPath expression (simplified)
        expr_parts = []
        if pos < len(tokens) and tokens[pos] == '"':
            pos += 1
            while pos < len(tokens) and tokens[pos] != '"':
                expr_parts.append(tokens[pos])
                pos += 1
            if pos < len(tokens):
                pos += 1

        must_stmt = YangMustStmt(expression=' '.join(expr_parts))

        if pos < len(tokens) and tokens[pos] == '{':
            pos += 1
            while pos < len(tokens) and tokens[pos] != '}':
                handler = self._must_body_handlers.get(tokens[pos])
                if handler:
                    pos = handler(tokens, pos, must_stmt)
                else:
                    pos += 1

            if pos < len(tokens) and tokens[pos] == '}':
                pos += 1

        return pos

    def _parse_when(self, tokens: List[str], pos: int, parent: Optional[YangStatement] = None) -> int:
        """Parse when statement."""
        pos += 1
        if pos >= len(tokens):
            return pos

        # Extract XPath expression
        expr_parts = []
        if pos < len(tokens):
            # Handle quoted expression
            if tokens[pos] in ('"', "'"):
                quote = tokens[pos]
                pos += 1
                while pos < len(tokens) and tokens[pos] != quote:
                    expr_parts.append(tokens[pos])
                    pos += 1
                if pos < len(tokens):
                    pos += 1
            else:
                # Unquoted expression (shouldn't happen in YANG but handle it)
                while pos < len(tokens) and tokens[pos] != ';' and tokens[pos] != '{':
                    expr_parts.append(tokens[pos])
                    pos += 1

        when_stmt = YangWhenStmt(condition=' '.join(expr_parts))

        # Store in parent statement
        if parent:
            if hasattr(parent, 'when'):
                parent.when = when_stmt
            elif hasattr(parent, 'statements'):
                # If parent doesn't have when attribute, store as statement
                pass

        if pos < len(tokens) and tokens[pos] == ';':
            pos += 1

        return pos


def parse_yang_file(file_path: str) -> YangModule:
    """Parse a YANG file and return a YangModule."""
    parser = YangParser()
    return parser.parse_file(Path(file_path))


def parse_yang_string(content: str) -> YangModule:
    """Parse YANG content from a string and return a YangModule."""
    parser = YangParser()
    return parser.parse_string(content)
