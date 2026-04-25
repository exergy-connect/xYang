"""
XPath expression tokenizer for xpath.
"""

from typing import List, Optional, Set

from .tokens import Token, TokenType

QUOTE_CHARS: Set[str] = {'"', "'"}
OPERATOR_CHARS: Set[str] = {'=', '<', '>', '!', '+', '-', '*', '/'}


class XPathTokenizer:
    """Tokenizer for XPath expressions."""

    OPERATORS = [
        '<=', '>=', '!=', '==', '//',
        '=', '<', '>', '+', '-', '*', '/',
    ]

    KEYWORDS = ['or', 'and', 'not', 'true', 'false', 'current']

    def __init__(self, expression: str):
        self.expression = expression
        self.position = 0
        self.tokens: List[Token] = []

    def tokenize(self) -> List[Token]:
        """Tokenize the expression."""
        self.position = 0
        self.tokens = []

        while self.position < len(self.expression):
            if self._skip_whitespace():
                continue

            if self.position >= len(self.expression):
                break

            char = self.expression[self.position]

            if char in QUOTE_CHARS:
                self._tokenize_string()
            elif char.isdigit() or (char == '-' and self._is_next_digit()):
                self._tokenize_number()
            elif char.isalpha() or char == '_':
                self._tokenize_identifier()
            elif char == '/':
                self._tokenize_slash()
            elif char == '.':
                self._tokenize_dot()
            elif char in OPERATOR_CHARS:
                self._tokenize_operator()
            elif char == '(':
                self._add_simple_token(TokenType.PAREN_OPEN, '(', 1)
            elif char == ')':
                self._add_simple_token(TokenType.PAREN_CLOSE, ')', 1)
            elif char == '[':
                self._add_simple_token(TokenType.BRACKET_OPEN, '[', 1)
            elif char == ']':
                self._add_simple_token(TokenType.BRACKET_CLOSE, ']', 1)
            elif char == ',':
                self._add_simple_token(TokenType.COMMA, ',', 1)
            else:
                self.position += 1

        self.tokens.append(Token(TokenType.EOF, '', self.position))
        return self.tokens

    def _add_simple_token(self, token_type: TokenType, value: str, advance: int):
        self.tokens.append(Token(token_type, value, self.position))
        self.position += advance

    def _skip_whitespace(self) -> bool:
        if self.position < len(self.expression) and self.expression[self.position].isspace():
            while self.position < len(self.expression) and self.expression[self.position].isspace():
                self.position += 1
            return True
        return False

    def _is_next_digit(self) -> bool:
        return (self.position + 1 < len(self.expression) and
                self.expression[self.position + 1].isdigit())

    def _peek_char(self, offset: int = 0) -> Optional[str]:
        pos = self.position + offset
        return self.expression[pos] if 0 <= pos < len(self.expression) else None

    def _tokenize_string(self):
        quote_char = self.expression[self.position]
        start_pos = self.position
        self.position += 1

        value = []
        while self.position < len(self.expression):
            char = self.expression[self.position]
            if char == quote_char:
                if self.position > 0 and self.expression[self.position - 1] == '\\':
                    value[-1] = quote_char
                else:
                    self.position += 1
                    break
            value.append(char)
            self.position += 1

        self.tokens.append(Token(TokenType.STRING, ''.join(value), start_pos))

    def _tokenize_number(self):
        start_pos = self.position
        value = []

        if self.expression[self.position] == '-':
            value.append('-')
            self.position += 1

        while self.position < len(self.expression) and self.expression[self.position].isdigit():
            value.append(self.expression[self.position])
            self.position += 1

        if (self._peek_char() == '.' and self._peek_char(1) and
            self._peek_char(1).isdigit()):
            value.append('.')
            self.position += 1
            while self.position < len(self.expression) and self.expression[self.position].isdigit():
                value.append(self.expression[self.position])
                self.position += 1

        self.tokens.append(Token(TokenType.NUMBER, ''.join(value), start_pos))

    def _tokenize_identifier(self):
        start_pos = self.position
        value = []

        while self.position < len(self.expression):
            char = self.expression[self.position]
            if char.isalnum() or char in ('_', '-', ':'):
                value.append(char)
                self.position += 1
            else:
                break

        identifier = ''.join(value)
        self.tokens.append(Token(TokenType.IDENTIFIER, identifier, start_pos))

    def _tokenize_operator(self):
        start_pos = self.position
        remaining = self.expression[self.position:]

        for op in self.OPERATORS:
            if remaining.startswith(op):
                self.tokens.append(Token(TokenType.OPERATOR, op, start_pos))
                self.position += len(op)
                return

        char = self.expression[self.position]
        self.tokens.append(Token(TokenType.OPERATOR, char, start_pos))
        self.position += 1

    def _tokenize_dot(self):
        start_pos = self.position

        if self._peek_char(1) == '.':
            self.tokens.append(Token(TokenType.DOTDOT, '..', start_pos))
            self.position += 2
        else:
            self.tokens.append(Token(TokenType.DOT, '.', start_pos))
            self.position += 1

    def _tokenize_slash(self):
        start_pos = self.position

        if self._peek_char(1) == '/':
            self.tokens.append(Token(TokenType.OPERATOR, '//', start_pos))
            self.position += 2
        else:
            self.tokens.append(Token(TokenType.SLASH, '/', start_pos))
            self.position += 1
