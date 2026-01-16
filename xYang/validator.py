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
        self._root_data: Dict[str, Any] = {}  # Store root data for leafref validation

    def validate(self, data: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
        """
        Validate data against the YANG module.

        Returns:
            (is_valid, errors, warnings)
        """
        self.errors = []
        self.warnings = []
        self._root_data = data  # Store root data for leafref validation

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
                self._validate_leaf(data, stmt, context_path)
            elif isinstance(stmt, YangListStmt):
                self._validate_list(data, stmt, context_path)
            elif isinstance(stmt, YangLeafListStmt):
                self._validate_leaf_list(data, stmt)
            elif hasattr(stmt, 'statements'):
                # Container or other composite statement
                if stmt.name in data:
                    new_path = context_path + [stmt.name] if hasattr(stmt, 'name') else context_path
                    self._validate_structure(data[stmt.name], stmt.statements, context_path=new_path)
                elif isinstance(stmt, YangContainerStmt) and hasattr(stmt, 'presence') and stmt.presence:
                    # Presence container - if present in data, validate it
                    if stmt.name in data:
                        new_path = context_path + [stmt.name] if hasattr(stmt, 'name') else context_path
                        self._validate_structure(data[stmt.name], stmt.statements, context_path=new_path)

    def _validate_leaf(self, data: Dict[str, Any], leaf: YangLeafStmt, context_path: List[str] = None):
        """Validate a leaf."""
        if context_path is None:
            context_path = []
            
        if leaf.name not in data:
            if leaf.mandatory:
                self.errors.append(f"Missing mandatory leaf: {leaf.name}")
            elif leaf.default is not None:
                # Default value would be applied
                pass
        else:
            value = data[leaf.name]
            if leaf.type:
                # Check if it's a leafref type
                if leaf.type.name == 'leafref' and leaf.type.path:
                    self._validate_leafref(leaf, value, data, context_path)
                else:
                    is_valid, error_msg = self.type_system.validate(value, leaf.type.name)
                    if not is_valid:
                        self.errors.append(f"Invalid value for leaf {leaf.name}: {error_msg}")

    def _validate_list(self, data: Dict[str, Any], list_stmt: YangListStmt, context_path: List[str] = None):
        """Validate a list."""
        if context_path is None:
            context_path = []
            
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
                    # Pass context path for nested validation
                    item_path = context_path + [list_stmt.name] if context_path else [list_stmt.name]
                    self._validate_structure(item, list_stmt.statements, context_path=item_path)

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

    def _validate_leafref(self, leaf: YangLeafStmt, value: Any, data: Dict[str, Any], context_path: List[str]):
        """Validate a leafref value."""
        if not leaf.type or leaf.type.name != 'leafref' or not leaf.type.path:
            return

        path = leaf.type.path
        require_instance = leaf.type.require_instance if hasattr(leaf.type, 'require_instance') else True

        # Resolve the path to find the target node in the schema
        target_node = self._resolve_leafref_path(path, context_path)
        
        if target_node is None:
            self.errors.append(
                f"Invalid leafref value \"{value}\" - no target instance \"{path}\" found in schema"
            )
            return

        # If require-instance is true, validate that the value exists in the data
        # Use root data for absolute paths, not local data context
        if require_instance:
            # For absolute paths, use root data; for relative paths, use local data
            validation_data = self._root_data if path.startswith('/') else data
            target_values = self._get_leafref_target_values(path, validation_data)
            if value not in target_values:
                self.errors.append(
                    f"Invalid leafref value \"{value}\" - no target instance \"{path}\" with value \"{value}\""
                )

    def _resolve_leafref_path(self, path: str, context_path: List[str]) -> Any:
        """Resolve a leafref path to find the target node in the schema."""
        # Handle absolute paths starting with /
        if path.startswith('/'):
            return self._resolve_absolute_path(path)
        
        # Handle relative paths starting with ../
        if path.startswith('../'):
            return self._resolve_relative_path(path, context_path)
        
        # Handle simple field names (relative to current context)
        return self._resolve_simple_path(path, context_path)

    def _resolve_absolute_path(self, path: str) -> Any:
        """Resolve an absolute path like /data-model/entities/name."""
        # Remove leading /
        parts = [p for p in path.split('/') if p]
        
        if not parts:
            return None
        
        # Start from module statements
        current_statements = self.module.statements
        last_stmt = None
        
        for i, part in enumerate(parts):
            found = False
            for stmt in current_statements:
                if hasattr(stmt, 'name') and stmt.name == part:
                    last_stmt = stmt
                    # If this is the last part, return the statement
                    if i == len(parts) - 1:
                        return stmt
                    # Otherwise, continue navigating
                    if hasattr(stmt, 'statements'):
                        current_statements = stmt.statements
                        found = True
                        break
            if not found:
                return None
        
        return last_stmt

    def _resolve_relative_path(self, path: str, context_path: List[str]) -> Any:
        """Resolve a relative path like ../field."""
        # For now, simplified - would need full context tracking
        # This is a basic implementation
        parts = [p for p in path.split('/') if p and p != '..']
        # Navigate up from context_path and then down
        # Simplified: just try to find in current context
        return None  # TODO: Implement full relative path resolution

    def _resolve_simple_path(self, path: str, context_path: List[str]) -> Any:
        """Resolve a simple path relative to current context."""
        # Try to find in current context statements
        # This is simplified - full implementation would track context
        return None  # TODO: Implement simple path resolution

    def _get_leafref_target_values(self, path: str, data: Dict[str, Any]) -> List[Any]:
        """Get all values at the target path in the data."""
        # Remove leading /
        parts = [p for p in path.split('/') if p]
        
        if not parts:
            return []
        
        current_data = data
        values = []
        
        def collect_values(data_obj: Any, remaining_parts: List[str]) -> List[Any]:
            """Recursively collect values from nested structures."""
            if not remaining_parts:
                # We've reached the target - collect the value
                if isinstance(data_obj, list):
                    return data_obj
                elif data_obj is not None:
                    return [data_obj]
                return []
            
            part = remaining_parts[0]
            rest = remaining_parts[1:]
            
            if isinstance(data_obj, dict):
                if part in data_obj:
                    return collect_values(data_obj[part], rest)
            elif isinstance(data_obj, list):
                # For lists, collect from all items
                result = []
                for item in data_obj:
                    if isinstance(item, dict) and part in item:
                        result.extend(collect_values(item[part], rest))
                    elif isinstance(item, dict):
                        # Try to find the part in nested structures
                        for key, value in item.items():
                            if key == part:
                                result.extend(collect_values(value, rest))
                return result
            
            return []
        
        return collect_values(current_data, parts)
