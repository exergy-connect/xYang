"""
Parser context and token stream abstractions.

Token types follow the minimal YANG grammar (meta-model-grammar.ebnf).
"""

from enum import Enum
from typing import List, Tuple, Optional, TYPE_CHECKING, Union
from dataclasses import dataclass
from ..errors import YangSyntaxError

if TYPE_CHECKING:
    from ..module import YangModule
    from ..ast import (
        YangStatement,
        YangStatementList,
        YangTypeStmt,
        YangMustStmt,
        YangWhenStmt,
    )


# Type for parser context parent: statement lists or nested statement contexts (type/must/when)
_ParserParent = Union[
    "YangStatementList", "YangTypeStmt", "YangMustStmt", "YangWhenStmt"
]


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
    # Unquoted \d+(\.\d+)+ — e.g. yang-version 1.1; not an identifier per RFC 7950.
    DOTTED_NUMBER = "DOTTED_NUMBER"

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
    IDENTITY = "identity"
    BASE = "base"
    TYPE = "type"
    # RFC 7950 built-in types (Section 4.2.4) — lexer keywords, same spelling as YANG source.
    BINARY = "binary"
    BITS = "bits"
    BOOLEAN = "boolean"
    DECIMAL64 = "decimal64"
    EMPTY = "empty"
    ENUMERATION = "enumeration"
    IDENTITYREF = "identityref"
    INSTANCE_IDENTIFIER = "instance-identifier"
    INT8 = "int8"
    INT16 = "int16"
    INT32 = "int32"
    INT64 = "int64"
    LEAFREF = "leafref"
    STRING_KW = "string"
    UINT8 = "uint8"
    UINT16 = "uint16"
    UINT32 = "uint32"
    UINT64 = "uint64"
    UNION = "union"
    PATH = "path"
    REQUIRE_INSTANCE = "require-instance"
    ENUM = "enum"
    BIT = "bit"
    POSITION = "position"
    PATTERN = "pattern"
    LENGTH = "length"
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
    ORDERED_BY = "ordered-by"
    MANDATORY = "mandatory"
    DEFAULT = "default"
    ERROR_MESSAGE = "error-message"
    TRUE = "true"
    FALSE = "false"


def diagnostic_source_lines(content: str) -> List[str]:
    """Split source on newlines for error snippets (verbatim text, comments included)."""
    if not content:
        return []
    return [segment.rstrip("\r") for segment in content.split("\n")]


# Map keyword lexeme -> YangTokenType for tokenizer
YANG_KEYWORDS = {
    tt.value: tt
    for tt in YangTokenType
    if tt
    not in (
        YangTokenType.STRING,
        YangTokenType.IDENTIFIER,
        YangTokenType.INTEGER,
        YangTokenType.DOTTED_NUMBER,
    )
    and tt
    not in (
        YangTokenType.LBRACE,
        YangTokenType.RBRACE,
        YangTokenType.SEMICOLON,
        YangTokenType.EQUALS,
        YangTokenType.PLUS,
        YangTokenType.SLASH,
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
        source: str,
        filename: Optional[str] = None,
    ):
        self._token_list = token_list
        self.tokens = [t.value for t in token_list]
        self.positions = [(t.line_num, t.char_pos) for t in token_list]
        self._source = source
        self._diagnostic_lines: Optional[List[str]] = None
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

    def peek_type(self) -> Optional[YangTokenType]:
        """Peek at current token type without consuming."""
        tok = self.peek_token()
        return tok.type if tok else None

    def consume_type(self, expected: YangTokenType) -> str:
        """Consume current token if its type matches expected; raise otherwise. Returns value."""
        if self.index >= len(self._token_list):
            raise self._make_error("Unexpected end of input")
        tok = self._token_list[self.index]
        if tok.type != expected:
            raise self._make_error(f"Expected {expected.name}, got {tok.type.name} ({tok.value!r})")
        self.index += 1
        return tok.value

    def consume_if_type(self, expected: YangTokenType) -> bool:
        """Consume token if its type matches expected, return True if consumed."""
        if self.peek_type() == expected:
            self.consume_type(expected)
            return True
        return False

    def consume_oneof(self, allowed_types: List[YangTokenType]) -> Tuple[str, YangTokenType]:
        """Consume current token if its type is in allowed_types; raise otherwise.
        Returns (token_value, token_type)."""
        if self.index >= len(self._token_list):
            raise self._make_error("Unexpected end of input")
        tok = self._token_list[self.index]
        if tok.type not in allowed_types:
            names = ", ".join(t.name for t in allowed_types)
            raise self._make_error(
                f"Expected one of ({names}), got {tok.type.name} ({tok.value!r})"
            )
        self.index += 1
        return (tok.value, tok.type)

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
    
    def _diagnostic_lines_once(self) -> List[str]:
        """Build per-line source text for errors (lazy, at most once per stream)."""
        if self._diagnostic_lines is None:
            self._diagnostic_lines = diagnostic_source_lines(self._source)
        return self._diagnostic_lines

    def _make_error(self, message: str, context_lines: int = 3) -> YangSyntaxError:
        """Create a syntax error at current position."""
        line_num, _ = self.position()
        lines = self._diagnostic_lines_once()

        context = []
        start_line = max(1, line_num - context_lines)
        end_line = min(len(lines), line_num + context_lines)

        for ctx_line_num in range(start_line, end_line + 1):
            if ctx_line_num <= len(lines):
                context.append((ctx_line_num, lines[ctx_line_num - 1]))

        line = lines[line_num - 1] if line_num <= len(lines) else ""
        
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
    module: "YangModule"
    current_parent: _ParserParent

    def push_parent(self, parent: _ParserParent) -> "ParserContext":
        """Create new context with updated parent."""
        return ParserContext(module=self.module, current_parent=parent)