"""
YANG validation engine.
"""

from typing import Any, Dict, List, Tuple
from .module import YangModule
from .ast import YangStatement, YangLeafStmt, YangListStmt, YangLeafListStmt, YangContainerStmt
from .types import TypeSystem
from .xpath import XPathEvaluator


class YangValidator:
    """YANG data validator."""

    def __init__(self, module: YangModule):
        self.module = module
        self.type_system = TypeSystem()
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate(self, data: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
        """
        Validate data against the YANG module.

        Returns:
            (is_valid, errors, warnings)
        """
        self.errors = []
        self.warnings = []

        # Validate against module structure
        self._validate_structure(data, self.module.statements)

        # Validate must statements
        self._validate_must_statements(data)

        return len(self.errors) == 0, self.errors, self.warnings

    def _validate_structure(self, data: Dict[str, Any], statements: List[YangStatement], context_path: List[str] = None):
        """Validate data structure against statements."""
        if context_path is None:
            context_path = []

        for stmt in statements:
            # Check when condition - skip if condition is false
            if hasattr(stmt, 'when') and stmt.when:
                evaluator = XPathEvaluator(data, self.module, context_path=context_path)
                if not evaluator.evaluate(stmt.when.condition):
                    # When condition is false, skip this statement
                    continue

            if isinstance(stmt, YangLeafStmt):
                self._validate_leaf(data, stmt)
            elif isinstance(stmt, YangListStmt):
                self._validate_list(data, stmt)
            elif isinstance(stmt, YangLeafListStmt):
                self._validate_leaf_list(data, stmt)
            elif hasattr(stmt, 'statements'):
                # Container or other composite statement
                if stmt.name in data:
                    new_path = context_path + [stmt.name] if hasattr(stmt, 'name') else context_path
                    self._validate_structure(data[stmt.name], stmt.statements, context_path=new_path)

    def _validate_leaf(self, data: Dict[str, Any], leaf: YangLeafStmt):
        """Validate a leaf."""
        if leaf.name not in data:
            if leaf.mandatory:
                self.errors.append(f"Missing mandatory leaf: {leaf.name}")
            elif leaf.default is not None:
                # Default value would be applied
                pass
        else:
            value = data[leaf.name]
            if leaf.type:
                is_valid, error_msg = self.type_system.validate(value, leaf.type.name)
                if not is_valid:
                    self.errors.append(f"Invalid value for leaf {leaf.name}: {error_msg}")

    def _validate_list(self, data: Dict[str, Any], list_stmt: YangListStmt):
        """Validate a list."""
        if list_stmt.name in data:
            items = data[list_stmt.name]
            if not isinstance(items, list):
                self.errors.append(f"Expected list for {list_stmt.name}, got {type(items).__name__}")
                return

            if list_stmt.min_elements is not None and len(items) < list_stmt.min_elements:
                self.errors.append(f"List {list_stmt.name} has fewer than {list_stmt.min_elements} elements")

            if list_stmt.max_elements is not None and len(items) > list_stmt.max_elements:
                self.errors.append(f"List {list_stmt.name} has more than {list_stmt.max_elements} elements")

            # Validate each item
            for item in items:
                if isinstance(item, dict):
                    self._validate_structure(item, list_stmt.statements)

    def _validate_leaf_list(self, data: Dict[str, Any], leaf_list: YangLeafListStmt):
        """Validate a leaf-list."""
        if leaf_list.name in data:
            items = data[leaf_list.name]
            if not isinstance(items, list):
                self.errors.append(f"Expected list for {leaf_list.name}, got {type(items).__name__}")
                return

            if leaf_list.min_elements is not None and len(items) < leaf_list.min_elements:
                self.errors.append(f"Leaf-list {leaf_list.name} has fewer than {leaf_list.min_elements} elements")

            if leaf_list.max_elements is not None and len(items) > leaf_list.max_elements:
                self.errors.append(f"Leaf-list {leaf_list.name} has more than {leaf_list.max_elements} elements")

            # Validate each item type
            if leaf_list.type:
                for item in items:
                    is_valid, error_msg = self.type_system.validate(item, leaf_list.type.name)
                    if not is_valid:
                        self.errors.append(f"Invalid value in leaf-list {leaf_list.name}: {error_msg}")

    def _validate_must_statements(self, data: Dict[str, Any]):
        """Validate must statements using XPath evaluator."""
        # Create evaluator with root context
        evaluator = XPathEvaluator(data, self.module, context_path=[])

        # Validate must statements recursively
        for stmt in self.module.statements:
            self._validate_must_in_statement(data, stmt, evaluator, [])

    def _validate_must_in_statement(self, data: Dict[str, Any], stmt: YangStatement,
                                   evaluator: XPathEvaluator, path: List[str]):
        """Recursively validate must statements in a statement."""
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

        # Validate must statements on this statement
        if isinstance(stmt, YangLeafStmt):
            for must in stmt.must_statements:
                if not evaluator.evaluate(must.expression):
                    error_msg = must.error_message or f"Must constraint failed for {stmt.name}"
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
