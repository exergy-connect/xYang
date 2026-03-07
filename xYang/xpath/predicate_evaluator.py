"""
Predicate evaluation logic for XPath expressions.
"""

from typing import Any, List

from .ast import BinaryOpNode, LiteralNode, XPathNode
from .utils import compare_equal, yang_bool
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
        # Handle index access [1] or [0] - check if predicate is a numeric literal
        if isinstance(predicate, LiteralNode) and isinstance(predicate.value, (int, float)):
            pred_value = int(predicate.value)
            # Handle [0] as 0-based indexing for convenience, [1] and above as 1-based (XPath standard)
            if pred_value == 0:
                idx = 0
            else:
                idx = pred_value - 1  # XPath is 1-indexed
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

        # For any other predicate (e.g. count(...) > 7), evaluate per item and filter by truthiness
        # so that expressions like entities[count(fields[type != 'array']) > 7] work in Phase 1 must checks
        filtered = []
        for item in items:
            new_context = context.for_item(item)
            try:
                pred_result = predicate.evaluate(self.evaluator, new_context)
                if yang_bool(pred_result):
                    filtered.append(item)
            except Exception:
                pass  # Excluded when predicate raises
        return filtered
