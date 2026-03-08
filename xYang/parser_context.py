"""
Parser context and token stream abstractions.

Token types follow the minimal YANG grammar (meta-model-grammar.ebnf).
"""

from enum import Enum
from typing import List, Tuple, Optional, TYPE_CHECKING
from dataclasses import dataclass
from .errors import YangSyntaxError

if TYPE_CHECKING:
    from .module import YangModule
    from .ast import YangStatement


class YangTokenType(Enum):
    """Token types from the YANG grammar (meta-model-grammar.ebnf)."""

    # Punctuation
    LBRACE = "{"
    RBRACE = "}"
    SEMICOLON = ";"
    EQUALS = "="
    PLUS = "+"
    SLASH = "/"

    # Literals (value is lexeme)
    STRING = "STRING"
    IDENTIFIER = "IDENTIFIER"
    INTEGER = "INTEGER"

    # Keywords (value in token is the keyword string)
    MODULE = "module"
    YANG_VERSION = "yang-version"
    NAMESPACE = "namespace"
    PREFIX = "prefix"
    ORGANIZATION = "organization"
    CONTACT = "contact"
    DESCRIPTION = "description"
    REVISION = "revision"
    TYPEDEF = "typedef"
    TYPE = "type"
    UNION = "union"
    LEAFREF = "leafref"
    PATH = "path"
    REQUIRE_INSTANCE = "require-instance"
    ENUM = "enum"
    ENUMERATION = "enumeration"
    STRING_KW = "string"
    PATTERN = "pattern"
    LENGTH = "length"
    INT32 = "int32"
    UINT8 = "uint8"
    DECIMAL64 = "decimal64"
    FRACTION_DIGITS = "fraction-digits"
    RANGE = "range"
    GROUPING = "grouping"
    USES = "uses"
    REFINE = "refine"
    CONTAINER = "container"
    LIST = "list"
    LEAF = "leaf"
    LEAF_LIST = "leaf-list"
    CHOICE = "choice"
    CASE = "case"
    MUST = "must"
    WHEN = "when"
    PRESENCE = "presence"
    KEY = "key"
    MIN_ELEMENTS = "min-elements"
    MAX_ELEMENTS = "max-elements"
    MANDATORY = "mandatory"
    DEFAULT = "default"
    ERROR_MESSAGE = "error-message"
    TRUE = "true"
    FALSE = "false"


# Map keyword lexeme -> YangTokenType for tokenizer
YANG_KEYWORDS = {
    tt.value: tt
    for tt in YangTokenType
    if tt not in (YangTokenType.STRING, YangTokenType.IDENTIFIER, YangTokenType.INTEGER)
    and tt not in (
        YangTokenType.LBRACE, YangTokenType.RBRACE, YangTokenType.SEMICOLON,
        YangTokenType.EQUALS, YangTokenType.PLUS, YangTokenType.SLASH,
    )
}


@dataclass
class Token:
    """A token with position information."""
    value: str
    line_num: int
    char_pos: int


@dataclass
class YangToken:
    """A YANG token: type (from grammar) and value (lexeme), with position."""
    type: YangTokenType
    value: str
    line_num: int
    char_pos: int


class TokenStream:
    """Abstraction over token list with position tracking."""

    def __init__(
        self,
        token_list: List[YangToken],
        lines: List[str],
        filename: Optional[str] = None,
    ):
        self._token_list = token_list
        self.tokens = [t.value for t in token_list]
        self.positions = [(t.line_num, t.char_pos) for t in token_list]
        self.lines = lines
        self.filename = filename
        self.index = 0

    def peek_token(self) -> Optional[YangToken]:
        """Peek at current token without consuming."""
        if self.index < len(self._token_list):
            return self._token_list[self.index]
        return None

    def peek(self) -> Optional[str]:
        """Peek at current token value without consuming."""
        tok = self.peek_token()
        return tok.value if tok else None

    def consume(self, expected: Optional[str] = None) -> str:
        """Consume current token, optionally checking it matches expected."""
        if self.index >= len(self.tokens):
            raise self._make_error("Unexpected end of input")

        token_val = self.tokens[self.index]
        if expected is not None and token_val != expected:
            raise self._make_error(f"Expected {expected!r}, got {token_val!r}")

        self.index += 1
        return token_val

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