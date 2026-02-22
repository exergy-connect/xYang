"""
Current node (.) or current() function.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import XPathNode
    from ..evaluator import XPathEvaluator
    from ..context import Context
    from . import JsonValue

from .base import XPathNode


class CurrentNode(XPathNode):
    """Current node (.) or current() function."""
    
    def __init__(self, is_current_function: bool = False):
        """Initialize current node.
        
        Args:
            is_current_function: True if this is current() function, False if it's . (current node)
        """
        self.is_current_function = is_current_function

    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        # pylint: disable=protected-access
        if self.is_current_function:
            # current() always refers to original context
            # Pass evaluator for per-evaluator caching (thread safety)
            return context.current(evaluator)
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
            # Pass evaluator for per-evaluator caching (thread safety)
            return context.current(evaluator)

    def __repr__(self):
        return "current()" if self.is_current_function else "."
