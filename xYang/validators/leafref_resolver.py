"""
Leafref resolver and validator.
"""

from typing import Any, Dict, List, Optional
from ..module import YangModule
from ..ast import YangLeafStmt


class LeafrefResolver:
    """Resolves and validates leafref paths."""
    
    def __init__(self, module: YangModule):
        """
        Initialize leafref resolver.
        
        Args:
            module: YANG module
        """
        self.module = module
        self.errors: List[str] = []
    
    def validate_leafref(
        self,
        leaf: YangLeafStmt,
        value: Any,
        data: Dict[str, Any],
        context_path: List[str],
        root_data: Dict[str, Any]
    ) -> None:
        """
        Validate a leafref value.
        
        Args:
            leaf: Leaf statement with leafref type
            value: Value to validate
            data: Local data context
            context_path: Current path in data structure
            root_data: Root data for absolute paths
        """
        if not leaf.type or leaf.type.name != 'leafref' or not leaf.type.path:
            return
        
        path = leaf.type.path
        require_instance = (leaf.type.require_instance
                             if hasattr(leaf.type, 'require_instance') else True)
        
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
            # Convert relative path to absolute data path for value lookup
            if path.startswith('/'):
                # Absolute path - use root data
                data_path = path
                validation_data = root_data
            else:
                # Relative path - convert to absolute data path
                # Map context_path to data path and resolve relative path
                data_path = self._resolve_relative_data_path(path, context_path, root_data)
                validation_data = root_data
            
            target_values = self._get_leafref_target_values(data_path, validation_data)
            if value not in target_values:
                self.errors.append(
                    f"Invalid leafref value \"{value}\" - no target instance "
                    f"\"{path}\" with value \"{value}\""
                )
    
    def _resolve_leafref_path(self, path: str, context_path: List[str]) -> Optional[Any]:
        """
        Resolve a leafref path to find the target node in the schema.
        
        Args:
            path: Leafref path
            context_path: Current context path
            
        Returns:
            Target node or None if not found
        """
        # Handle absolute paths starting with /
        if path.startswith('/'):
            return self._resolve_absolute_path(path)
        
        # Handle relative paths starting with ../
        if path.startswith('../'):
            return self._resolve_relative_path(path, context_path)
        
        # Handle simple field names (relative to current context)
        return self._resolve_simple_path(path, context_path)
    
    def _resolve_absolute_path(self, path: str) -> Optional[Any]:
        """
        Resolve an absolute path like /data-model/entities/name.
        
        Args:
            path: Absolute path
            
        Returns:
            Target node or None
        """
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
    
    def _resolve_relative_path(
        self, path: str, context_path: List[str]
    ) -> Optional[Any]:
        """
        Resolve a relative path like ../field or ../../fields/name.
        
        Args:
            path: Relative path
            context_path: Current context path in data structure
            
        Returns:
            Target node in schema or None
        """
        # Parse the path to get up levels and field parts
        parts = path.split('/')
        up_levels = sum(1 for p in parts if p == '..')
        field_parts = [p for p in parts if p and p != '..']
        
        # Map data context path to schema path
        # Data paths like ['data-model', 'entities', 0, 'parents', 0, 'child_fk']
        # should map to schema path ['data-model', 'entities', 'parents', 'child_fk']
        # When context is at a list level (e.g., ['data-model', 'entities', 'parents']),
        # we're actually inside a list item, so .. goes to the parent of the list
        schema_path = []
        for part in context_path:
            if isinstance(part, int):
                # Skip list indices - they don't exist in schema
                continue
            schema_path.append(part)
        
        # YANG semantics: when you're inside a list item and use .., you go to the parent of the list
        # So if the last element in schema_path is a list name, the first .. goes to its parent
        # We need to check if we're at a list level and adjust accordingly
        # For now, we'll use the simple approach: go up the specified number of levels
        # But we need to ensure we don't go past the root
        
        # Navigate up the schema path
        if up_levels > len(schema_path):
            return None
        
        # Go up the specified number of levels
        base_path = schema_path[:-up_levels] if up_levels > 0 else schema_path
        
        # Build the target path by adding field parts
        target_path = base_path + field_parts
        absolute_path = '/' + '/'.join(target_path)
        result = self._resolve_absolute_path(absolute_path)
        
        # If that didn't work, try going up one less level
        # This handles cases like ../../fields/name from entities/parents where:
        # - We go up 2 levels: parents -> entities -> data-model (wrong, fields not under data-model)
        # - Should go up 1 level: parents -> entities, then fields/name (correct)
        if result is None and up_levels > 1:
            alt_base_path = schema_path[:-(up_levels - 1)] if (up_levels - 1) > 0 else schema_path
            alt_target_path = alt_base_path + field_parts
            alt_absolute_path = '/' + '/'.join(alt_target_path)
            alt_result = self._resolve_absolute_path(alt_absolute_path)
            if alt_result is not None:
                return alt_result
        
        return result
    
    def _resolve_simple_path(
        self, path: str, context_path: List[str]
    ) -> Optional[Any]:
        """
        Resolve a simple path relative to current context.
        
        Args:
            path: Simple path
            context_path: Current context path
            
        Returns:
            Target node or None
            
        Raises:
            NotImplementedError: Simple path resolution not yet implemented
        """
        # TODO: Implement simple path resolution
        raise NotImplementedError(
            f"Simple path resolution not yet implemented: {path}"
        )
    
    def _resolve_relative_data_path(
        self, path: str, context_path: List[str], root_data: Dict[str, Any]
    ) -> str:
        """
        Resolve a relative leafref path to an absolute data path.
        
        Args:
            path: Relative path (e.g., ../../fields/name)
            context_path: Current context path in data
            root_data: Root data for navigation
            
        Returns:
            Absolute data path (e.g., /data-model/entities/fields/name)
        """
        # Parse the path to get up levels and field parts
        parts = path.split('/')
        up_levels = sum(1 for p in parts if p == '..')
        field_parts = [p for p in parts if p and p != '..']
        
        # Navigate up from context_path
        if up_levels > len(context_path):
            # Can't go up that far - return a path that won't match
            return '/invalid/path'
        
        # Go up the specified number of levels
        base_path = context_path[:-up_levels] if up_levels > 0 else context_path
        
        # Build the absolute path
        absolute_path = '/' + '/'.join(base_path + field_parts)
        
        # Try to verify the path exists in data
        # If it doesn't, try going up one less level (same fix as schema resolution)
        test_values = self._get_leafref_target_values(absolute_path, root_data)
        if not test_values and up_levels > 1:
            # Try going up one less level
            alt_base_path = context_path[:-(up_levels - 1)] if (up_levels - 1) > 0 else context_path
            alt_absolute_path = '/' + '/'.join(alt_base_path + field_parts)
            alt_test_values = self._get_leafref_target_values(alt_absolute_path, root_data)
            if alt_test_values:
                return alt_absolute_path
        
        return absolute_path
    
    def _get_leafref_target_values(self, path: str, data: Dict[str, Any]) -> List[Any]:
        """
        Get all values at the target path in the data.
        
        Args:
            path: Leafref path
            data: Data to search
            
        Returns:
            List of values at the path
        """
        # Remove leading /
        parts = [p for p in path.split('/') if p]
        
        if not parts:
            return []
        
        def collect_values(data_obj: Any, remaining_parts: List[str]) -> List[Any]:
            """Recursively collect values from nested structures."""
            if not remaining_parts:
                # We've reached the target - collect the value
                if isinstance(data_obj, list):
                    return data_obj
                if data_obj is not None:
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
        
        return collect_values(data, parts)