"""
XPath expression tokenizer and parser.
"""

from typing import List, Optional

from .ast import (
    Token, TokenType, XPathNode, LiteralNode, PathNode, CurrentNode,
    FunctionCallNode, BinaryOpNode, UnaryOpNode
)
from ..errors import XPathSyntaxError


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
            # Skip whitespace
            if self._skip_whitespace():
                continue

            # Check for end of input
            if self.position >= len(self.expression):
                break

            char = self.expression[self.position]

            # String literals
            if char in ('"', "'"):
                self._tokenize_string()
            # Numbers
            elif char.isdigit() or (char == '-' and self._is_next_digit()):
                self._tokenize_number()
            # Identifiers and keywords
            elif char.isalpha() or char == '_':
                self._tokenize_identifier()
            # Operators
            elif char in ('=', '<', '>', '!', '+', '-', '*', '/'):
                self._tokenize_operator()
            # Parentheses
            elif char == '(':
                self.tokens.append(Token(TokenType.PAREN_OPEN, '(', self.position))
                self.position += 1
            elif char == ')':
                self.tokens.append(Token(TokenType.PAREN_CLOSE, ')', self.position))
                self.position += 1
            # Brackets
            elif char == '[':
                self.tokens.append(Token(TokenType.BRACKET_OPEN, '[', self.position))
                self.position += 1
            elif char == ']':
                self.tokens.append(Token(TokenType.BRACKET_CLOSE, ']', self.position))
                self.position += 1
            # Dot
            elif char == '.':
                self._tokenize_dot()
            # Slash
            elif char == '/':
                self._tokenize_slash()
            # Comma
            elif char == ',':
                self.tokens.append(Token(TokenType.COMMA, ',', self.position))
                self.position += 1
            else:
                # Unknown character, skip
                self.position += 1

        self.tokens.append(Token(TokenType.EOF, '', self.position))
        return self.tokens

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
        if (self.position < len(self.expression) and
            self.expression[self.position] == '.' and
            self.position + 1 < len(self.expression) and
            self.expression[self.position + 1].isdigit()):
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
            if char.isalnum() or char == '_' or char == '-':
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
        """Tokenize a dot (could be . or .. or part of a number)."""
        start_pos = self.position

        # Check for .. (parent path)
        if (self.position + 1 < len(self.expression) and
            self.expression[self.position + 1] == '.'):
            self.tokens.append(Token(TokenType.IDENTIFIER, '..', start_pos))
            self.position += 2
        else:
            # Single dot
            self.tokens.append(Token(TokenType.DOT, '.', start_pos))
            self.position += 1

    def _tokenize_slash(self):
        """Tokenize a slash."""
        start_pos = self.position

        # Check for // (descendant-or-self)
        if (self.position + 1 < len(self.expression) and
            self.expression[self.position + 1] == '/'):
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

        if self._current_token().type != TokenType.EOF:
            token = self._current_token()
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

    def _consume(self, expected_type: Optional[TokenType] = None, expected_value: Optional[str] = None) -> Token:
        """Consume current token."""
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

    def _parse_expression(self) -> XPathNode:
        """Parse an expression (lowest precedence)."""
        return self._parse_logical_or()

    def _parse_logical_or(self) -> XPathNode:
        """Parse logical OR (lowest precedence)."""
        left = self._parse_logical_and()

        while (self._current_token().type == TokenType.IDENTIFIER and
               self._current_token().value.lower() == 'or'):
            self._consume()  # Consume 'or'
            right = self._parse_logical_and()
            left = BinaryOpNode('or', left, right)

        return left

    def _parse_logical_and(self) -> XPathNode:
        """Parse logical AND."""
        left = self._parse_comparison()

        while (self._current_token().type == TokenType.IDENTIFIER and
               self._current_token().value.lower() == 'and'):
            self._consume()  # Consume 'and'
            right = self._parse_comparison()
            left = BinaryOpNode('and', left, right)

        return left

    def _parse_comparison(self) -> XPathNode:
        """Parse comparison operators."""
        left = self._parse_additive()

        token = self._current_token()
        if token.type == TokenType.OPERATOR and token.value in ('=', '!=', '<', '>', '<=', '>='):
            op = self._consume().value
            right = self._parse_additive()
            return BinaryOpNode(op, left, right)

        return left

    def _parse_additive(self) -> XPathNode:
        """Parse additive operators (+ and -)."""
        left = self._parse_multiplicative()

        while True:
            token = self._current_token()
            if token.type == TokenType.OPERATOR and token.value in ('+', '-'):
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
            # Don't treat / as division if left is a path node (it's a path separator)
            if (token.type == TokenType.OPERATOR and token.value == '/' and
                isinstance(left, PathNode)):
                # This is a path continuation, not division
                # Parse the rest as a path and merge
                self._consume()  # Consume the /
                # Continue parsing path steps
                right_path = self._parse_path()
                # Merge paths
                left.steps.extend(right_path.steps)
                left.predicate = right_path.predicate
            # Also handle / after function calls (like deref()) as path navigation
            elif (token.type == TokenType.OPERATOR and token.value == '/' and
                  isinstance(left, FunctionCallNode) and left.name == 'deref'):
                # deref() followed by / is path navigation, not division
                # Create a special node that evaluates deref() then navigates the path
                self._consume()  # Consume the /
                right_path = self._parse_path()
                # Create a BinaryOpNode with '/' but mark it as path navigation
                # The evaluator will handle this specially
                left = BinaryOpNode('/', left, right_path)
            elif token.type == TokenType.OPERATOR and token.value in ('*', '/'):
                op = self._consume().value
                right = self._parse_unary()
                left = BinaryOpNode(op, left, right)
            else:
                break

        return left

    def _parse_unary(self) -> XPathNode:
        """Parse unary operators and function calls."""
        token = self._current_token()

        # Unary minus
        if token.type == TokenType.OPERATOR and token.value == '-':
            self._consume()
            operand = self._parse_unary()
            return UnaryOpNode('-', operand)

        # Unary plus (explicit positive, usually no-op but we support it)
        if token.type == TokenType.OPERATOR and token.value == '+':
            self._consume()
            operand = self._parse_unary()
            return operand  # Unary + is a no-op, just return the operand

        # Unary not
        if token.type == TokenType.IDENTIFIER and token.value.lower() == 'not':
            self._consume()
            self._consume(TokenType.PAREN_OPEN)
            operand = self._parse_expression()
            self._consume(TokenType.PAREN_CLOSE)
            return UnaryOpNode('not', operand)

        return self._parse_primary()

    def _parse_primary(self) -> XPathNode:
        """Parse primary expressions."""
        token = self._current_token()

        # Literals
        if token.type == TokenType.STRING:
            value = self._consume().value
            return LiteralNode(value)

        if token.type == TokenType.NUMBER:
            value = self._consume().value
            try:
                if '.' in value:
                    return LiteralNode(float(value))
                return LiteralNode(int(value))
            except ValueError:
                token = self._current_token()
                raise XPathSyntaxError(
                    f"Invalid number: {value}",
                    position=token.position,
                    expression=self._get_expression()
                )

        # Boolean literals
        if token.type == TokenType.IDENTIFIER:
            if token.value.lower() == 'true':
                self._consume()
                # Check if it's a function call
                if self._current_token().type == TokenType.PAREN_OPEN:
                    self._consume(TokenType.PAREN_OPEN)
                    self._consume(TokenType.PAREN_CLOSE)
                    return FunctionCallNode('true', [])
                return LiteralNode(True)

            if token.value.lower() == 'false':
                self._consume()
                # Check if it's a function call
                if self._current_token().type == TokenType.PAREN_OPEN:
                    self._consume(TokenType.PAREN_OPEN)
                    self._consume(TokenType.PAREN_CLOSE)
                    return FunctionCallNode('false', [])
                return LiteralNode(False)

        # Current node
        if token.type == TokenType.DOT:
            self._consume()
            # Check if it's current() function
            if self._current_token().type == TokenType.PAREN_OPEN:
                self._consume(TokenType.PAREN_OPEN)
                self._consume(TokenType.PAREN_CLOSE)
                return CurrentNode()
            return CurrentNode()

        # Function calls - check if identifier is followed by (
        if token.type == TokenType.IDENTIFIER:
            # Peek ahead to see if it's a function call
            if (self.position + 1 < len(self.tokens) and
                self.tokens[self.position + 1].type == TokenType.PAREN_OPEN):
                name = self._consume().value
                self._consume(TokenType.PAREN_OPEN)
                args = []
                if self._current_token().type != TokenType.PAREN_CLOSE:
                    args = self._parse_argument_list()
                self._consume(TokenType.PAREN_CLOSE)
                return FunctionCallNode(name, args)
            # Otherwise, it's a path (could be .. or field name)
            return self._parse_path()

        # Path expressions starting with slash
        if token.type == TokenType.SLASH:
            return self._parse_path()

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

    def _parse_path(self) -> XPathNode:
        """Parse a path expression."""
        steps = []
        is_absolute = False

        # Check for absolute path
        if self._current_token().type == TokenType.SLASH:
            self._consume()
            is_absolute = True

        # Parse path steps
        while True:
            token = self._current_token()

            # Parent step (..)
            if token.type == TokenType.IDENTIFIER and token.value == '..':
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
