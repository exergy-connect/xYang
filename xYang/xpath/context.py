"""
Immutable context for XPath evaluation.
"""

from typing import Any, Dict, List
from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationContext:
    """Immutable context for XPath evaluation."""
    data: Dict[str, Any]
    context_path: List[str]
    module: Any  # YangModule
    
    def with_data(self, data: Dict[str, Any]) -> 'EvaluationContext':
        """Create new context with updated data."""
        return EvaluationContext(
            data=data,
            context_path=self.context_path,
            module=self.module
        )
    
    def with_path(self, path: List[str]) -> 'EvaluationContext':
        """Create new context with updated path."""
        return EvaluationContext(
            data=self.data,
            context_path=path,
            module=self.module
        )
    
    def with_data_and_path(self, data: Dict[str, Any], path: List[str]) -> 'EvaluationContext':
        """Create new context with updated data and path."""
        return EvaluationContext(
            data=data,
            context_path=path,
            module=self.module
        )