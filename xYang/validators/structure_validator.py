"""
Structure validator for YANG data.
"""

from typing import Any, Dict, List
from ..module import YangModule
from ..ast import (
    YangStatement, YangLeafStmt, YangListStmt, YangLeafListStmt, YangContainerStmt
)
from ..xpath import XPathEvaluator


class StructureValidator:
    """Validates data structure against YANG schema."""
    
    def __init__(self, module: YangModule, evaluator_factory=None):
        """
        Initialize structure validator.
        
        Args:
            module: YANG module to validate against
            evaluator_factory: Factory function for creating XPathEvaluator instances
        """
        self.module = module
        self.evaluator_factory = evaluator_factory or XPathEvaluator
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def validate(
        self, 
        data: Dict[str, Any], 
        statements: List[YangStatement],
        context_path: List[str] = None
    ) -> None:
        """
        Validate data structure against statements.
        
        Args:
            data: Data to validate
            statements: YANG statements to validate against
            context_path: Current path in data structure
        """
        if context_path is None:
            context_path = []
        
        for stmt in statements:
            # Check when condition - skip if condition is false
            if hasattr(stmt, 'when') and stmt.when:
                evaluator = self.evaluator_factory(data, self.module, context_path=context_path)
                if not evaluator.evaluate(stmt.when.condition):
                    # When condition is false, skip this statement
                    continue
            
            if isinstance(stmt, YangLeafStmt):
                self._validate_leaf(data, stmt, context_path)
            elif isinstance(stmt, YangListStmt):
                self._validate_list(data, stmt, context_path)
            elif isinstance(stmt, YangLeafListStmt):
                self._validate_leaf_list(data, stmt)
            elif hasattr(stmt, 'statements'):
                # Container or other composite statement
                if stmt.name in data:
                    new_path = context_path + [stmt.name] if hasattr(stmt, 'name') else context_path
                    self.validate(
                        data[stmt.name], stmt.statements, context_path=new_path
                    )
                elif (isinstance(stmt, YangContainerStmt) and
                      hasattr(stmt, 'presence') and stmt.presence):
                    # Presence container - if present in data, validate it
                    if stmt.name in data:
                        new_path = (context_path + [stmt.name]
                                     if hasattr(stmt, 'name') else context_path)
                        self.validate(
                            data[stmt.name], stmt.statements, context_path=new_path
                        )
    
    def _validate_leaf(
        self, data: Dict[str, Any], leaf: YangLeafStmt, context_path: List[str]
    ) -> None:
        """Validate a leaf."""
        if leaf.name not in data:
            if leaf.mandatory:
                self.errors.append(f"Missing mandatory leaf: {leaf.name}")
            elif leaf.default is not None:
                # Default value would be applied
                pass
    
    def _validate_list(
        self, data: Dict[str, Any], list_stmt: YangListStmt, context_path: List[str]
    ) -> None:
        """Validate a list."""
        if list_stmt.name in data:
            items = data[list_stmt.name]
            if not isinstance(items, list):
                self.errors.append(
                    f"Expected list for {list_stmt.name}, got {type(items).__name__}"
                )
                return
            
            if list_stmt.min_elements is not None and len(items) < list_stmt.min_elements:
                self.errors.append(
                    f"List {list_stmt.name} has fewer than {list_stmt.min_elements} elements"
                )
            
            if list_stmt.max_elements is not None and len(items) > list_stmt.max_elements:
                self.errors.append(
                    f"List {list_stmt.name} has more than {list_stmt.max_elements} elements"
                )
            
            # Validate each item
            for item in items:
                if isinstance(item, dict):
                    # Pass context path for nested validation
                    item_path = (context_path + [list_stmt.name]
                                  if context_path else [list_stmt.name])
                    self.validate(item, list_stmt.statements, context_path=item_path)
    
    def _validate_leaf_list(self, data: Dict[str, Any], leaf_list: YangLeafListStmt) -> None:
        """Validate a leaf-list."""
        if leaf_list.name in data:
            items = data[leaf_list.name]
            if not isinstance(items, list):
                self.errors.append(
                    f"Expected list for {leaf_list.name}, got {type(items).__name__}"
                )
                return
            
            if leaf_list.min_elements is not None and len(items) < leaf_list.min_elements:
                self.errors.append(
                    f"Leaf-list {leaf_list.name} has fewer than "
                    f"{leaf_list.min_elements} elements"
                )
            
            if leaf_list.max_elements is not None and len(items) > leaf_list.max_elements:
                self.errors.append(
                    f"Leaf-list {leaf_list.name} has more than "
                    f"{leaf_list.max_elements} elements"
                )