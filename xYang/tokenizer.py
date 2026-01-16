"""
YANG tokenizer implementation.
"""

from typing import Optional
from .parser_context import TokenStream


class YangTokenizer:
    """Tokenizer for YANG content."""
    
    def tokenize(self, content: str, filename: Optional[str] = None) -> TokenStream:
        """
        Tokenize YANG content and return a TokenStream.
        
        Args:
            content: YANG file content
            filename: Optional filename for error reporting
            
        Returns:
            TokenStream with tokens and position information
        """
        lines = content.split('\n')
        
        # Remove comments and normalize whitespace
        cleaned_lines = []
        for line in lines:
            # Remove single-line comments
            comment_idx = line.find('//')
            if comment_idx >= 0:
                line = line[:comment_idx]
            cleaned_lines.append(line.rstrip())
        
        content = '\n'.join(cleaned_lines)
        
        # Tokenize
        tokens = []
        token_positions = []
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
            # Skip whitespace
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
                token_positions.append((line_num, char_pos))
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
                token_positions.append((line_num, char_pos))
                continue
            
            # Special characters
            if char in special_chars:
                token_start = i
                line_num = get_line_num(token_start)
                char_pos = token_start - line_map[line_num - 1] if line_num > 0 else 0
                tokens.append(char)
                token_positions.append((line_num, char_pos))
                i += 1
                continue
            
            i += 1
        
        return TokenStream(tokens, token_positions, lines, filename)