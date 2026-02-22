"""
Predicate evaluation logic for XPath expressions.
"""

from typing import Any, List

from .ast import BinaryOpNode, LiteralNode, XPathNode
from .utils import compare_equal
from .context import Context


class PredicateEvaluator:
    """Handles predicate evaluation in XPath expressions."""
    
    def __init__(self, evaluator: Any):
        """Initialize predicate evaluator with reference to main evaluator.
        
        Args:
            evaluator: The main XPathEvaluator instance
        """
        self.evaluator = evaluator
    
    def apply_predicate(self, items: List[Any], predicate: XPathNode, context: Context) -> Any:
        """Apply a predicate filter to a list of items.
        
        Args:
            items: List of items to filter
            predicate: AST node representing the predicate expression
            context: Context for evaluation
        
        Returns:
            For simple index predicates like [1], returns the element directly.
            For other predicates, returns a filtered list.
        """
        # Handle index access [1] - check if predicate is a numeric literal
        if isinstance(predicate, LiteralNode) and isinstance(predicate.value, (int, float)):
            idx = int(predicate.value) - 1  # XPath is 1-indexed
            items_len = len(items)
            if 0 <= idx < items_len:
                return items[idx]  # Return element directly, not wrapped in list
            return None

        # Handle comparison expressions like [name = current()] or [type != 'array']
        if isinstance(predicate, BinaryOpNode) and predicate.operator in ('=', '!='):
            op = predicate.operator
            is_equal_op = (op == '=')
            
            # Optimized: initialize empty list (Python lists grow efficiently)
            filtered = []
            
            for item in items:
                # Create new context for evaluation, preserving original values for current()
                new_context = context.for_item(item)

                # Evaluate left and right operands
                left_val = predicate.left.evaluate(self.evaluator, new_context)
                right_val = predicate.right.evaluate(self.evaluator, new_context)

                # Single comparison check
                if compare_equal(left_val, right_val) == is_equal_op:
                    filtered.append(item)
            
            return filtered
        
        # For other predicate expressions (not simple comparisons), return items unchanged
        # This matches the original behavior where non-comparison predicates were ignored
        return items
