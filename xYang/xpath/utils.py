"""
Utility functions for XPath evaluation.
"""

from typing import Any


def yang_bool(value: Any) -> bool:
    """Convert a value to boolean following YANG rules.

    In YANG/JSON context:
    - String "true" -> True
    - String "false" -> False
    - Boolean true -> True
    - Boolean false -> False
    - Other values -> truthy/falsy
    """
    # Optimized: check bool first (fastest)
    if isinstance(value, bool):
        return value
    # Optimized: check None early
    if value is None:
        return False
    # Optimized: check empty collections early
    if isinstance(value, (list, dict)):
        return len(value) > 0
    if isinstance(value, str):
        # YANG/JSON boolean strings - check exact matches first (most common)
        if value == 'true':
            return True
        if value == 'false':
            return False
        # Check case-insensitive variants (covers 'True', 'False', etc.)
        lower_val = value.lower().strip()
        if lower_val == 'true':
            return True
        if lower_val == 'false':
            return False
        # Other strings are truthy
        return bool(value)
    # For other types, use Python's bool()
    return bool(value)


def xpath_number(value: Any) -> float:
    """Convert a value to a number following XPath number() function rules."""
    if value is None:
        return float('nan')
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    # Try to convert to float (handles strings and other types)
    try:
        return float(value)
    except (ValueError, TypeError):
        return float('nan')


def compare_equal(left: Any, right: Any) -> bool:
    """Compare two values for equality."""
    # Handle None/missing values first - in XPath, empty sequences don't equal anything
    # This is consistent with comparison operators (<=, >=, etc.) which return False for None
    # Note: We check this before the fast path to ensure None == None returns False
    if left is None or right is None:
        return False
    # Fast path: same object reference (only reached if both are not None)
    if left is right:
        return True
    # Fast path for same types
    if type(left) is type(right):
        return left == right
    # Handle string comparison with type coercion
    if isinstance(left, str) and isinstance(right, (int, float, bool)):
        return left == str(right)
    if isinstance(right, str) and isinstance(left, (int, float, bool)):
        return str(left) == right
    return left == right


def compare_less_equal(left: Any, right: Any) -> bool:
    """Compare left <= right."""
    # Handle None values - in XPath, comparisons with None/missing values evaluate to False
    # Exception: None == None is True, but for <=, None <= None should be False
    if left is None or right is None:
        # If both are None, comparison is undefined - return False for <=
        # If only one is None, comparison is False
        return False
    
    # Handle NaN values (from number() on date strings)
    # If both are NaN, try comparing as strings (for date strings in YYYY-MM-DD format)
    import math
    left_float = None
    right_float = None
    try:
        left_float = float(left)
        right_float = float(right)
    except (ValueError, TypeError):
        pass
    
    if left_float is not None and right_float is not None:
        if math.isnan(left_float) and math.isnan(right_float):
            # Both are NaN - likely from date strings, compare as strings
            return str(left) <= str(right)
        if math.isnan(left_float) or math.isnan(right_float):
            # One is NaN, comparison fails
            return False
        return left_float <= right_float
    
    # Fall back to string comparison
    try:
        return float(left) <= float(right)
    except (ValueError, TypeError):
        return str(left) <= str(right)


def compare_greater_equal(left: Any, right: Any) -> bool:
    """Compare left >= right."""
    # Handle None values - in XPath, comparisons with None/missing values evaluate to False
    # Exception: None == None is True, but for >=, None >= None should be False
    if left is None or right is None:
        # If both are None, comparison is undefined - return False for >=
        # If only one is None, comparison is False
        return False
    
    # Handle NaN values (from number() on date strings)
    # If both are NaN, try comparing as strings (for date strings in YYYY-MM-DD format)
    import math
    left_float = None
    right_float = None
    try:
        left_float = float(left)
        right_float = float(right)
    except (ValueError, TypeError):
        pass
    
    if left_float is not None and right_float is not None:
        if math.isnan(left_float) and math.isnan(right_float):
            # Both are NaN - likely from date strings, compare as strings
            return str(left) >= str(right)
        if math.isnan(left_float) or math.isnan(right_float):
            # One is NaN, comparison fails
            return False
        return left_float >= right_float
    
    # Fall back to string comparison
    try:
        return float(left) >= float(right)
    except (ValueError, TypeError):
        return str(left) >= str(right)


def compare_less(left: Any, right: Any) -> bool:
    """Compare left < right."""
    # Handle None values - in XPath, comparisons with None/missing values evaluate to False
    if left is None or right is None:
        return False
    try:
        return float(left) < float(right)
    except (ValueError, TypeError):
        return str(left) < str(right)


def compare_greater(left: Any, right: Any) -> bool:
    """Compare left > right."""
    # Handle None values - in XPath, comparisons with None/missing values evaluate to False
    if left is None or right is None:
        return False
    try:
        return float(left) > float(right)
    except (ValueError, TypeError):
        return str(left) > str(right)
