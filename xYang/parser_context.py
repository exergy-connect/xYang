"""
Parser context and token stream abstractions.
"""

from typing import List, Tuple, Optional, TYPE_CHECKING
from dataclasses import dataclass
from .errors import YangSyntaxError

if TYPE_CHECKING:
    from .module import YangModule
    from .ast import YangStatement


@dataclass
class Token:
    """A token with position information."""
    value: str
    line_num: int
    char_pos: int


class TokenStream:
    """Abstraction over token list with position tracking."""
    
    def __init__(self, tokens: List[str], positions: List[Tuple[int, int]], lines: List[str], filename: Optional[str] = None):
        self.tokens = tokens
        self.positions = positions
        self.lines = lines
        self.filename = filename
        self.index = 0
    
    def peek(self) -> Optional[str]:
        """Peek at current token without consuming."""
        if self.index < len(self.tokens):
            return self.tokens[self.index]
        return None
    
    def consume(self, expected: Optional[str] = None) -> str:
        """Consume current token, optionally checking it matches expected."""
        if self.index >= len(self.tokens):
            raise self._make_error("Unexpected end of input")
        
        token = self.tokens[self.index]
        if expected is not None and token != expected:
            raise self._make_error(f"Expected {expected!r}, got {token!r}")
        
        self.index += 1
        return token
    
    def consume_if(self, expected: str) -> bool:
        """Consume token if it matches expected, return True if consumed."""
        if self.peek() == expected:
            self.consume()
            return True
        return False
    
    def has_more(self) -> bool:
        """Check if there are more tokens."""
        return self.index < len(self.tokens)
    
    def position(self) -> Tuple[int, int]:
        """Get current position (line_num, char_pos)."""
        if self.index < len(self.positions):
            return self.positions[self.index]
        if self.positions:
            return self.positions[-1]
        return (1, 0)
    
    def _make_error(self, message: str, context_lines: int = 3) -> YangSyntaxError:
        """Create a syntax error at current position."""
        line_num, char_pos = self.position()
        
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


@dataclass
class ParserContext:
    """Context for parsing, holds module and current state."""
    module: 'YangModule'
    current_parent: Optional['YangStatement'] = None
    
    def push_parent(self, parent: 'YangStatement') -> 'ParserContext':
        """Create new context with updated parent."""
        return ParserContext(module=self.module, current_parent=parent)