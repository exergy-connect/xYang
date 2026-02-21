"""
Test utilities for XPath evaluator tests.
"""

from typing import Any, Dict, List, Optional
from xYang.xpath.context import Context


def create_context(data: Dict[str, Any], context_path: Optional[List[str]] = None) -> Context:
    """Create an initial context for evaluation.
    
    This is a test utility function for creating Context objects.
    In production code, contexts are created by the validator.
    
    Args:
        data: The data instance being validated
        context_path: Current path in the data structure (for current() and relative paths)
        
    Returns:
        Initial Context object
    """
    context_path = context_path or []
    return Context(
        data=data,
        context_path=context_path,
        original_context_path=context_path.copy(),
        original_data=data,
        root_data=data
    )
