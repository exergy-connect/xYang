"""
XPath expression tokenizer and parser.
"""

from typing import List, Optional, Set

from .ast import (
    Token, TokenType, XPathNode, LiteralNode, PathNode, CurrentNode,
    FunctionCallNode, BinaryOpNode, UnaryOpNode
)
from ..errors import XPathSyntaxError


# Constants for operator sets
COMPARISON_OPS: Set[str] = {'=', '!=', '<', '>', '<=', '>='}
ADDITIVE_OPS: Set[str] = {'+', '-'}
MULTIPLICATIVE_OPS: Set[str] = {'*', '/'}
BOOLEAN_KEYWORDS: Set[str] = {'true', 'false'}
LOGICAL_KEYWORDS: Set[str] = {'or', 'and', 'not'}
QUOTE_CHARS: Set[str] = {'"', "'"}
OPERATOR_CHARS: Set[str] = {'=', '<', '>', '!', '+', '-', '*', '/'}


class XPathTokenizer:
    """Tokenizer for XPath expressions."""

    # Operator patterns (ordered by length to match longer operators first)
    OPERATORS = [
        '<=', '>=', '!=', '==', '//',  # Two-character operators
        '=', '<', '>', '+', '-', '*', '/',  # Single-character operators
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
            
            # Dispatch to appropriate tokenizer
            if char in QUOTE_CHARS:
                self._tokenize_string()
            elif char.isdigit() or (char == '-' and self._is_next_digit()):
                self._tokenize_number()
            elif char.isalpha() or char == '_':
                self._tokenize_identifier()
            elif char == '/':
                # Check / before OPERATOR_CHARS to tokenize as SLASH, not OPERATOR
                self._tokenize_slash()
            elif char == '.':
                # Check . before OPERATOR_CHARS
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
                # Unknown character, skip
                self.position += 1

        self.tokens.append(Token(TokenType.EOF, '', self.position))
        return self.tokens

    def _add_simple_token(self, token_type: TokenType, value: str, advance: int):
        """Add a simple single-character token and advance position."""
        self.tokens.append(Token(token_type, value, self.position))
        self.position += advance

    def _skip_whitespace(self) -> bool:
        """Skip whitespace characters. Returns True if whitespace was found."""
        if self.position < len(self.expression) and self.expression[self.position].isspace():
            while self.position < len(self.expression) and self.expression[self.position].isspace():
                self.position += 1
            return True
        return False

    def _is_next_digit(self) -> bool:
        """Check if next character is a digit."""
        return (self.position + 1 < len(self.expression) and
                self.expression[self.position + 1].isdigit())

    def _peek_char(self, offset: int = 0) -> Optional[str]:
        """Peek at character at position + offset."""
        pos = self.position + offset
        return self.expression[pos] if 0 <= pos < len(self.expression) else None

    def _tokenize_string(self):
        """Tokenize a string literal."""
        quote_char = self.expression[self.position]
        start_pos = self.position
        self.position += 1  # Skip opening quote

        value = []
        while self.position < len(self.expression):
            char = self.expression[self.position]
            if char == quote_char:
                # Check if it's escaped
                if self.position > 0 and self.expression[self.position - 1] == '\\':
                    value[-1] = quote_char  # Replace escape with quote
                else:
                    # End of string
                    self.position += 1
                    break
            value.append(char)
            self.position += 1

        self.tokens.append(Token(TokenType.STRING, ''.join(value), start_pos))

    def _tokenize_number(self):
        """Tokenize a number literal."""
        start_pos = self.position
        value = []

        # Optional minus sign
        if self.expression[self.position] == '-':
            value.append('-')
            self.position += 1

        # Integer part
        while self.position < len(self.expression) and self.expression[self.position].isdigit():
            value.append(self.expression[self.position])
            self.position += 1

        # Decimal point and fractional part
        if (self._peek_char() == '.' and self._peek_char(1) and 
            self._peek_char(1).isdigit()):
            value.append('.')
            self.position += 1
            while self.position < len(self.expression) and self.expression[self.position].isdigit():
                value.append(self.expression[self.position])
                self.position += 1

        self.tokens.append(Token(TokenType.NUMBER, ''.join(value), start_pos))

    def _tokenize_identifier(self):
        """Tokenize an identifier or keyword."""
        start_pos = self.position
        value = []

        while self.position < len(self.expression):
            char = self.expression[self.position]
            if char.isalnum() or char in ('_', '-'):
                value.append(char)
                self.position += 1
            else:
                break

        identifier = ''.join(value)
        self.tokens.append(Token(TokenType.IDENTIFIER, identifier, start_pos))

    def _tokenize_operator(self):
        """Tokenize an operator."""
        start_pos = self.position
        remaining = self.expression[self.position:]

        # Try two-character operators first
        for op in self.OPERATORS:
            if remaining.startswith(op):
                self.tokens.append(Token(TokenType.OPERATOR, op, start_pos))
                self.position += len(op)
                return

        # Single character operator
        char = self.expression[self.position]
        self.tokens.append(Token(TokenType.OPERATOR, char, start_pos))
        self.position += 1

    def _tokenize_dot(self):
        """Tokenize a dot (could be . or ..)."""
        start_pos = self.position

        # Check for .. (parent path)
        if self._peek_char(1) == '.':
            self.tokens.append(Token(TokenType.DOTDOT, '..', start_pos))
            self.position += 2
        else:
            # Single dot
            self.tokens.append(Token(TokenType.DOT, '.', start_pos))
            self.position += 1

    def _tokenize_slash(self):
        """Tokenize a slash."""
        start_pos = self.position

        # Check for // (descendant-or-self)
        if self._peek_char(1) == '/':
            self.tokens.append(Token(TokenType.OPERATOR, '//', start_pos))
            self.position += 2
        else:
            # Single slash
            self.tokens.append(Token(TokenType.SLASH, '/', start_pos))
            self.position += 1


class XPathParser:
    """Parser for XPath expressions."""

    def __init__(self, tokens: List[Token], expression: str = None):
        self.tokens = tokens
        self.position = 0
        self.expression = expression or ""

    def _get_expression(self) -> str:
        """Get the original expression if available."""
        return self.expression

    def parse(self) -> XPathNode:
        """Parse tokens into an AST."""
        if not self.tokens or self.tokens[0].type == TokenType.EOF:
            raise XPathSyntaxError("Empty expression")

        node = self._parse_expression()

        token = self._current_token()
        if token.type != TokenType.EOF:
            raise XPathSyntaxError(
                f"Unexpected token: {token.type.name} ({token.value!r})",
                position=token.position,
                expression=self._get_expression()
            )

        return node

    def _current_token(self) -> Token:
        """Get current token."""
        if self.position < len(self.tokens):
            return self.tokens[self.position]
        return Token(TokenType.EOF, '', 0)

    def _consume(self, expected_type: Optional[TokenType] = None, 
                 expected_value: Optional[str] = None) -> Token:
        """Consume current token with optional validation."""
        token = self._current_token()
        
        if expected_type and token.type != expected_type:
            raise XPathSyntaxError(
                f"Expected {expected_type.name}, got {token.type.name} ({token.value!r})",
                position=token.position,
                expression=self._get_expression()
            )
        if expected_value and token.value != expected_value:
            raise XPathSyntaxError(
                f"Expected {expected_value!r}, got {token.value!r}",
                position=token.position,
                expression=self._get_expression()
            )
        
        self.position += 1
        return token

    def _is_keyword(self, keyword: str) -> bool:
        """Check if current token is a specific keyword (case-insensitive)."""
        token = self._current_token()
        return (token.type == TokenType.IDENTIFIER and 
                token.value.lower() == keyword.lower())

    def _parse_expression(self) -> XPathNode:
        """Parse an expression (lowest precedence)."""
        return self._parse_logical_or()

    def _parse_logical_or(self) -> XPathNode:
        """Parse logical OR (lowest precedence)."""
        left = self._parse_logical_and()

        while self._is_keyword('or'):
            self._consume()  # Consume 'or'
            right = self._parse_logical_and()
            left = BinaryOpNode('or', left, right)

        return left

    def _parse_logical_and(self) -> XPathNode:
        """Parse logical AND."""
        left = self._parse_comparison()

        while self._is_keyword('and'):
            self._consume()  # Consume 'and'
            right = self._parse_comparison()
            left = BinaryOpNode('and', left, right)

        return left

    def _parse_comparison(self) -> XPathNode:
        """Parse comparison operators."""
        left = self._parse_additive()

        token = self._current_token()
        if token.type == TokenType.OPERATOR and token.value in COMPARISON_OPS:
            op = self._consume().value
            right = self._parse_additive()
            return BinaryOpNode(op, left, right)

        return left

    def _parse_additive(self) -> XPathNode:
        """Parse additive operators (+ and -)."""
        left = self._parse_multiplicative()

        while True:
            token = self._current_token()
            if token.type == TokenType.OPERATOR and token.value in ADDITIVE_OPS:
                op = self._consume().value
                right = self._parse_multiplicative()
                left = BinaryOpNode(op, left, right)
            else:
                break

        return left

    def _parse_multiplicative(self) -> XPathNode:
        """Parse multiplicative operators (* and /)."""
        left = self._parse_unary()

        while True:
            token = self._current_token()
            # Check for / operator (can be SLASH or OPERATOR token type)
            is_slash = (token.type == TokenType.SLASH) or (token.type == TokenType.OPERATOR and token.value == '/')
            
            if not is_slash:
                # Not a slash, check for other multiplicative ops
                if token.type == TokenType.OPERATOR and token.value == '*':
                    op = self._consume().value
                    right = self._parse_unary()
                    left = BinaryOpNode(op, left, right)
                else:
                    break
                continue

            # Handle / operator - could be division or path navigation
            if isinstance(left, PathNode):
                # Path continuation - merge paths
                self._consume()
                right_path = self._parse_path(is_absolute=False)
                left.steps.extend(right_path.steps)
                # Only overwrite predicate if right has one
                if right_path.predicate is not None:
                    left.predicate = right_path.predicate
            elif isinstance(left, FunctionCallNode) and left.name == 'deref':
                # deref() followed by / is path navigation
                self._consume()
                right_path = self._parse_path(is_absolute=False)
                left = BinaryOpNode('/', left, right_path)
            else:
                # Regular division
                op = self._consume().value
                right = self._parse_unary()
                left = BinaryOpNode(op, left, right)

        return left

    def _parse_unary(self) -> XPathNode:
        """Parse unary operators and function calls."""
        token = self._current_token()

        # Unary minus
        if token.type == TokenType.OPERATOR and token.value == '-':
            self._consume()
            return UnaryOpNode('-', self._parse_unary())

        # Unary plus (no-op)
        if token.type == TokenType.OPERATOR and token.value == '+':
            self._consume()
            return self._parse_unary()  # Unary + is a no-op

        # Unary not
        if self._is_keyword('not'):
            self._consume()
            self._consume(TokenType.PAREN_OPEN)
            operand = self._parse_expression()
            self._consume(TokenType.PAREN_CLOSE)
            return UnaryOpNode('not', operand)

        return self._parse_primary()

    def _parse_boolean_literal(self, value: bool) -> XPathNode:
        """Parse a boolean literal (true/false), handling function call syntax."""
        self._consume()
        # Check if it's a function call
        if self._current_token().type == TokenType.PAREN_OPEN:
            self._consume(TokenType.PAREN_OPEN)
            self._consume(TokenType.PAREN_CLOSE)
            return FunctionCallNode(str(value).lower(), [])
        return LiteralNode(value)

    def _parse_number_literal(self) -> XPathNode:
        """Parse a number literal."""
        value = self._consume().value
        try:
            return LiteralNode(float(value) if '.' in value else int(value))
        except ValueError:
            token = self._current_token()
            raise XPathSyntaxError(
                f"Invalid number: {value}",
                position=token.position,
                expression=self._get_expression()
            )

    def _parse_function_call(self) -> XPathNode:
        """Parse a function call."""
        name = self._consume().value
        self._consume(TokenType.PAREN_OPEN)
        args = []
        if self._current_token().type != TokenType.PAREN_CLOSE:
            args = self._parse_argument_list()
        self._consume(TokenType.PAREN_CLOSE)
        return FunctionCallNode(name, args)

    def _parse_primary(self) -> XPathNode:
        """Parse primary expressions."""
        token = self._current_token()

        # String literals
        if token.type == TokenType.STRING:
            value = self._consume().value
            return LiteralNode(value)

        # Number literals
        if token.type == TokenType.NUMBER:
            return self._parse_number_literal()

        # Boolean literals
        if token.type == TokenType.IDENTIFIER:
            if self._is_keyword('true'):
                return self._parse_boolean_literal(True)
            if self._is_keyword('false'):
                return self._parse_boolean_literal(False)

        # Current node
        if token.type == TokenType.DOT:
            self._consume()
            # Check if it's current() function
            if self._current_token().type == TokenType.PAREN_OPEN:
                self._consume(TokenType.PAREN_OPEN)
                self._consume(TokenType.PAREN_CLOSE)
            return CurrentNode(is_current_function=False)

        # Parent path (..) - treat as path expression
        if token.type == TokenType.DOTDOT:
            return self._parse_path(is_absolute=False)

        # Function calls - check if identifier is followed by (
        if token.type == TokenType.IDENTIFIER:
            # Peek ahead to see if it's a function call
            if (self.position + 1 < len(self.tokens) and
                self.tokens[self.position + 1].type == TokenType.PAREN_OPEN):
                return self._parse_function_call()
            # Otherwise, it's a path (field name)
            return self._parse_path(is_absolute=False)

        # Path expressions starting with slash
        if token.type == TokenType.SLASH:
            self._consume()
            return self._parse_path(is_absolute=True)

        # Parenthesized expressions
        if token.type == TokenType.PAREN_OPEN:
            self._consume(TokenType.PAREN_OPEN)
            expr = self._parse_expression()
            self._consume(TokenType.PAREN_CLOSE)
            return expr

        raise ValueError(f"Unexpected token: {token} at position {token.position}")

    def _parse_argument_list(self) -> List[XPathNode]:
        """Parse function argument list."""
        args = [self._parse_expression()]

        while self._current_token().type == TokenType.COMMA:
            self._consume(TokenType.COMMA)
            args.append(self._parse_expression())

        return args

    def _parse_path(self, is_absolute: bool = False) -> XPathNode:
        """Parse a path expression.
        
        Args:
            is_absolute: Whether this is an absolute path (starts with /)
        """
        steps = []

        # Parse path steps
        while True:
            token = self._current_token()

            # Parent step (..)
            if token.type == TokenType.DOTDOT:
                steps.append(self._consume().value)
                # Check for slash after ..
                if self._current_token().type == TokenType.SLASH:
                    self._consume()
                # If no slash, we're done with this path
                elif self._current_token().type not in (TokenType.SLASH, TokenType.BRACKET_OPEN, TokenType.EOF):
                    # Next token is not part of path, stop
                    break
            # Current step (.)
            elif token.type == TokenType.DOT:
                self._consume()
                steps.append('.')
                # Check for slash after .
                if self._current_token().type == TokenType.SLASH:
                    self._consume()
                else:
                    break
            # Identifier step
            elif token.type == TokenType.IDENTIFIER:
                steps.append(self._consume().value)
                # Check for slash after identifier
                if self._current_token().type == TokenType.SLASH:
                    self._consume()
                else:
                    break
            else:
                break

        # Create path node
        path_node = PathNode(steps, is_absolute)

        # Check for predicate
        if self._current_token().type == TokenType.BRACKET_OPEN:
            self._consume(TokenType.BRACKET_OPEN)
            path_node.predicate = self._parse_expression()
            self._consume(TokenType.BRACKET_CLOSE)

        return path_node
