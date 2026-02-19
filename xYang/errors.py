"""
Custom exception classes for YANG parsing and validation errors.
"""


class YangSyntaxError(SyntaxError):
    """YANG syntax error with line number and context."""

    def __init__(self, message: str, line_num: int = None, line: str = None,
                 context_lines: list = None, filename: str = None):
        """
        Initialize syntax error.

        Args:
            message: Error message
            line_num: Line number (1-indexed)
            line: The line content where error occurred
            context_lines: List of (line_num, line_content) tuples for context
            filename: Optional filename
        """
        self.message = message
        self.line_num = line_num
        self.line = line
        self.context_lines = context_lines or []
        self.filename = filename

        # Build detailed error message
        parts = []
        if filename:
            parts.append(f"{filename}:")
        if line_num:
            parts.append(f"{line_num}:")
        parts.append(message)
        base_msg = " ".join(parts)

        # Add context if available
        if self.context_lines:
            base_msg += "\n"
            for ctx_line_num, ctx_line in self.context_lines:
                marker = ">>> " if ctx_line_num == line_num else "    "
                base_msg += f"{marker}{ctx_line_num:4d} | {ctx_line}\n"
            if line_num and line:
                base_msg += f"     {' ' * (len(str(line_num)) + 3)}{'^' * max(1, len(line.strip()))}"

        super().__init__(base_msg)

    def __str__(self):
        return self.message


class XPathSyntaxError(ValueError):
    """XPath syntax error with position and context."""

    def __init__(self, message: str, position: int = None, expression: str = None,
                 context_before: int = 10, context_after: int = 10):
        """
        Initialize XPath syntax error.

        Args:
            message: Error message
            position: Character position in expression
            expression: The XPath expression
            context_before: Number of characters to show before error
            context_after: Number of characters to show after error
        """
        self.message = message
        self.position = position
        self.expression = expression

        # Build detailed error message
        if expression and position is not None:
            start = max(0, position - context_before)
            end = min(len(expression), position + context_after)
            context = expression[start:end]
            pointer_pos = position - start

            # Show context with pointer
            parts = [message]
            parts.append(f"\nExpression: {context}")
            parts.append(f"           {' ' * pointer_pos}^")
            if position < len(expression):
                parts.append(f"Position: {position} (character: {expression[position]!r})")
            else:
                parts.append(f"Position: {position} (end of expression)")

            super().__init__("\n".join(parts))
        else:
            super().__init__(message)

    def __str__(self):
        return self.message


class XPathEvaluationError(ValueError):
    """XPath evaluation error."""
    
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
    
    def __str__(self):
        return self.message


class UnsupportedXPathError(ValueError):
    """XPath expression contains unsupported constructs."""
    
    def __init__(self, message: str, expression: str = None, construct: str = None):
        """
        Initialize unsupported XPath error.
        
        Args:
            message: Error message
            expression: The XPath expression that contains unsupported constructs
            construct: The specific unsupported construct (optional)
        """
        self.message = message
        self.expression = expression
        self.construct = construct
        
        # Build detailed error message
        parts = [message]
        if construct:
            parts.append(f"Unsupported construct: {construct}")
        if expression:
            parts.append(f"Expression: {expression}")
        
        super().__init__("\n".join(parts))
    
    def __str__(self):
        return self.message


class YangCrossReferenceError(ValueError):
    """YANG validation error indicating cross-reference issues.
    
    This error is raised when validation fails due to cross-reference issues
    (e.g., entities or fields defined in other files). This is expected when
    validating individual files that reference entities in other files, and
    should not trigger individual file validation.
    
    Attributes:
        message: Error message
        errors: List of error strings
    """
    
    def __init__(self, message: str, errors: list[str] = None):
        """
        Initialize cross-reference error.
        
        Args:
            message: Error message
            errors: List of error strings (optional)
        """
        self.message = message
        self.errors = errors or []
        super().__init__(message)
    
    def __str__(self):
        return self.message
