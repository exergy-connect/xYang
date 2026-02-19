"""
XPath validator for checking supported constructs at parse time.

This module validates XPath expressions against a whitelist of supported
constructs, raising UnsupportedXPathError immediately if unsupported
features are detected.
"""

from typing import Set

from .ast import (
    XPathNode, LiteralNode, PathNode, CurrentNode,
    FunctionCallNode, BinaryOpNode, UnaryOpNode
)
from ..errors import UnsupportedXPathError
from .parser import XPathTokenizer, XPathParser


# Whitelist of supported XPath functions
SUPPORTED_FUNCTIONS: Set[str] = {
    'string-length',
    'translate',
    'count',
    'deref',
    'current',
    'not',
    'true',
    'false',
    'bool',
    'number',
}

# Whitelist of supported binary operators
SUPPORTED_BINARY_OPS: Set[str] = {
    '=', '!=', '<=', '>=', '<', '>',  # Comparison operators
    '+', '-', '*', '/',  # Arithmetic operators
    'or', 'and',  # Logical operators
}

# Whitelist of supported unary operators
SUPPORTED_UNARY_OPS: Set[str] = {
    'not',  # Logical not
    '-',  # Unary minus
}


class XPathValidator:
    """Validates XPath expressions against a whitelist of supported constructs."""
    
    def __init__(self):
        """Initialize the validator."""
        pass
    
    def validate(self, expression: str) -> XPathNode:
        """
        Validate an XPath expression against the whitelist and return the parsed AST.
        
        Args:
            expression: The XPath expression to validate
            
        Returns:
            The parsed XPath AST node
            
        Raises:
            UnsupportedXPathError: If the expression contains unsupported constructs
            XPathSyntaxError: If the expression has syntax errors
        """
        # Parse the expression to get an AST
        try:
            tokenizer = XPathTokenizer(expression)
            tokens = tokenizer.tokenize()
            parser = XPathParser(tokens, expression=expression)
            ast = parser.parse()
        except Exception as e:
            # Re-raise parsing errors as-is (they're already XPathSyntaxError)
            raise
        
        # Walk the AST and validate all nodes
        self._validate_node(ast, expression)
        
        # Return the validated AST for reuse
        return ast
    
    def _validate_node(self, node: XPathNode, expression: str) -> None:
        """
        Recursively validate an AST node and its children.
        
        Args:
            node: The AST node to validate
            expression: The original expression (for error messages)
            
        Raises:
            UnsupportedXPathError: If the node contains unsupported constructs
        """
        # Validate based on node type
        if isinstance(node, LiteralNode):
            # Literals are always supported
            pass
        elif isinstance(node, PathNode):
            # Path nodes are supported
            # Validate predicate if present
            if node.predicate is not None:
                self._validate_node(node.predicate, expression)
        elif isinstance(node, CurrentNode):
            # Current node is supported
            pass
        elif isinstance(node, FunctionCallNode):
            # Validate function name
            func_name = node.name.lower()
            if func_name not in SUPPORTED_FUNCTIONS:
                raise UnsupportedXPathError(
                    f"Unsupported XPath function: {node.name}",
                    expression=expression,
                    construct=f"function:{node.name}"
                )
            # Validate function arguments recursively
            for arg in node.args:
                self._validate_node(arg, expression)
        elif isinstance(node, BinaryOpNode):
            # Validate operator
            op = node.operator.lower()
            if op not in SUPPORTED_BINARY_OPS:
                raise UnsupportedXPathError(
                    f"Unsupported XPath binary operator: {node.operator}",
                    expression=expression,
                    construct=f"operator:{node.operator}"
                )
            # Validate left and right operands
            self._validate_node(node.left, expression)
            self._validate_node(node.right, expression)
        elif isinstance(node, UnaryOpNode):
            # Validate operator
            op = node.operator.lower()
            if op not in SUPPORTED_UNARY_OPS:
                raise UnsupportedXPathError(
                    f"Unsupported XPath unary operator: {node.operator}",
                    expression=expression,
                    construct=f"operator:{node.operator}"
                )
            # Validate operand
            self._validate_node(node.operand, expression)
        else:
            # Unknown node type - this shouldn't happen, but be safe
            raise UnsupportedXPathError(
                f"Unknown XPath node type: {type(node).__name__}",
                expression=expression,
                construct=f"node_type:{type(node).__name__}"
            )
