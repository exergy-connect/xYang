"""
Schema and leafref resolution utilities for XPath expressions.
"""

from typing import Any, List, Iterator

from .ast import FunctionCallNode, PathNode, BinaryOpNode, FunctionCallNode as FCN
from .parser import XPathTokenizer, XPathParser
from .context import Context


class SchemaLeafrefResolver:
    """Resolves schema paths and leafref references for XPath deref() function."""
    
    def __init__(self, evaluator: Any):
        """Initialize deref evaluator with reference to main evaluator.
        
        Args:
            evaluator: The main XPathEvaluator instance
        """
        self.evaluator = evaluator
    
    def _parse_path_steps(self, path: str) -> tuple[List[str], bool, int]:
        """Parse a path string using AST parser and extract steps.
        
        Args:
            path: Path string to parse
            
        Returns:
            Tuple of (steps, is_absolute, up_levels)
            - steps: List of path steps (excluding '..')
            - is_absolute: True if path starts with '/'
            - up_levels: Number of '..' steps
            
        Raises:
            XPathSyntaxError: If the path cannot be parsed
        """
        tokenizer = XPathTokenizer(path)
        tokens = tokenizer.tokenize()
        parser = XPathParser(tokens, path)
        path_node = parser.parse()
        
        from ..errors import XPathSyntaxError
        
        if not isinstance(path_node, PathNode):
            raise XPathSyntaxError(f"Expected path expression, got {type(path_node).__name__}")
        
        steps = []
        up_levels = 0
        for segment in path_node.segments:
            if segment.step == '..':
                up_levels += 1
            elif segment.step and segment.step != '.':
                steps.append(segment.step)
        return steps, path_node.is_absolute, up_levels
    
    def evaluate_deref(self, path: str, context: Context) -> Any:
        """Evaluate deref() - resolve a leafref path.
        
        In YANG, deref() takes a leafref path and returns the node it references.
        This follows the YANG specification strictly:
        1. Evaluate the path to get the leafref value
        2. Find the schema node for the field at that path
        3. Get the leafref path definition from the schema
        4. Use that path to find the referenced node in the data
        
        Args:
            path: Path expression to evaluate (e.g., "current()", "../entity")
            context: Context for evaluation (required, never None)
        
        For example: deref(../entity)
        - Evaluates ../entity to get value (e.g., "company")
        - Finds the schema leaf for "entity" field
        - Gets its leafref path (e.g., "/data-model/entities/name")
        - Uses that path to find the node where name="company"
        """
        try:
            # Check cache first (cache context path string to avoid repeated conversion)
            context_str = str(context.context_path)
            cache_key = f"{path}:{context_str}"
            if cache_key in self.evaluator.leafref_cache:
                return self.evaluator.leafref_cache[cache_key]
            
            # Step 1: Evaluate the path to get the leafref value
            ref_value = self.evaluator.path_evaluator.evaluate_path(path, context)
            
            if ref_value is None:
                # Referenced node doesn't exist - acceptable for optional references
                return None
            
            # Step 2: Find the schema node for the field at this path
            leafref_path = self.get_leafref_path_from_schema(path, context)
            
            if not leafref_path:
                # No leafref definition found - cannot resolve
                return None
            
            # Step 3: Use the leafref path to find the referenced node
            result_tuple = self.find_node_by_leafref_path(leafref_path, ref_value, context)
            if result_tuple:
                result, node_path = result_tuple
                if node_path:
                    self.evaluator._deref_node_paths[id(result)] = node_path
                self.evaluator.leafref_cache[cache_key] = result
                return result
            self.evaluator.leafref_cache[cache_key] = None
            return None
        except Exception:
            # If path evaluation fails, deref() returns None (referenced node doesn't exist)
            return None
    
    def build_path_from_node(self, node: Any) -> str:
        """Build a path string from an AST node.
        
        Args:
            node: AST node (PathNode, FunctionCallNode, BinaryOpNode, etc.)
            
        Returns:
            Path string representation
        """
        if isinstance(node, PathNode):
            # Optimized: use join directly, avoid conditional string concatenation
            steps_str = '/'.join(seg.step for seg in node.segments)
            return '/' + steps_str if node.is_absolute else steps_str
        
        if isinstance(node, FCN):
            # Optimized: early return for common case
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
    
    def get_leafref_path_from_schema(self, path: str, context: Context) -> str:
        """Get the leafref path definition from the schema for the field at the given path.
        
        Args:
            path: XPath expression pointing to a leafref field (e.g., "../entity", "current()")
            context: Context to use for schema resolution (required, never None)
            
        Returns:
            The leafref path string, or None if not found
        """
        # Resolve the path to find the schema node
        schema_path = self.resolve_path_to_schema_location(path, context)
        if not schema_path:
            return None
        
        # Find the schema node at that path
        schema_node = self.find_schema_node(schema_path)
        
        if not schema_node:
            # If we can't find the schema node, try alternative approaches
            # For current(), the path might need adjustment
            if path == 'current()':
                # Cache context paths to avoid repeated attribute access
                original_context = context.original_context_path
                context_to_use = original_context if original_context else context.context_path
                if context_to_use:
                    # Try to find the schema node by matching the last element of the context
                    last_part = context_to_use[-1]
                    if last_part and not isinstance(last_part, int):
                        # Try to find a schema node with this name in the parent context
                        parent_schema_path = self.data_path_to_schema_path(context_to_use[:-1])
                        if parent_schema_path:
                            parent_node = self.find_schema_node(parent_schema_path)
                            if parent_node:
                                # Search for a child with the matching name (optimized: early return)
                                statements = getattr(parent_node, 'statements', [])
                                for stmt in statements:
                                    if getattr(stmt, 'name', None) == last_part:
                                        schema_node = stmt
                                        break
            
            if not schema_node:
                return None
        
        # If schema_node is a container, try to find a 'name' leaf inside it
        # This handles cases like ../child_fk where child_fk is a container with a name leaf
        from ..ast import YangContainerStmt
        if isinstance(schema_node, YangContainerStmt):
            # Look for a 'name' leaf inside the container
            statements = getattr(schema_node, 'statements', [])
            for stmt in statements:
                from ..ast import YangLeafStmt
                if isinstance(stmt, YangLeafStmt) and getattr(stmt, 'name', None) == 'name':
                    schema_node = stmt
                    break
        
        # Check if it's a leaf with leafref type (optimized: early returns)
        from ..ast import YangLeafStmt
        if not isinstance(schema_node, YangLeafStmt):
            return None
        
        type_obj = schema_node.type
        if not type_obj or type_obj.name != 'leafref':
            return None
        
        # Get the leafref path (optimized: single attribute check)
        return getattr(type_obj, 'path', None)
    
    def resolve_path_to_schema_location(self, path: str, context: Context) -> List[str]:
        """Resolve an XPath expression to a schema location path.
        
        Args:
            path: XPath expression (e.g., "../entity", "current()", "./field")
            context: Context to use for schema resolution (required, never None)
            
        Returns:
            List of schema node names representing the full path from module root, or None
        """
        # Cache context paths to avoid repeated attribute access
        original_context = context.original_context_path
        context_to_use = original_context if original_context else context.context_path
        context_len = len(context_to_use) if context_to_use else 0
        
        # Handle current() or .
        if path == 'current()' or path == '.':
            schema_path = self.data_path_to_schema_path(context_to_use)
            # Ensure we have the full path from root
            if schema_path:
                root_container = self._get_root_container_name()
                if not root_container:
                    return None
                if schema_path[0] != root_container:
                    schema_path = [root_container] + schema_path
            return schema_path
        
        # Handle relative paths using AST parser
        if path.startswith('../') or path.startswith('./'):
            field_parts, _, up_levels = self._parse_path_steps(path)
            
            # Navigate up from context
            if up_levels == 0:
                data_path = context_to_use + field_parts
            elif up_levels <= context_len:
                data_path = context_to_use[:-up_levels] + field_parts
            else:
                return None
            
            schema_path = self.data_path_to_schema_path(data_path)
            # Ensure we have the full path from root
            if schema_path:
                root_container = self._get_root_container_name()
                if not root_container:
                    return None
                if schema_path[0] != root_container:
                    schema_path = [root_container] + schema_path
            return schema_path
        
        # Simple field name
        if path and not path.startswith('/'):
            data_path = context_to_use + [path]
            return self.data_path_to_schema_path(data_path)
        
        # Handle absolute paths using AST parser
        if path.startswith('/'):
            steps, _, _ = self._parse_path_steps(path)
            return steps
        
        return None
    
    def data_path_to_schema_path(self, data_path: List) -> List[str]:
        """Convert a data structure path to a schema path.
        
        Removes list indices and converts to schema node names.
        
        Args:
            data_path: Path in data structure (may contain integers for list indices)
            
        Returns:
            Schema path (list of node names, no indices)
        """
        # Optimized: use list comprehension with filter
        # Skip list indices (integers) and special XPath parts
        skip_parts = {'.', '..', 'current()'}
        return [str(part) for part in data_path 
                if not isinstance(part, int) and part not in skip_parts]
    
    def _get_root_container_name(self) -> str | None:
        """Get the root container name from the module.
        
        Returns:
            The name of the root container, or None if not found
        """
        module = self.evaluator.module
        if not module:
            return None
        
        # Look for the first top-level container in the module
        from ..ast import YangContainerStmt
        for stmt in module.statements:
            if isinstance(stmt, YangContainerStmt):
                return getattr(stmt, 'name', None)
        
        return None
    
    def find_schema_node(self, schema_path: List[str]) -> Any:
        """Find a schema node at the given path.
        
        Traverses uses statements by following grouping references.
        Only instantiates nodes when there's a refine statement.
        
        Args:
            schema_path: List of schema node names
            
        Returns:
            The schema node (YangStatement), or None if not found
        """
        # Optimized: early return
        module = self.evaluator.module
        if not module or not schema_path:
            return None
        
        current_statements = module.statements
        last_node = None
        
        # Optimized: iterate through path parts with early return
        for part in schema_path:
            found = False
            # Traverse statements (groupings are already expanded during parsing)
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
    
    def find_node_by_leafref_path(self, leafref_path: str, ref_value: Any, context: Context) -> tuple[Any, List] | None:
        """Find a node in the data using a leafref path by recursively walking the tree.
        
        Args:
            leafref_path: The leafref path (e.g., "/data-model/entities/name" or "../../fields/name")
            ref_value: The value to search for
            context: Context for evaluation (required, never None)
            
        Returns:
            Tuple of (node, path) where node is the found node and path is its location in data tree,
            or None if not found
        """
        # Resolve relative paths to determine the target location using AST parser
        if leafref_path.startswith('/'):
            # Absolute path - walk from root using AST parser
            steps, _, _ = self._parse_path_steps(leafref_path)
            target_path = steps
        else:
            # Relative path - resolve relative to original context
            # Cache context paths to avoid repeated attribute access
            original_context = context.original_context_path
            context_to_use = original_context if original_context else context.context_path
            
            # Parse the relative path using AST parser
            field_parts, _, up_levels = self._parse_path_steps(leafref_path)
            
            # Build target path by going up from context, then adding field parts
            context_len = len(context_to_use)
            if up_levels > context_len:
                return None
            
            # Remove list indices when going up (optimized: list comprehension)
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
        # Create new context with root_data as data for path walking
        nav_context = context.with_data(context.root_data, context.context_path)
        # For absolute paths, don't use context index (search in all entities)
        # For relative paths, use context index (search in specific entity)
        use_context_index = not leafref_path.startswith('/')
        container = self.walk_path_to_container(container_path_parts, nav_context, use_context_index=use_context_index)
        
        if container is None:
            return None
        
        # Search for the node with key_field == ref_value
        node = self.search_for_node(container, key_field, ref_value)
        if node is None:
            return None
        
        # Find the full path to the node by searching the data tree
        node_path = self._find_node_path(context.root_data, node, container_path_parts, key_field, ref_value)
        return (node, node_path) if node_path else (node, None)
    
    def _find_node_path(self, root_data: Any, target_node: Any, container_path: List[str], key_field: str, ref_value: Any) -> List | None:
        """Find the full data path to a node by recursively searching the tree.
        
        Args:
            root_data: Root data to search in
            target_node: The node to find
            container_path: Path to the container (schema path, no indices)
            key_field: The key field name
            ref_value: The key field value
            
        Returns:
            Full data path (with indices) to the node, or None if not found
        """
        def search_recursive(data: Any, path: List) -> List | None:
            """Recursively search for the target node."""
            if data is target_node:
                return path
            
            if isinstance(data, dict):
                for key, value in data.items():
                    if value is target_node:
                        return path + [key]
                    if isinstance(value, (dict, list)):
                        result = search_recursive(value, path + [key])
                        if result:
                            return result
            elif isinstance(data, list):
                for idx, item in enumerate(data):
                    if item is target_node:
                        return path + [idx]
                    if isinstance(item, (dict, list)):
                        result = search_recursive(item, path + [idx])
                        if result:
                            return result
            return None
        
        # Search from root
        return search_recursive(root_data, [])
    
    def walk_path_to_container(self, path_parts: List[str], context: Context, use_context_index: bool = True) -> Any:
        """Recursively walk down the tree following the path to find the container.
        
        This method uses context information (like entity indices) to navigate
        through lists when possible. For example, when walking to "entities/fields",
        it uses the entity index from the current context to find the specific entity.
        
        Args:
            path_parts: List of path parts (schema node names, no indices)
            context: Context for evaluation (required, never None)
            use_context_index: If False, don't use entity index from context (for absolute paths)
            
        Returns:
            The container at that path, or None if not found
        """
        # Optimized: early return
        if not path_parts:
            return context.root_data
        
        # Extract list index from context if available and requested
        # Cache context paths to avoid repeated attribute access
        original_context = context.original_context_path
        context_to_use = original_context if original_context else context.context_path
        list_idx = None
        list_name = None
        if use_context_index and context_to_use:
            context_len = len(context_to_use)
            # Find any list in the context path (generic, not hardcoded to "entities")
            # Look for pattern: [..., list_name, index, ...]
            for j in range(context_len - 1):
                if isinstance(context_to_use[j + 1], int):
                    # Found a list index - store the list name and index
                    list_name = context_to_use[j]
                    list_idx = context_to_use[j + 1]
                    break
        
        current = context.root_data
        
        for i, part in enumerate(path_parts):
            if current is None:
                return None
            
            if isinstance(current, dict):
                if part in current:
                    next_value = current[part]
                    # Special handling: if we're navigating to a list that matches the context,
                    # and we have a list index from context AND use_context_index is True, use it
                    # This is generic - works with any list, not just "entities"
                    if (part == list_name and isinstance(next_value, list) and 
                        list_idx is not None and use_context_index):
                        if 0 <= list_idx < len(next_value):
                            current = next_value[list_idx]
                        else:
                            return None
                    else:
                        current = next_value
                else:
                    return None
            elif isinstance(current, list):
                # For lists, check if context has an index for this list part
                # Use cached context_to_use instead of accessing attribute again
                list_idx = None
                if context_to_use:
                    context_len = len(context_to_use)
                    # Optimized: iterate with explicit bounds check
                    for j in range(context_len - 1):
                        if context_to_use[j] == part:
                            next_item = context_to_use[j + 1]
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
        
        # Optimized: type check once, use isinstance for performance
        container_type = type(container)
        if container_type is list:
            # Search in list items - optimized iteration
            for item in container:
                if isinstance(item, dict):
                    # Check direct match first (common case - optimized: single dict lookup)
                    item_value = item.get(key_field)
                    if item_value == ref_value:
                        return item
                    # Also search recursively in nested structures
                    result = self.search_for_node(item, key_field, ref_value)
                    if result is not None:
                        return result
        elif container_type is dict:
            # Check if container itself matches (fast path - optimized: single dict lookup)
            container_value = container.get(key_field)
            if container_value == ref_value:
                return container
            # Search in nested structures (optimized: iterate values directly)
            for value in container.values():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            # Check direct match first (optimized: single dict lookup)
                            item_value = item.get(key_field)
                            if item_value == ref_value:
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
    
    def _find_node_location_in_data(self, node: dict, search_context: List) -> List:
        """Find the location of a node in the data structure.
        
        Args:
            node: The node dict to find
            search_context: Context to start searching from (unused, but kept for API consistency)
            
        Returns:
            The context path where the node was found, or None
        """
        # Search recursively in the data structure
        # Start from root and search for the node
        root_data = self.evaluator.root_data
        if not root_data:
            return None
        
        # Use a helper to recursively search
        def search_recursive(data, path, target_node):
            if data is target_node or (isinstance(data, dict) and isinstance(target_node, dict) and 
                                      data == target_node):
                return path
            if isinstance(data, dict):
                for key, value in data.items():
                    result = search_recursive(value, path + [key], target_node)
                    if result:
                        return result
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    result = search_recursive(item, path + [i], target_node)
                    if result:
                        return result
            return None
        
        result_path = search_recursive(root_data, [], node)
        return result_path if result_path else None
    