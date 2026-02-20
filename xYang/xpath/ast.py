"""
AST nodes for XPath expressions.
"""

from enum import Enum
from typing import Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .evaluator import XPathEvaluator


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


class XPathNode:
    """Base class for XPath AST nodes."""

    def evaluate(self, evaluator: Any) -> Any:
        """Evaluate this node."""
        raise NotImplementedError


class LiteralNode(XPathNode):
    """Literal value node (string, number, boolean)."""

    def __init__(self, value: Any):
        self.value = value

    def evaluate(self, evaluator: 'XPathEvaluator') -> Any:
        return self.value

    def __repr__(self):
        return f"Literal({self.value!r})"


class PathNode(XPathNode):
    """Path navigation node."""

    def __init__(self, steps: List[str], is_absolute: bool = False):
        self.steps = steps  # List of path steps (e.g., ['..', '..', 'field'])
        self.is_absolute = is_absolute  # True if starts with /
        self.predicate: Optional[XPathNode] = None  # Optional predicate filter

    def evaluate(self, evaluator: 'XPathEvaluator') -> Any:
        # pylint: disable=protected-access
        return evaluator._evaluate_path_node(self)

    def __repr__(self):
        pred_str = f"[{self.predicate}]" if self.predicate else ""
        prefix = "/" if self.is_absolute else ""
        return f"Path({prefix}{'/'.join(self.steps)}{pred_str})"


class CurrentNode(XPathNode):
    """Current node (.) or current() function."""
    
    def __init__(self, is_current_function: bool = False):
        """Initialize current node.
        
        Args:
            is_current_function: True if this is current() function, False if it's . (current node)
        """
        self.is_current_function = is_current_function

    def evaluate(self, evaluator: 'XPathEvaluator') -> Any:
        # pylint: disable=protected-access
        if self.is_current_function:
            # current() always refers to original context
            return evaluator._get_current_value()
        else:
            # . refers to current context node/value
            # If data is a primitive value, return it directly
            if isinstance(evaluator.data, (str, int, float, bool)):
                return evaluator.data
            # If data is a dict and context_path is empty, check if it's a wrapped value
            if isinstance(evaluator.data, dict) and not evaluator.context_path:
                # If it's a wrapped value (from predicate evaluator), return the value
                if 'value' in evaluator.data and len(evaluator.data) == 1:
                    return evaluator.data['value']
                # Otherwise return the dict itself
                return evaluator.data
            # Otherwise, get value from current context path
            if evaluator.context_path:
                return evaluator.path_evaluator.get_path_value(evaluator.context_path)
            # Fallback to current() if no context
            return evaluator._get_current_value()

    def __repr__(self):
        return "current()" if self.is_current_function else "."


class FunctionCallNode(XPathNode):
    """Function call node."""

    def __init__(self, name: str, args: List[XPathNode]):
        self.name = name
        self.args = args

    def evaluate(self, evaluator: 'XPathEvaluator') -> Any:
        # pylint: disable=protected-access
        return evaluator._evaluate_function_node(self)

    def __repr__(self):
        args_str = ", ".join(repr(arg) for arg in self.args)
        return f"Function({self.name}({args_str}))"


class BinaryOpNode(XPathNode):
    """Binary operator node."""

    def __init__(self, operator: str, left: XPathNode, right: XPathNode):
        self.operator = operator
        self.left = left
        self.right = right

    def evaluate(self, evaluator: 'XPathEvaluator') -> Any:
        # pylint: disable=protected-access
        return evaluator._evaluate_binary_op(self)

    def __repr__(self):
        return f"BinaryOp({self.operator}, {self.left}, {self.right})"


class UnaryOpNode(XPathNode):
    """Unary operator node (e.g., not())."""

    def __init__(self, operator: str, operand: XPathNode):
        self.operator = operator
        self.operand = operand

    def evaluate(self, evaluator: 'XPathEvaluator') -> Any:
        # pylint: disable=protected-access
        return evaluator._evaluate_unary_op(self)

    def __repr__(self):
        return f"UnaryOp({self.operator}, {self.operand})"
