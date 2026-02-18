"""
Predicate evaluation logic for XPath expressions.
"""

from typing import Any, List

from .parser import XPathTokenizer, XPathParser
from .utils import yang_bool, compare_equal


class PredicateEvaluator:
    """Handles predicate evaluation in XPath expressions."""
    
    def __init__(self, evaluator: Any):
        """Initialize predicate evaluator with reference to main evaluator.
        
        Args:
            evaluator: The main XPathEvaluator instance
        """
        self.evaluator = evaluator
    
    def apply_predicate(self, items: List[Any], predicate: str) -> Any:
        """Apply a predicate filter to a list of items.
        
        Returns:
            For simple index predicates like [1], returns the element directly.
            For other predicates, returns a filtered list.
        """
        # Optimized: check length first, then start/end
        pred_len = len(predicate)
        if pred_len < 3 or predicate[0] != '[' or predicate[-1] != ']':
            return items

        pred_expr = predicate[1:-1]

        # Handle index access [1] - return the element directly, not a list
        # Optimized: check if all digits before converting
        if pred_expr and pred_expr.isdigit():
            idx = int(pred_expr) - 1  # XPath is 1-indexed
            items_len = len(items)
            if 0 <= idx < items_len:
                return items[idx]  # Return element directly, not wrapped in list
            return None

        # Handle comparisons like [name = current()] or [type != 'array']
        # Optimized: check for != first (longer string) to avoid false matches
        if '!=' in pred_expr:
            op = '!='
            parts = pred_expr.split('!=', 1)
        elif '=' in pred_expr:
            op = '='
            parts = pred_expr.split('=', 1)
        else:
            return items
        
        if len(parts) == 2:
            left_expr = parts[0].strip()
            right_expr = parts[1].strip()
            
            # Optimized: pre-allocate list if we know approximate size
            items_len = len(items)
            filtered = []
            # Reserve space for common case (most items match)
            if items_len > 10:
                filtered = []

            for item in items:
                # Evaluate in the context of this item
                left_val = self.evaluate_value_in_context(left_expr, item)
                right_val = self.evaluate_value_in_context(right_expr, item)

                if op == '=':
                    if compare_equal(left_val, right_val):
                        filtered.append(item)
                else:  # !=
                    if not compare_equal(left_val, right_val):
                        filtered.append(item)

            return filtered

        return items
    
    def evaluate_value_in_context(self, expr: str, context: Any) -> Any:
        """Evaluate a value expression in a specific context.
        
        Note: current() should always refer to the original context, not the predicate context.
        So we preserve original_context_path and original_data while setting data and context_path
        to the item being tested (so paths like 'name' evaluate from the item).
        """
        # Save current context
        old_data = self.evaluator.data
        old_context_path = self.evaluator.context_path
        old_original_context_path = self.evaluator.original_context_path
        old_original_data = self.evaluator.original_data
        
        # Set context - if it's a dict, use it directly; otherwise wrap it
        if isinstance(context, dict):
            self.evaluator.data = context
        else:
            self.evaluator.data = {'value': context}
        # Set context_path to empty so paths like 'name' evaluate from the item root
        # But preserve original_context_path and original_data so current() still works
        self.evaluator._set_context_path([])

        try:
            # Parse and evaluate using AST
            tokenizer = XPathTokenizer(expr)
            tokens = tokenizer.tokenize()
            parser = XPathParser(tokens)
            ast = parser.parse()
            result = ast.evaluate(self.evaluator)
        finally:
            self.evaluator.data = old_data
            self.evaluator._set_context_path(old_context_path)
            self.evaluator.original_context_path = old_original_context_path
            self.evaluator.original_data = old_original_data

        return result
