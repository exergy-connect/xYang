"""
XPath token types and Token class (used by xpath tokenizer/parser).
"""

from enum import Enum


class TokenType(Enum):
    """XPath token types."""
    IDENTIFIER = "IDENTIFIER"
    NUMBER = "NUMBER"
    STRING = "STRING"
    OPERATOR = "OPERATOR"
    PAREN_OPEN = "PAREN_OPEN"
    PAREN_CLOSE = "PAREN_CLOSE"
    BRACKET_OPEN = "BRACKET_OPEN"
    BRACKET_CLOSE = "BRACKET_CLOSE"
    DOT = "DOT"
    DOTDOT = "DOTDOT"
    SLASH = "SLASH"
    COMMA = "COMMA"
    EOF = "EOF"


class Token:
    """XPath token."""

    def __init__(self, token_type: TokenType, value: str, position: int = 0):
        self.type = token_type
        self.value = value
        self.position = position

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, pos={self.position})"
