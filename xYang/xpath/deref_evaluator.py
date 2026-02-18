"""
Deref evaluation logic for XPath expressions.
"""

from typing import Any, List

from .ast import FunctionCallNode, PathNode, BinaryOpNode, FunctionCallNode as FCN


class DerefEvaluator:
    """Handles deref() function evaluation and leafref resolution."""
    
    def __init__(self, evaluator: Any):
        """Initialize deref evaluator with reference to main evaluator.
        
        Args:
            evaluator: The main XPathEvaluator instance
        """
        self.evaluator = evaluator
    
    def evaluate_deref_function(self, node: FunctionCallNode) -> Any:
        """Evaluate a deref() function call."""
        if len(node.args) == 1:
            arg_node = node.args[0]
            
            # Check if argument is a BinaryOpNode with '/' (path navigation from a node)
            # This handles cases like deref(deref(current())/../foreignKey/entity)
            if isinstance(arg_node, BinaryOpNode) and arg_node.operator == '/':
                # Evaluate left side (might be nested deref() or other expression)
                left_result = arg_node.left.evaluate(self.evaluator)
                
                # If left side is a node (dict), navigate from it
                if isinstance(left_result, dict):
                    # Save current context
                    old_data = self.evaluator.data
                    old_context = self.evaluator.context_path
                    try:
                        # Set the node as current data context
                        self.evaluator.data = left_result
                        self.evaluator._set_context_path([])
                        
                        # Evaluate right side (path navigation)
                        if isinstance(arg_node.right, PathNode):
                            # It's a PathNode - navigate from the node
                            path_value = self.evaluator.path_evaluator.evaluate_path_node(arg_node.right)
                        elif isinstance(arg_node.right, BinaryOpNode) and arg_node.right.operator == '/':
                            # Nested path - extract and evaluate
                            path_parts = self.evaluator.path_evaluator.extract_path_from_binary_op(arg_node.right)
                            if path_parts:
                                path_str = '/'.join(str(p) for p in path_parts if p)
                                path_value = self.evaluator.path_evaluator.evaluate_path(path_str)
                            else:
                                path_value = None
                        else:
                            # Try to evaluate as path
                            path_value = arg_node.right.evaluate(self.evaluator)
                        
                        # Now deref() the resulting value
                        if path_value is not None:
                            # We have a value - try to deref it
                            # First try to find it as an entity name (common case)
                            result = self.deref_value(path_value)
                            
                            # If that didn't work, try to get schema context from the path
                            # and use standard leafref resolution
                            if result is None:
                                # Try to determine what type of value this is based on context
                                # If we navigated from a field node, the value might be an entity name
                                # Try looking it up as an entity name
                                if isinstance(path_value, str):
                                    result = self.find_entity_by_name(path_value)
                                
                                # If still not found, try as field name in current entity
                                if result is None:
                                    result = self.find_field_by_name(path_value)
                        else:
                            result = None
                        
                        return result
                    finally:
                        self.evaluator.data = old_data
                        self.evaluator._set_context_path(old_context)
                else:
                    # Left side is not a node - treat as regular path expression
                    # Build path string from the binary op
                    path = self.build_path_from_node(arg_node)
                    return self.evaluate_deref(path)
            
            # Handle simple path expressions
            if isinstance(arg_node, PathNode):
                # It's a PathNode - build path string from steps
                if arg_node.is_absolute:
                    path = '/' + '/'.join(arg_node.steps)
                else:
                    path = '/'.join(arg_node.steps)
            elif isinstance(arg_node, FCN):
                # It's a function call like current() - use the function name and args as path
                # For current(), we want to pass "current()" as the path
                if arg_node.name == 'current' and len(arg_node.args) == 0:
                    path = 'current()'
                else:
                    # For other functions, build the path representation
                    path = f"{arg_node.name}()"
            else:
                # For other node types, try to get a string representation
                # This handles cases where the path is a simple value
                if hasattr(arg_node, 'evaluate'):
                    # Evaluate to get the value, but we need the path expression
                    # For deref(), we actually want to evaluate the path to get the value,
                    # then find the schema node at that location to get its leafref path
                    # So we need to pass the path expression, not the value
                    # For now, try to reconstruct the path from the node
                    path = str(arg_node) if hasattr(arg_node, '__str__') else ''
                else:
                    path = str(arg_node)
            return self.evaluate_deref(path)
        return None
    
    def evaluate_deref(self, path: str) -> Any:
        """Evaluate deref() - resolve a leafref path.
        
        In YANG, deref() takes a leafref path and returns the node it references.
        This follows the YANG specification strictly:
        1. Evaluate the path to get the leafref value
        2. Find the schema node for the field at that path
        3. Get the leafref path definition from the schema
        4. Use that path to find the referenced node in the data
        
        For example: deref(../entity)
        - Evaluates ../entity to get value (e.g., "company")
        - Finds the schema leaf for "entity" field
        - Gets its leafref path (e.g., "/data-model/entities/name")
        - Uses that path to find the node where name="company"
        """
        try:
            # Check cache first
            cache_key = f"{path}:{self.evaluator.context_path}"
            if cache_key in self.evaluator.leafref_cache:
                return self.evaluator.leafref_cache[cache_key]
            
            # Step 1: Evaluate the path to get the leafref value
            ref_value = self.evaluator.path_evaluator.evaluate_path(path)
            
            if ref_value is None:
                # Referenced node doesn't exist - acceptable for optional references
                return None
            
            # Step 2: Find the schema node for the field at this path
            leafref_path = self.get_leafref_path_from_schema(path)
            
            if not leafref_path:
                # No leafref definition found - cannot resolve
                return None
            
            # Step 3: Use the leafref path to find the referenced node
            result = self.find_node_by_leafref_path(leafref_path, ref_value)
            
            if result is not None:
                self.evaluator.leafref_cache[cache_key] = result
            
            return result
        except Exception:
            # If path evaluation fails, deref() returns None (referenced node doesn't exist)
            return None
    
    def deref_value(self, value: Any) -> Any:
        """Deref a value directly (when we already have the value, not the path).
        
        This is used for nested deref() calls where we've already evaluated
        the inner expression to get a value. We need to find the node containing
        that value in the data structure.
        
        Args:
            value: The value to deref (typically an entity name or field name)
            
        Returns:
            The node containing that value, or None if not found
        """
        if value is None:
            return None
        
        # Try to find as entity name first (most common case)
        result = self.find_entity_by_name(value)
        if result is not None:
            return result
        
        # Try to find as field name in current entity
        result = self.find_field_by_name(value)
        return result
    
    def find_entity_by_name(self, name: str) -> Any:
        """Find an entity node by name.
        
        Args:
            name: Entity name to search for
            
        Returns:
            Entity node (dict), or None if not found
        """
        # Optimized: early return for invalid inputs
        if not isinstance(name, str) or not self.evaluator.root_data:
            return None
        
        # Optimized: check key existence before get()
        data_model = self.evaluator.root_data.get("data-model")
        if not data_model:
            return None
        
        entities = data_model.get("entities")
        if not entities:
            return None
        
        # Optimized: iterate directly, avoid isinstance check if possible
        for entity in entities:
            if isinstance(entity, dict):
                entity_name = entity.get("name")
                if entity_name == name:
                    return entity
        
        return None
    
    def find_field_by_name(self, name: str) -> Any:
        """Find a field node by name in the current entity.
        
        Args:
            name: Field name to search for
            
        Returns:
            Field node (dict), or None if not found
        """
        # Optimized: early return for invalid inputs
        if not isinstance(name, str) or not self.evaluator.context_path:
            return None
        
        # Find the entity index from context - optimized single pass
        entity_idx = None
        context_len = len(self.evaluator.context_path)
        for i, part in enumerate(self.evaluator.context_path):
            if part == "entities" and i + 1 < context_len:
                next_part = self.evaluator.context_path[i + 1]
                if isinstance(next_part, int):
                    entity_idx = next_part
                    break
        
        if entity_idx is not None and self.evaluator.root_data:
            data_model = self.evaluator.root_data.get("data-model")
            if data_model:
                entities = data_model.get("entities")
                if entities and entity_idx < len(entities):
                    entity = entities[entity_idx]
                    if isinstance(entity, dict):
                        fields = entity.get("fields")
                        if fields:
                            # Optimized: iterate directly
                            for field in fields:
                                if isinstance(field, dict):
                                    field_name = field.get("name")
                                    if field_name == name:
                                        return field
        
        return None
    
    def build_path_from_node(self, node: Any) -> str:
        """Build a path string from an AST node.
        
        Args:
            node: AST node (PathNode, FunctionCallNode, BinaryOpNode, etc.)
            
        Returns:
            Path string representation
        """
        if isinstance(node, PathNode):
            if node.is_absolute:
                return '/' + '/'.join(node.steps)
            return '/'.join(node.steps)
        
        if isinstance(node, FCN):
            if node.name == 'current' and len(node.args) == 0:
                return 'current()'
            return f"{node.name}()"
        
        if isinstance(node, BinaryOpNode) and node.operator == '/':
            # Build path from binary op
            left_path = self.build_path_from_node(node.left)
            right_path = self.build_path_from_node(node.right)
            if left_path and right_path:
                return f"{left_path}/{right_path}"
            return left_path or right_path or ''
        
        # Fallback to string representation
        return str(node) if hasattr(node, '__str__') else ''
    
    def get_leafref_path_from_schema(self, path: str) -> str:
        """Get the leafref path definition from the schema for the field at the given path.
        
        Args:
            path: XPath expression pointing to a leafref field (e.g., "../entity", "current()")
            
        Returns:
            The leafref path string, or None if not found
        """
        # Resolve the path to find the schema node
        # First, resolve the path to an absolute schema path
        schema_path = self.resolve_path_to_schema_location(path)
        
        if not schema_path:
            return None
        
        # Find the schema node at that path
        schema_node = self.find_schema_node(schema_path)
        
        if not schema_node:
            return None
        
        # Check if it's a leaf with leafref type
        from ..ast import YangLeafStmt
        if not isinstance(schema_node, YangLeafStmt):
            return None
        
        if not schema_node.type or schema_node.type.name != 'leafref':
            return None
        
        # Get the leafref path
        if hasattr(schema_node.type, 'path') and schema_node.type.path:
            return schema_node.type.path
        
        return None
    
    def resolve_path_to_schema_location(self, path: str) -> List[str]:
        """Resolve an XPath expression to a schema location path.
        
        Args:
            path: XPath expression (e.g., "../entity", "current()", "./field")
            
        Returns:
            List of schema node names representing the full path from module root, or None
        """
        # Use original_context_path if available (for current() support in predicates)
        context_to_use = self.evaluator.original_context_path if self.evaluator.original_context_path else self.evaluator.context_path
        context_len = len(context_to_use) if context_to_use else 0
        
        # Handle current() or .
        if path == 'current()' or path == '.':
            # Use original context path, but convert data path to schema path
            # Schema path is similar but may need adjustment
            return self.data_path_to_schema_path(context_to_use)
        
        # Handle relative paths
        if path.startswith('../') or path.startswith('./'):
            parts = path.split('/')
            # Optimized: single pass through parts
            up_levels = 0
            field_parts = []
            for p in parts:
                if p == '..':
                    up_levels += 1
                elif p and p != '.':
                    field_parts.append(p)
            
            # Navigate up from context
            if up_levels == 0:
                # No navigation up - use current context + field parts
                data_path = context_to_use + field_parts
            elif up_levels <= context_len:
                # Navigate up 'up_levels' steps
                data_path = context_to_use[:-up_levels] + field_parts
            else:
                return None
            
            schema_path = self.data_path_to_schema_path(data_path)
            # Ensure we have the full path from root (should start with data-model)
            if schema_path and schema_path[0] != "data-model":
                # Prepend data-model if not present
                schema_path = ["data-model"] + schema_path
            return schema_path
        
        # Simple field name
        if path and not path.startswith('/'):
            data_path = context_to_use + [path]
            return self.data_path_to_schema_path(data_path)
        
        # Handle absolute paths
        if path.startswith('/'):
            # Remove leading / and convert to schema path
            parts = [p for p in path.split('/') if p]
            return parts
        
        return None
    
    def data_path_to_schema_path(self, data_path: List) -> List[str]:
        """Convert a data structure path to a schema path.
        
        Removes list indices and converts to schema node names.
        
        Args:
            data_path: Path in data structure (may contain integers for list indices)
            
        Returns:
            Schema path (list of node names, no indices)
        """
        schema_path = []
        for part in data_path:
            # Skip list indices (integers)
            if isinstance(part, int):
                continue
            # Skip special XPath parts
            if part in ('.', '..', 'current()'):
                continue
            schema_path.append(str(part))
        return schema_path
    
    def find_schema_node(self, schema_path: List[str]) -> Any:
        """Find a schema node at the given path.
        
        Args:
            schema_path: List of schema node names
            
        Returns:
            The schema node (YangStatement), or None if not found
        """
        # Optimized: early return
        if not self.evaluator.module or not schema_path:
            return None
        
        current_statements = self.evaluator.module.statements
        last_node = None
        
        # Optimized: iterate through path parts
        for part in schema_path:
            found = False
            # Optimized: iterate statements directly
            for stmt in current_statements:
                # Optimized: check name attribute existence once
                stmt_name = getattr(stmt, 'name', None)
                if stmt_name == part:
                    last_node = stmt
                    # Optimized: get statements attribute once
                    current_statements = getattr(stmt, 'statements', [])
                    found = True
                    break
            if not found:
                return None
        
        return last_node
    
    def find_node_by_leafref_path(self, leafref_path: str, ref_value: Any) -> Any:
        """Find a node in the data using a leafref path by recursively walking the tree.
        
        Args:
            leafref_path: The leafref path (e.g., "/data-model/entities/name" or "../../fields/name")
            ref_value: The value to search for
            
        Returns:
            The node containing the value, or None if not found
        """
        # Resolve relative paths to determine the target location
        if leafref_path.startswith('/'):
            # Absolute path - walk from root
            target_path = [p for p in leafref_path.split('/') if p]
        else:
            # Relative path - resolve relative to original context (for current() support in predicates)
            # Use original_context_path if available, otherwise use context_path
            context_to_use = self.evaluator.original_context_path if self.evaluator.original_context_path else self.evaluator.context_path
            
            # Parse the relative path - optimized single pass
            parts = leafref_path.split('/')
            up_levels = 0
            field_parts = []
            for p in parts:
                if p == '..':
                    up_levels += 1
                elif p:
                    field_parts.append(p)
            
            # Build target path by going up from context, then adding field parts
            context_len = len(context_to_use)
            if up_levels > context_len:
                return None
            
            # Remove list indices when going up (they're not part of schema structure)
            # Optimized: single pass to filter and count
            context_without_indices = [p for p in context_to_use if not isinstance(p, int)]
            if up_levels > len(context_without_indices):
                return None
            
            # Go up 'up_levels' schema levels, then add field parts
            base_path = context_without_indices[:-up_levels] if up_levels > 0 else context_without_indices
            target_path = base_path + field_parts
        
        if not target_path:
            return None
        
        # The last part is the key field name
        # Everything before it is the container/list path
        if len(target_path) < 2:
            return None
        
        key_field = target_path[-1]
        container_path_parts = target_path[:-1]
        
        # Recursively walk down the tree from root to find the container
        # Then search for the node with key_field == ref_value
        old_data = self.evaluator.data
        try:
            self.evaluator.data = self.evaluator.root_data
            # For absolute paths, don't use context index (search in all entities)
            # For relative paths, use context index (search in specific entity)
            use_context_index = not leafref_path.startswith('/')
            container = self.walk_path_to_container(container_path_parts, use_context_index=use_context_index)
            
            if container is None:
                return None
            
            # Search for the node with key_field == ref_value
            return self.search_for_node(container, key_field, ref_value)
        finally:
            self.evaluator.data = old_data
    
    def walk_path_to_container(self, path_parts: List[str], use_context_index: bool = True) -> Any:
        """Recursively walk down the tree following the path to find the container.
        
        This method uses context information (like entity indices) to navigate
        through lists when possible. For example, when walking to "entities/fields",
        it uses the entity index from the current context to find the specific entity.
        
        Args:
            path_parts: List of path parts (schema node names, no indices)
            use_context_index: If False, don't use entity index from context (for absolute paths)
            
        Returns:
            The container at that path, or None if not found
        """
        # Optimized: early return
        if not path_parts:
            return self.evaluator.root_data
        
        # Extract entity index from context if available and requested
        # Use original_context_path if available (for current() support in predicates)
        context_to_use = self.evaluator.original_context_path if self.evaluator.original_context_path else self.evaluator.context_path
        entity_idx = None
        if use_context_index and context_to_use:
            context_len = len(context_to_use)
            # Optimized: iterate with explicit bounds check
            for j in range(context_len - 1):
                if context_to_use[j] == "entities":
                    next_item = context_to_use[j + 1]
                    if isinstance(next_item, int):
                        entity_idx = next_item
                        break
        
        current = self.evaluator.root_data
        
        for i, part in enumerate(path_parts):
            if current is None:
                return None
            
            if isinstance(current, dict):
                if part in current:
                    next_value = current[part]
                    # Special handling: if we're navigating to "entities" and it's a list,
                    # and we have an entity index from context AND use_context_index is True, use it
                    if (part == "entities" and isinstance(next_value, list) and 
                        entity_idx is not None and use_context_index):
                        if 0 <= entity_idx < len(next_value):
                            current = next_value[entity_idx]
                        else:
                            return None
                    else:
                        current = next_value
                else:
                    return None
            elif isinstance(current, list):
                # For lists, check if context has an index for this list part
                list_idx = None
                if self.evaluator.context_path:
                    context_len = len(self.evaluator.context_path)
                    # Optimized: iterate with explicit bounds check
                    for j in range(context_len - 1):
                        if self.evaluator.context_path[j] == part:
                            next_item = self.evaluator.context_path[j + 1]
                            if isinstance(next_item, int):
                                list_idx = next_item
                                break
                
                if list_idx is not None and 0 <= list_idx < len(current):
                    # Use the specific list item from context
                    current = current[list_idx]
                else:
                    # Search through items to find one with the next part
                    # This handles cases where we need to search across list items
                    found = False
                    remaining_parts = path_parts[i:]
                    for item in current:
                        if isinstance(item, dict):
                            # Check if this item has the next part in the path
                            if remaining_parts and remaining_parts[0] in item:
                                # Recursively continue from this item
                                result = self.walk_path_from_node(item, remaining_parts)
                                if result is not None:
                                    return result
                    return None
            else:
                return None
        
        return current
    
    def walk_path_from_node(self, node: Any, path_parts: List[str]) -> Any:
        """Recursively walk down from a specific node following the path.
        
        Args:
            node: Starting node
            path_parts: Remaining path parts to follow
            
        Returns:
            The node at the end of the path, or None if not found
        """
        if not path_parts:
            return node
        
        current = node
        for part in path_parts:
            if current is None:
                return None
            
            if isinstance(current, dict):
                if part in current:
                    current = current[part]
                else:
                    return None
            elif isinstance(current, list):
                # For lists, collect all matching items from all list elements
                # This is used when searching for fields across entities
                results = []
                for item in current:
                    if isinstance(item, dict) and part in item:
                        value = item[part]
                        if isinstance(value, list):
                            results.extend(value)
                        else:
                            results.append(value)
                if not results:
                    return None
                # If there's only one result and no more path parts, return it
                if len(path_parts) == 1 and len(results) == 1:
                    return results[0] if isinstance(results[0], dict) else None
                # Otherwise, we need to continue searching
                # For now, return the first list if it's a list of dicts
                if results and isinstance(results[0], list):
                    current = results[0]
                elif results:
                    # If we have multiple results, we need to search through them
                    # This is a simplified approach - in practice, we'd need more context
                    return None
                else:
                    return None
            else:
                return None
        
        return current
    
    def search_for_node(self, container: Any, key_field: str, ref_value: Any) -> Any:
        """Search for a node in the container where key_field == ref_value.
        
        Args:
            container: The container to search in (dict, list, or nested structure)
            key_field: The field name to match
            ref_value: The value to search for
            
        Returns:
            The node containing the value, or None if not found
        """
        # Optimized: early return for None
        if container is None:
            return None
        
        # Optimized: type check once
        if isinstance(container, list):
            # Search in list items - optimized iteration
            for item in container:
                if isinstance(item, dict):
                    # Check direct match first (common case)
                    if key_field in item and item[key_field] == ref_value:
                        return item
                    # Also search recursively in nested structures
                    result = self.search_for_node(item, key_field, ref_value)
                    if result is not None:
                        return result
        elif isinstance(container, dict):
            # Check if container itself matches (fast path)
            if key_field in container and container[key_field] == ref_value:
                return container
            # Search in nested structures
            for value in container.values():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            # Check direct match first
                            if key_field in item and item[key_field] == ref_value:
                                return item
                            # Recursively search nested structures
                            result = self.search_for_node(item, key_field, ref_value)
                            if result is not None:
                                return result
                elif isinstance(value, dict):
                    # Recursively search in nested dicts
                    result = self.search_for_node(value, key_field, ref_value)
                    if result is not None:
                        return result
        
        return None
