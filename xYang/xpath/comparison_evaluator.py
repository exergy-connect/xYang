"""
Comparison operations for XPath expressions with type-aware coercion.
"""

from typing import Any, Optional

from .utils import (
    compare_equal,
    compare_less_equal,
    compare_greater_equal,
    compare_less,
    compare_greater
)


class ComparisonEvaluator:
    """Handles comparison operations in XPath expressions with type-aware coercion."""
    
    def __init__(self, evaluator: Any):
        """Initialize comparison evaluator.
        
        Args:
            evaluator: The main XPathEvaluator instance (for accessing module/schema)
        """
        self.evaluator = evaluator
    
    def evaluate_comparison(self, op: str, left: Any, right: Any, type_context: Optional[Any] = None) -> bool:
        """Evaluate a comparison operation with type-aware coercion.
        
        Args:
            op: Comparison operator (=, !=, <=, >=, <, >)
            left: Left operand
            right: Right operand
            type_context: Schema type context (YangTypeStmt) for coercion
            
        Returns:
            Boolean result of comparison
        """
        # Coerce values based on type context
        left = self._coerce_value(left, type_context)
        right = self._coerce_value(right, type_context)
        
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
    
    def _coerce_value(self, value: Any, type_context: Optional[Any]) -> Any:
        """
        Coerce a value based on type context.
        
        Args:
            value: Value to coerce
            type_context: Schema type context (YangTypeStmt)
            
        Returns:
            Coerced value, or original value if no coercion needed/applicable
        """
        if type_context is None:
            return value
        
        # Handle union types: try coercion in declared order, use first success
        if hasattr(type_context, 'types') and type_context.types:
            for union_type in type_context.types:
                coerced = self._coerce_value_for_type(value, union_type)
                if coerced is not None:
                    return coerced
            return value
        
        # Handle simple types
        coerced = self._coerce_value_for_type(value, type_context)
        return coerced if coerced is not None else value
    
    def _coerce_value_for_type(self, value: Any, type_stmt: Any) -> Optional[Any]:
        """
        Coerce a value for a specific type statement.
        
        Args:
            value: Value to coerce
            type_stmt: Type statement (YangTypeStmt)
            
        Returns:
            Coerced value, or None if no coercion needed/applicable
        """
        if not hasattr(type_stmt, 'name'):
            return None
        
        type_name = type_stmt.name
        
        if type_name == 'boolean':
            return self._coerce_boolean(value)
        elif type_name == 'int32':
            return self._coerce_int32(value)
        
        return None
    
    def _coerce_boolean(self, value: Any) -> Optional[bool]:
        """
        Coerce a value to boolean.
        
        Coerces string "true"/"false" to Python True/False.
        This ensures bool() in XPath sees actual booleans, not strings.
        
        Args:
            value: Value to coerce
            
        Returns:
            Coerced boolean value, or None if value is already boolean or not coercible
        """
        if isinstance(value, bool):
            return None  # Already boolean, no coercion needed
        
        if isinstance(value, str):
            value_lower = value.lower().strip()
            if value_lower == 'true':
                return True
            elif value_lower == 'false':
                return False
        
        return None  # Not coercible to boolean
    
    def _coerce_int32(self, value: Any) -> Optional[int]:
        """
        Coerce a value to int32.
        
        Coerces string digits to integers.
        
        Args:
            value: Value to coerce
            
        Returns:
            Coerced integer value, or None if value is already int or not coercible
        """
        if isinstance(value, int):
            return None  # Already integer, no coercion needed
        
        if isinstance(value, str):
            # Try to parse as integer
            try:
                # Remove whitespace
                value_stripped = value.strip()
                # Check if it's all digits (with optional sign)
                if value_stripped and (value_stripped[0] in '+-' and value_stripped[1:].isdigit() or value_stripped.isdigit()):
                    return int(value_stripped)
            except (ValueError, AttributeError):
                pass
        
        return None  # Not coercible to int32
