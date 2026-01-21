"""
Constraint validator for YANG must/when statements.
"""

from typing import Any, Dict, List
from ..module import YangModule
from ..ast import YangStatement, YangLeafStmt, YangListStmt, YangContainerStmt
from ..xpath import XPathEvaluator


class ConstraintValidator:
    """Validates must constraints using XPath evaluator."""
    
    def __init__(self, module: YangModule, evaluator_factory=None):
        """
        Initialize constraint validator.
        
        Args:
            module: YANG module
            evaluator_factory: Factory function for creating XPathEvaluator instances
        """
        self.module = module
        self.evaluator_factory = evaluator_factory or XPathEvaluator
        self.errors: List[str] = []
    
    def validate_must_statements(self, data: Dict[str, Any], root_data: Dict[str, Any] = None) -> None:
        """
        Validate must statements using XPath evaluator.
        
        Args:
            data: Data to validate
            root_data: Root data structure (for absolute paths and cross-references)
        """
        # Use root_data if provided, otherwise use data as root
        root = root_data if root_data is not None else data
        
        # Create evaluator with root context
        evaluator = self.evaluator_factory(root, self.module, context_path=[])
        
        # Store root data in evaluator for absolute path resolution
        if hasattr(evaluator, 'root_data'):
            evaluator.root_data = root
        
        # Validate must statements recursively
        for stmt in self.module.statements:
            self._validate_must_in_statement(data, stmt, evaluator, [])
    
    def _validate_must_in_statement(
        self, 
        data: Dict[str, Any], 
        stmt: YangStatement,
        evaluator: XPathEvaluator, 
        path: List[str]
    ) -> None:
        """
        Recursively validate must statements in a statement.
        
        Args:
            data: Data to validate
            stmt: Statement to check
            evaluator: XPath evaluator (will be updated with context)
            path: Current path in data structure
        """
        current_path = path + [stmt.name] if hasattr(stmt, 'name') else path
        
        # Update evaluator context
        evaluator.context_path = current_path
        if current_path:
            # Try to get current data context
            current_data = data
            for p in current_path:
                if isinstance(current_data, dict) and p in current_data:
                    current_data = current_data[p]
                else:
                    current_data = None
                    break
            if current_data is not None:
                evaluator.data = current_data
            else:
                # If we can't find the data context, use root data
                # This allows must statements to work even when context is missing
                evaluator.data = data
        
        # Validate must statements on this statement
        if isinstance(stmt, YangLeafStmt):
            # Skip validation if the field doesn't exist in data (optional fields)
            if stmt.name not in data:
                # Only skip if field is not mandatory and has no default
                if not (stmt.mandatory or (hasattr(stmt, 'default') and stmt.default is not None)):
                    return  # Skip validation for missing optional fields
            
            for must in stmt.must_statements:
                try:
                    result = evaluator.evaluate(must.expression)
                    if not result:
                        error_msg = must.error_message or f"Must constraint failed for {stmt.name}"
                        self.errors.append(error_msg)
                except Exception as e:
                    # If evaluation fails (e.g., missing data, XPath error), log but don't fail
                    # unless it's a syntax error (which indicates a real problem)
                    # Missing data in optional fields is acceptable
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.debug(
                        "Must constraint evaluation failed for %s: %s (expression: %s)",
                        stmt.name, e, must.expression
                    )
                    # Only add error if field is mandatory or if it's a syntax error
                    if stmt.mandatory or "syntax" in str(e).lower() or "parse" in str(e).lower():
                        error_msg = must.error_message or f"Must constraint evaluation failed for {stmt.name}: {e}"
                        self.errors.append(error_msg)
        elif isinstance(stmt, (YangListStmt, YangContainerStmt)):
            if hasattr(stmt, 'must_statements'):
                for must in stmt.must_statements:
                    if not evaluator.evaluate(must.expression):
                        error_msg = must.error_message or f"Must constraint failed for {stmt.name}"
                        self.errors.append(error_msg)
        
        # Recurse into child statements
        if hasattr(stmt, 'statements'):
            for child in stmt.statements:
                self._validate_must_in_statement(data, child, evaluator, current_path)