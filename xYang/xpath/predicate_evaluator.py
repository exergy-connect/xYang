"""
Predicate evaluation logic for XPath expressions.
"""

from typing import Any, List

from .parser import XPathTokenizer, XPathParser
from .utils import yang_bool, compare_equal
from .context import Context


class PredicateEvaluator:
    """Handles predicate evaluation in XPath expressions."""
    
    def __init__(self, evaluator: Any):
        """Initialize predicate evaluator with reference to main evaluator.
        
        Args:
            evaluator: The main XPathEvaluator instance
        """
        self.evaluator = evaluator
    
    def apply_predicate(self, items: List[Any], predicate: str, context: Context) -> Any:
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
        # Optimized: isdigit() returns False for empty strings, so no need for 'and pred_expr'
        if pred_expr.isdigit():
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
        
        if len(parts) != 2:
            return items
        
        # Strip whitespace from expressions
        left_expr = parts[0].strip()
        right_expr = parts[1].strip()
        
        # Optimized: initialize empty list (Python lists grow efficiently)
        filtered = []
        
        # Optimized: combine comparison logic to avoid duplicate code
        is_equal_op = (op == '=')
        for item in items:
            # Evaluate in the context of this item
            # Pass base_context to preserve original_context_path and original_data for current()
            left_val = self.evaluate_value_in_context(left_expr, item, context)
            right_val = self.evaluate_value_in_context(right_expr, item, context)
            
            # Single comparison check
            if compare_equal(left_val, right_val) == is_equal_op:
                filtered.append(item)

        return filtered
    
    def evaluate_value_in_context(self, expr: str, item_context: Any, base_context: Context) -> Any:
        """Evaluate a value expression in a specific context.
        
        Note: current() should always refer to the original context, not the predicate context.
        So we preserve original_context_path and original_data while setting data and context_path
        to the item being tested (so paths like 'name' evaluate from the item).
        
        Args:
            expr: Expression to evaluate
            item_context: Item context (dict or value)
            base_context: Base context (preserves original_context_path and original_data)
        """
        # Create new context for evaluation, preserving original values for current()
        item_data = item_context if isinstance(item_context, dict) else {'value': item_context}
        new_context = base_context.with_data(item_data, [])

        # Optimized: use evaluator's expression cache if available
        # Check cache first (only for short expressions to avoid memory bloat)
        if len(expr) < 100 and hasattr(self.evaluator, '_expression_cache'):
            if expr in self.evaluator._expression_cache:
                ast = self.evaluator._expression_cache[expr]
            else:
                # Parse expression into AST
                tokenizer = XPathTokenizer(expr)
                tokens = tokenizer.tokenize()
                parser = XPathParser(tokens)
                ast = parser.parse()
                # Cache only short expressions
                self.evaluator._expression_cache[expr] = ast
        else:
            # Parse and evaluate using AST (no caching for long expressions)
            tokenizer = XPathTokenizer(expr)
            tokens = tokenizer.tokenize()
            parser = XPathParser(tokens)
            ast = parser.parse()
        
        result = ast.evaluate(self.evaluator, new_context)
        return result
