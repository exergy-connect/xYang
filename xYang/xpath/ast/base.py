"""
Base AST node class.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..evaluator import XPathEvaluator
    from ..context import Context
    from . import JsonValue


class XPathNode:
    """Base class for XPath AST nodes."""

    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Evaluate this node.
        
        Args:
            evaluator: XPath evaluator instance
            context: Context for evaluation
            
        Returns:
            The evaluated value (JSON-like structure or primitive)
        """
        raise NotImplementedError
