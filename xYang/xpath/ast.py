"""
AST nodes for XPath expressions.
"""

from enum import Enum
from typing import Any, List, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from .evaluator import XPathEvaluator
    from .context import Context

# Type alias for JSON-like values that XPath can evaluate to
# Note: This is a recursive type, so we use Any for nested structures
JsonValue = Union[dict[str, Any], list[Any], str, int, float, bool, None]


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


class XPathNode:
    """Base class for XPath AST nodes."""

    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> JsonValue:
        """Evaluate this node.
        
        Args:
            evaluator: XPath evaluator instance
            context: Context for evaluation
            
        Returns:
            The evaluated value (JSON-like structure or primitive)
        """
        raise NotImplementedError


class LiteralNode(XPathNode):
    """Literal value node (string, number, boolean)."""

    def __init__(self, value: Union[str, int, float, bool]):
        self.value = value

    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> JsonValue:
        return self.value

    def __repr__(self):
        return f"Literal({self.value!r})"


class PathSegment:
    """A single segment in a path expression.
    
    Each segment represents one step in the path (e.g., 'entities', 'fields')
    and can optionally have a predicate (e.g., [name = 'value']).
    """
    
    def __init__(self, step: str, predicate: Optional['XPathNode'] = None):
        """Initialize a path segment.
        
        Args:
            step: The step name (e.g., 'entities', '..', '.')
            predicate: Optional predicate expression for this step
        """
        self.step = step
        self.predicate = predicate
    
    def __repr__(self):
        pred_str = f"[{self.predicate}]" if self.predicate else ""
        return f"{self.step}{pred_str}"


class PathNode(XPathNode):
    """Path navigation node."""

    def __init__(self, segments: List[PathSegment], is_absolute: bool = False):
        """Initialize a path node.
        
        Args:
            segments: List of path segments, each with an optional predicate
            is_absolute: True if path starts with /
        """
        self.segments = segments  # List of PathSegment objects
        self.is_absolute = is_absolute  # True if starts with /

    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> JsonValue:
        # pylint: disable=protected-access
        return evaluator._evaluate_path_node(self, context)

    def __repr__(self):
        prefix = "/" if self.is_absolute else ""
        segments_str = '/'.join(repr(seg) for seg in self.segments)
        return f"Path({prefix}{segments_str})"


class CurrentNode(XPathNode):
    """Current node (.) or current() function."""
    
    def __init__(self, is_current_function: bool = False):
        """Initialize current node.
        
        Args:
            is_current_function: True if this is current() function, False if it's . (current node)
        """
        self.is_current_function = is_current_function

    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> JsonValue:
        # pylint: disable=protected-access
        if self.is_current_function:
            # current() always refers to original context
            return context.current()
        else:
            # . refers to current context node/value
            # If data is a primitive value, return it directly
            if isinstance(context.data, (str, int, float, bool)):
                return context.data
            # If data is a dict and context_path is empty, check if it's a wrapped value
            if isinstance(context.data, dict) and not context.context_path:
                # If it's a wrapped value (from predicate evaluator), return the value
                if 'value' in context.data and len(context.data) == 1:
                    return context.data['value']
                # Otherwise return the dict itself
                return context.data
            # Otherwise, get value from current context path
            if context.context_path:
                return evaluator.path_evaluator.get_path_value(context.context_path, context)
            # Fallback to current() if no context
            return context.current()

    def __repr__(self):
        return "current()" if self.is_current_function else "."


class FunctionCallNode(XPathNode):
    """Function call node."""

    def __init__(self, name: str, args: List[XPathNode]):
        self.name = name
        self.args = args

    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> JsonValue:
        # pylint: disable=protected-access
        return evaluator._evaluate_function_node(self, context)

    def __repr__(self):
        args_str = ", ".join(repr(arg) for arg in self.args)
        return f"Function({self.name}({args_str}))"


class BinaryOpNode(XPathNode):
    """Binary operator node."""

    def __init__(self, operator: str, left: XPathNode, right: XPathNode):
        self.operator = operator
        self.left = left
        self.right = right

    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> JsonValue:
        # pylint: disable=protected-access
        return evaluator._evaluate_binary_op(self, context)

    def __repr__(self):
        return f"BinaryOp({self.operator}, {self.left}, {self.right})"


class UnaryOpNode(XPathNode):
    """Unary operator node (e.g., not())."""

    def __init__(self, operator: str, operand: XPathNode):
        self.operator = operator
        self.operand = operand

    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> JsonValue:
        # pylint: disable=protected-access
        return evaluator._evaluate_unary_op(self, context)

    def __repr__(self):
        return f"UnaryOp({self.operator}, {self.operand})"
