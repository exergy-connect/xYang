"""
Comparison operations for XPath expressions.
"""

from typing import Any

from .utils import (
    compare_equal,
    compare_less_equal,
    compare_greater_equal,
    compare_less,
    compare_greater
)


class ComparisonEvaluator:
    """Handles comparison operations in XPath expressions."""
    
    def evaluate_comparison(self, op: str, left: Any, right: Any) -> bool:
        """Evaluate a comparison operation.
        
        Args:
            op: Comparison operator (=, !=, <=, >=, <, >)
            left: Left operand
            right: Right operand
            
        Returns:
            Boolean result of comparison
        """
        if op == '=':
            return compare_equal(left, right)
        if op == '!=':
            return not compare_equal(left, right)
        if op == '<=':
            return compare_less_equal(left, right)
        if op == '>=':
            return compare_greater_equal(left, right)
        if op == '<':
            return compare_less(left, right)
        if op == '>':
            return compare_greater(left, right)
        
        return False
