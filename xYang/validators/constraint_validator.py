"""
Constraint validator for YANG must/when statements.
"""

import logging
from typing import Any, Dict, List
from ..module import YangModule
from ..ast import YangStatement, YangLeafStmt, YangListStmt, YangContainerStmt
from ..xpath import XPathEvaluator

logger = logging.getLogger(__name__)


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
    
    def _navigate_path(self, root_data: Dict[str, Any], path: List[str]) -> Any:
        """
        Navigate through data structure following the given path.
        
        Args:
            root_data: Root data structure to navigate from
            path: List of path parts (strings for dict keys, ints for list indices)
            
        Returns:
            The data at the path, or None if path doesn't exist
        """
        current = root_data
        for p in path:
            if current is None:
                return None
            if isinstance(current, dict):
                if p in current:
                    current = current[p]
                else:
                    return None
            elif isinstance(current, list):
                if isinstance(p, int) and 0 <= p < len(current):
                    current = current[p]
                else:
                    return None
            else:
                # Primitive value - can't navigate further
                return None
        return current
    
    def _get_root_data(self, evaluator: XPathEvaluator, fallback: Dict[str, Any]) -> Dict[str, Any]:
        """Get root_data from evaluator or use fallback."""
        return evaluator.root_data if hasattr(evaluator, 'root_data') else fallback
    
    def _setup_evaluator_context(
        self, 
        evaluator: XPathEvaluator, 
        context_path: List[str], 
        root_data: Dict[str, Any]
    ) -> None:
        """
        Set up evaluator context for must constraint evaluation.
        
        Args:
            evaluator: XPath evaluator to configure
            context_path: Current path in data structure
            root_data: Root data structure
        """
        evaluator.context_path = context_path
        evaluator.original_context_path = context_path.copy() if context_path else []
        evaluator.original_data = root_data
        
        # Navigate to current data context
        current_data = self._navigate_path(root_data, context_path)
        
        # Set evaluator.data appropriately
        if current_data is not None and not isinstance(current_data, (dict, list)):
            # Primitive value - use root_data so current() can navigate via context_path
            evaluator.data = root_data
        elif current_data is not None:
            evaluator.data = current_data
        else:
            # Path doesn't exist - use root_data as fallback
            evaluator.data = root_data
    
    def _validate_child_in_list_item(
        self,
        root_data: Dict[str, Any],
        child_stmt: YangStatement,
        evaluator: XPathEvaluator,
        item_path: List[str]
    ) -> None:
        """Validate a child statement within a list item (without recursion).
        
        This is used when iterating through list items to validate child statements
        for each item. It only validates the immediate child's constraints, not grandchildren.
        """
        child_path = item_path + [child_stmt.name] if hasattr(child_stmt, 'name') else item_path
        
        # Set up evaluator context
        self._setup_evaluator_context(evaluator, child_path, root_data)
        
        # Validate must statements on this child statement only
        if isinstance(child_stmt, YangLeafStmt):
            # Check if field exists in current data context
            field_exists = (
                isinstance(evaluator.data, dict) and child_stmt.name in evaluator.data
            )
            
            # Skip validation if the field doesn't exist (optional fields)
            if not field_exists:
                if not (child_stmt.mandatory or (hasattr(child_stmt, 'default') and child_stmt.default is not None)):
                    return  # Skip validation for missing optional fields
            
            # Evaluate must constraints
            for must in child_stmt.must_statements:
                evaluator.original_data = root_data
                evaluator.original_context_path = child_path.copy() if child_path else []
                self._evaluate_must_constraint(evaluator, must, child_stmt.name, child_stmt.mandatory)
        
        elif isinstance(child_stmt, (YangListStmt, YangContainerStmt)):
            if hasattr(child_stmt, 'must_statements'):
                for must in child_stmt.must_statements:
                    evaluator.original_data = root_data
                    evaluator.original_context_path = child_path.copy() if child_path else []
                    self._evaluate_must_constraint(evaluator, must, child_stmt.name, False)
        
        # Do NOT recurse - grandchildren will be handled by the normal recursion path
        # when _validate_must_in_statement is called for the list statement itself
    
    def _evaluate_must_constraint(
        self,
        evaluator: XPathEvaluator,
        must_expr: Any,
        field_name: str,
        is_mandatory: bool
    ) -> None:
        """
        Evaluate a must constraint and add error if it fails.
        
        Args:
            evaluator: XPath evaluator
            must_expr: Must statement with expression and error_message
            field_name: Name of field being validated (for error messages)
            is_mandatory: Whether the field is mandatory
        """
        try:
            result = evaluator.evaluate(must_expr.expression)
            if not result:
                error_msg = must_expr.error_message or f"Must constraint failed for {field_name}"
                self.errors.append(error_msg)
        except Exception as e:
            # Log evaluation failures for debugging
            logger.debug(
                "Must constraint evaluation failed for %s: %s (expression: %s)",
                field_name, e, must_expr.expression
            )
            # Only add error if field is mandatory or if it's a syntax error
            if is_mandatory or "syntax" in str(e).lower() or "parse" in str(e).lower():
                error_msg = must_expr.error_message or f"Must constraint evaluation failed for {field_name}: {e}"
                self.errors.append(error_msg)
    
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
            data: Data to validate (legacy parameter, not used)
            stmt: Statement to check
            evaluator: XPath evaluator (will be updated with context)
            path: Current path in data structure
        """
        current_path = path + [stmt.name] if hasattr(stmt, 'name') else path
        root_data = self._get_root_data(evaluator, data)
        
        # Set up evaluator context
        self._setup_evaluator_context(evaluator, current_path, root_data)
        
        # Validate must statements on this statement
        if isinstance(stmt, YangLeafStmt):
            # Check if field exists in current data context
            field_exists = (
                isinstance(evaluator.data, dict) and stmt.name in evaluator.data
            )
            
            # Skip validation if the field doesn't exist (optional fields)
            if not field_exists:
                if not (stmt.mandatory or (hasattr(stmt, 'default') and stmt.default is not None)):
                    return  # Skip validation for missing optional fields
            
            # Evaluate must constraints
            for must in stmt.must_statements:
                # Ensure original_data is set before each evaluation
                evaluator.original_data = root_data
                evaluator.original_context_path = current_path.copy() if current_path else []
                self._evaluate_must_constraint(evaluator, must, stmt.name, stmt.mandatory)
                
        elif isinstance(stmt, (YangListStmt, YangContainerStmt)):
            if hasattr(stmt, 'must_statements'):
                for must in stmt.must_statements:
                    # Ensure original_data is set before each evaluation
                    evaluator.original_data = root_data
                    evaluator.original_context_path = current_path.copy() if current_path else []
                    self._evaluate_must_constraint(evaluator, must, stmt.name, False)
        
        # Recurse into child statements
        if hasattr(stmt, 'statements'):
            # For list statements, iterate through actual list items in data
            if isinstance(stmt, YangListStmt):
                list_data = self._navigate_path(root_data, current_path)
                if isinstance(list_data, list):
                    # Validate each list item with its index in the path
                    for idx, item in enumerate(list_data):
                        item_path = current_path + [idx]
                        # Set up evaluator context for this list item
                        self._setup_evaluator_context(evaluator, item_path, root_data)
                        # Validate child statements for this list item
                        # Use a helper to validate children without double recursion
                        for child in stmt.statements:
                            self._validate_child_in_list_item(root_data, child, evaluator, item_path)
                else:
                    # List doesn't exist or is not a list - validate child statements normally
                    for child in stmt.statements:
                        child_data = self._navigate_path(root_data, current_path)
                        if child_data is None:
                            child_data = root_data
                        self._validate_must_in_statement(child_data, child, evaluator, current_path)
            else:
                # For non-list statements, validate child statements normally
                for child in stmt.statements:
                    # Navigate to child data from root_data
                    child_data = self._navigate_path(root_data, current_path)
                    if child_data is None:
                        child_data = root_data
                    self._validate_must_in_statement(child_data, child, evaluator, current_path)