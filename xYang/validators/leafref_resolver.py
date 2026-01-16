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
            # For absolute paths, use root data; for relative paths, use local data
            validation_data = root_data if path.startswith('/') else data
            target_values = self._get_leafref_target_values(path, validation_data)
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
        Resolve a relative path like ../field.
        
        Args:
            path: Relative path
            context_path: Current context path
            
        Returns:
            Target node or None
            
        Raises:
            NotImplementedError: Relative path resolution not yet implemented
        """
        # TODO: Implement full relative path resolution
        raise NotImplementedError(
            f"Relative path resolution not yet implemented: {path}"
        )
    
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