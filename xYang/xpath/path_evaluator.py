"""
Path evaluation logic for XPath expressions.
"""

from typing import Any, List, Optional

from .ast import BinaryOpNode, LiteralNode, PathNode
from .parser import XPathTokenizer, XPathParser
from .context import Context


class PathEvaluator:
    """Handles path evaluation in XPath expressions."""
    
    def __init__(self, evaluator: Any):
        """Initialize path evaluator with reference to main evaluator.
        
        Args:
            evaluator: The main XPathEvaluator instance
        """
        self.evaluator = evaluator
    
    
    
    def _navigate_from_result(self, result: Any, remaining_path: str, context: Context) -> Any:
        """Navigate a path from a predicate result.
        
        Args:
            result: Result from predicate (list)
            remaining_path: Path to navigate from result
            
        Returns:
            Value at the navigated path, or None
        """
        # If predicate returned empty list, no match found - return empty list
        # This allows the constraint to evaluate to False (no match)
        if not result or len(result) == 0:
            return []
        # Create new context with result[0] as data
        item_data = result[0] if isinstance(result[0], dict) else {'value': result[0]}
        new_context = context.with_data(item_data, [])
        return self.evaluate_path(remaining_path, new_context)
    
    def _evaluate_path_and_apply_predicate(self, path: str, predicate: Any, context: Context, remaining_steps: List[str] = None) -> Any:
        """Evaluate a path, apply predicate if value is a list, then navigate remaining steps.
        
        Args:
            path: Path to evaluate
            predicate: Predicate to apply (if value is list)
            context: Context for evaluation
            remaining_steps: Additional path steps to navigate after predicate
            
        Returns:
            Evaluated result after predicate and navigation
        """
        value = self.evaluate_path(path, context)
        if isinstance(value, list) and predicate:
            result = self._apply_predicate_to_value(value, predicate, context)
            if remaining_steps:
                remaining_path = '/'.join(remaining_steps)
                return self._navigate_from_result(result, remaining_path, context)
            return result
        return value
    
    def _apply_predicate_to_list(self, items: List[Any], predicate_node: Any, context: Context) -> List[Any]:
        """Apply a predicate node to a list of items.
        
        Args:
            items: List of items to filter
            predicate_node: Predicate AST node to evaluate
            context: Context for evaluation
            
        Returns:
            Filtered list of items
        """
        from .utils import yang_bool
        
        filtered = []
        for item in items:
            # Create new context for the item being tested (so paths like 'name' evaluate from the item)
            # Preserve original_context_path and original_data for current()
            item_data = item if isinstance(item, dict) else {'value': item}
            item_context = context.with_data(item_data, [])
            
            pred_result = predicate_node.evaluate(self.evaluator, item_context)
            if yang_bool(pred_result):
                filtered.append(item)
        
        return filtered
    
    
    def _go_up_context_path(self, context_path: List, up_levels: int) -> List:
        """Navigate up the context path by the specified number of levels.
        
        Handles list indices properly:
        - For leaf-list elements: removes both the index and the leaf-list name together
          (because the indexed value is a scalar, not a container)
        - For list elements: when going up from a list item, removes both the index and
          the list name to get to the parent container (YANG semantics: .. from list item
          goes to parent of list, not the list itself)
        - Exception: when the parent of a list is also a list item (nested lists), we need
          to be more careful. From entities[1]/fields[1], going up should remove fields[1]
          to get to entities[1], not remove both fields and entities.
        
        Args:
            context_path: Current context path to navigate from
            up_levels: Number of levels to go up
            
        Returns:
            New context path after going up
        """
        new_path = list(context_path)
        for _ in range(up_levels):
            if not new_path:
                break
            removed = new_path.pop()
            # If it was a list index (int), check if the parent is a leaf-list or a list
            if isinstance(removed, int) and len(new_path) > 0:
                # Get the name of the list/leaf-list (the element before the index)
                list_name = new_path[-1] if new_path else None
                if list_name and isinstance(list_name, str):
                    # Check if this is a leaf-list in the schema
                    is_leaf_list = self._is_leaf_list_in_schema(new_path)
                    if is_leaf_list:
                        # For leaf-list: remove both the index (already removed) and the name
                        # because the indexed value is a scalar, not a container
                        new_path.pop()
                    # For regular lists: keep the list name (it represents the list entry container)
                    # The index has already been removed, so we're done
            # If it was a string (list/container name), we've removed it and are at parent
        return new_path
    
    def _is_leaf_list_in_schema(self, path_to_list: List) -> bool:
        """Check if the schema node at the given path is a leaf-list.
        
        Args:
            path_to_list: Path to the list/leaf-list node (without the index)
            
        Returns:
            True if the node is a leaf-list, False if it's a regular list or not found
        """
        if not self.evaluator.module:
            return False
        
        from ..ast import YangLeafListStmt
        
        # Convert data path to schema path (remove indices)
        schema_path = [p for p in path_to_list if not isinstance(p, int)]
        
        # Navigate schema to find the node
        statements = self.evaluator.module.statements
        for step in schema_path:
            for stmt in statements:
                if hasattr(stmt, 'name') and stmt.name == step:
                    if isinstance(stmt, YangLeafListStmt):
                        return True
                    if hasattr(stmt, 'statements'):
                        statements = stmt.statements
                        break
        return False
    
    def evaluate_path(self, path: str, context: Context) -> Any:
        """Evaluate a path expression.
        
        Args:
            path: Path expression to evaluate
            context: Context for evaluation
        """
        # Handle current node - but distinguish between . and current()
        if path == 'current()':
            return context.current()
        if path == '.':
            # . means the current context node/value
            # If data is a primitive value, return it directly
            if isinstance(context.data, (str, int, float, bool)):
                return context.data
            # If data is a dict and context_path is empty, check if it's a wrapped value
            if isinstance(context.data, dict) and not context.context_path:
                # If it's a wrapped value (from predicate evaluator), return the value
                if 'value' in context.data and len(context.data) == 1:
                    return context.data['value']
                return context.data
            # Get value from current context path or fallback to current()
            return self.get_path_value(context.context_path, context) if context.context_path else context.current()
        
        # Handle relative paths with ..
        if path.startswith('../'):
            return self.evaluate_relative_path(path, context)
        
        # Handle absolute paths
        if path.startswith('/'):
            return self.evaluate_absolute_path(path, context)
        
        # Simple field access - try direct access first, then build path from context
        if '/' not in path:
            # First, try to access the field directly from context.data
            # This handles the case where context.data is set to a list item (e.g., entity dict)
            if isinstance(context.data, dict) and path in context.data:
                return context.data[path]
            # Fall back to building path from context
            full_path = list(context.context_path) + [path]
            return self.get_path_value(full_path, context)
        
        # Path with slashes - try direct access first for first part
        # Parse path parts, handling predicates that may contain '/' characters
        parts = self._parse_path_parts(path)
        if parts and isinstance(context.data, dict) and parts[0] in context.data:
            # Start from current data and navigate remaining parts
            current = context.data[parts[0]]
            for part in parts[1:]:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                elif isinstance(current, list) and part.isdigit():
                    idx = int(part)
                    if 0 <= idx < len(current):
                        current = current[idx]
                    else:
                        return None
                else:
                    return None
            return current
        # Fall back to building path from context
        return self.get_path_value(list(context.context_path) + parts, context)
    
    def evaluate_relative_path(self, path: str, context: Context) -> Any:
        """Evaluate a relative path like ../field or ../../field.
        
        Args:
            path: Relative path to evaluate
            context: Context for evaluation
        """
        # Parse path parts, handling predicates that may contain '/' characters
        parts = self._parse_path_parts(path)
        up_levels = sum(1 for p in parts if p == '..')
        field_parts = [p for p in parts if p and p != '..']
        
        context_len = len(context.context_path) if context.context_path else 0
        
        # Navigate up the context path
        if up_levels <= context_len:
            # When navigating from a list item context, we need to use root_data
            # because the path is relative to the context path, not the current data
            # Use root_data for navigation when we have a context path
            nav_context = context
            if context_len > 0 and isinstance(context.root_data, dict):
                nav_context = context.with_data(context.root_data, context.context_path)
            
            # Try going up the specified number of levels
            new_path = self._go_up_context_path(context.context_path, up_levels) + field_parts
            result = self.get_path_value(new_path, nav_context)
            
            # If that didn't work, try two fallback strategies:
            # 1. Try going up one more semantic level by removing the list name
            #    (YANG semantics: .. from list item goes to parent of list, not the list itself)
            if result is None and field_parts and len(new_path) > len(field_parts):
                # new_path includes field_parts at the end, so we need to remove field_parts first
                # to get the base path, then remove the list name, then re-add field_parts
                base_path = new_path[:-len(field_parts)] if len(field_parts) > 0 else new_path
                if len(base_path) > 0 and isinstance(base_path[-1], str):
                    # Remove the list name and re-add field_parts
                    new_path_alt = base_path[:-1] + field_parts
                    result_alt = self.get_path_value(new_path_alt, nav_context)
                    if result_alt is not None:
                        return result_alt
            
            # 2. Try going up fewer levels (in case we went up too far)
            # But only if the first fallback didn't work and we're sure we need to go up less
            # (Don't try this if we already tried removing the list name)
            if result is None and field_parts and up_levels > 1:
                # Only try going up one less level, not all the way down to 0
                # This prevents finding wrong paths that happen to exist
                alt_levels = up_levels - 1
                new_path_alt = self._go_up_context_path(context.context_path, alt_levels) + field_parts
                result_alt = self.get_path_value(new_path_alt, nav_context)
                # Only use this result if it's a list (for field access) or matches expected type
                if result_alt is not None:
                    return result_alt
            
            return result
        
        return None
    
    def evaluate_absolute_path(self, path: str, context: Context) -> Any:
        """Evaluate an absolute path like /data-model/entities.
        
        Args:
            path: Absolute path to evaluate
            context: Context for evaluation
        """
        # Parse path parts, handling predicates that may contain '/' characters
        parts = self._parse_path_parts(path.lstrip('/'))
        nav_context = context.with_data(context.root_data, [])
        return self.get_path_value(parts, nav_context)
    
    def _parse_path_parts(self, path: str) -> List[str]:
        """Parse a path string into parts, handling predicates that may contain '/' characters.
        
        Predicates are enclosed in brackets and may contain path expressions with '/',
        so we need to track bracket depth to avoid splitting on '/' inside predicates.
        
        Args:
            path: Path string to parse (without leading '/')
            
        Returns:
            List of path parts, with predicates preserved in their parts
        """
        if not path:
            return []
        
        parts = []
        current_part = []
        bracket_depth = 0
        i = 0
        
        while i < len(path):
            char = path[i]
            
            if char == '[':
                bracket_depth += 1
                current_part.append(char)
            elif char == ']':
                bracket_depth -= 1
                current_part.append(char)
            elif char == '/' and bracket_depth == 0:
                # Only split on '/' when we're not inside a predicate
                if current_part:
                    parts.append(''.join(current_part))
                    current_part = []
            else:
                current_part.append(char)
            
            i += 1
        
        # Add the last part
        if current_part:
            parts.append(''.join(current_part))
        
        return parts
    
    def _should_use_root_data(self, parts: List, context: Context) -> bool:
        """Determine if navigation should use root_data instead of current data.
        
        Args:
            parts: Path parts to navigate
            context: Context for evaluation
            
        Returns:
            True if root_data should be used
        """
        context_path = context.context_path
        if not (context_path and any(isinstance(p, int) for p in context_path) and
                len(parts) > 0 and isinstance(context.root_data, dict)):
            return False
        
        # Check if path starts with context path prefix
        min_len = min(len(parts), len(context_path))
        path_matches_context = all(parts[i] == context_path[i] for i in range(min_len))
        if not path_matches_context:
            return False
        
        # Check if we can navigate from current data
        first_part = parts[0] if parts else None
        return not (first_part and isinstance(first_part, str) and
                   isinstance(context.data, dict) and first_part in context.data)
    
    def _adjust_parts_for_root_data(self, parts: List, context_path: List) -> List:
        """Adjust path parts when navigating from root_data.
        
        Args:
            parts: Original path parts
            context_path: Current context path
            
        Returns:
            Adjusted path parts for root_data navigation
        """
        if len(parts) > len(context_path):
            return parts[len(context_path):]
        return parts
    
    def get_path_value(self, parts: List, context: Context) -> Any:
        """Get value at path in data structure.
        
        Args:
            parts: List of path parts (strings for dict keys, ints for list indices)
            context: Context for evaluation
        """
        context_path = context.context_path
        current = context.data
        
        # Special case: when in a list item context and path was built from context_path,
        # navigate from root_data instead of context.data
        if self._should_use_root_data(parts, context):
            current = context.root_data
            parts = self._adjust_parts_for_root_data(parts, context_path)
        elif (context_path and 
              isinstance(context.data, dict) and 
              context.data is not context.root_data and
              len(parts) > 0 and 
              isinstance(parts[0], str)):
            # If we're in a list item context and the path doesn't start with context_path,
            # we need to navigate from root_data using the full path
            # Check if the first part of parts matches the context_path
            if not (len(parts) > 0 and len(context_path) > 0 and parts[0] == context_path[0]):
                # Path doesn't start with context_path, so navigate from root_data
                current = context.root_data
        
        for part in parts:
            # Handle integer list indices
            if isinstance(part, int):
                if isinstance(current, list) and 0 <= part < len(current):
                    current = current[part]
                else:
                    return None
                continue
            
            # Handle predicates in path parts using AST parser
            if isinstance(part, str) and '[' in part:
                # Parse the path part as a path expression to check if it has a predicate
                tokenizer = XPathTokenizer(part)
                tokens = tokenizer.tokenize()
                parser = XPathParser(tokens, part)
                # Try to parse as a path expression (which handles predicates)
                parsed_node = parser.parse()
                
                # Check if this is a PathNode with a predicate
                if isinstance(parsed_node, PathNode) and parsed_node.predicate is not None:
                    # Extract base part (first step) and use predicate AST node directly
                    base_part = parsed_node.steps[0] if parsed_node.steps else part
                    
                    if isinstance(current, dict) and base_part in current:
                        value = current[base_part]
                        if isinstance(value, list):
                            # Apply predicate AST node directly (no string conversion)
                            filtered = self.evaluator.predicate_evaluator.apply_predicate(value, parsed_node.predicate, context)
                            # If there are more parts to navigate, continue from the filtered result
                            if filtered is not None and parts.index(part) < len(parts) - 1:
                                # Get remaining parts after this one
                                remaining_parts = parts[parts.index(part) + 1:]
                                # If filtered is a list, navigate from first item
                                if isinstance(filtered, list) and len(filtered) > 0:
                                    # Update current to the first filtered item and continue loop
                                    current = filtered[0]
                                    # Continue to next iteration to process remaining parts
                                    continue
                                # If filtered is a single item, navigate from it
                                elif filtered is not None:
                                    current = filtered
                                    # Continue to next iteration to process remaining parts
                                    continue
                            # No more parts, return the filtered result
                            return filtered
                        return value
                    return None
            
            # Navigate through dict or list
            if isinstance(current, dict):
                if part in current:
                    current = current[part]
                else:
                    # Path not found - try to get default value from schema
                    # This handles YANG default values when a leaf is not present in data
                    default_value = self._get_default_value_from_schema_path(parts[:parts.index(part)+1] if isinstance(parts, list) and part in parts else parts + [part])
                    if default_value is not None:
                        return default_value
                    return None
            elif isinstance(current, list) and part.isdigit():
                idx = int(part)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None
            else:
                return None
        
        return current
    
    def _evaluate_path_with_predicate(self, node: PathNode, context: Context) -> Any:
        """Evaluate a path node that has a predicate with multiple steps.
        
        The predicate should apply to the final list in the path, not intermediate lists.
        We try the complete path first, then fall back to trying individual steps.
        
        Args:
            node: PathNode with predicate and multiple steps
            context: Context for evaluation
            
        Returns:
            Evaluated result
        """
        # Handle paths starting with .. when navigating from a node
        steps = list(node.steps)
        if steps and steps[0] == '..' and context.context_path == []:
            steps = steps[1:]
        
        # Special case: if all steps are .., use _go_up_context_path
        if steps and all(step == '..' for step in steps):
            up_levels = len(steps)
            context_len = len(context.context_path) if context.context_path else 0
            if up_levels <= context_len:
                new_path = self._go_up_context_path(context.context_path, up_levels)
                nav_context = context.with_data(context.root_data, context.context_path)
                value = self.get_path_value(new_path, nav_context)
                if isinstance(value, list) and node.predicate:
                    return self._apply_predicate_to_value(value, node.predicate, context)
                return value
        
        # Try the complete path first (predicate should apply to the final list)
        if steps:
            complete_path = '/'.join(steps)
            value = self.evaluate_path(complete_path, context)
            if isinstance(value, list) and node.predicate:
                # Predicate applies to the complete path result
                return self._apply_predicate_to_value(value, node.predicate, context)
            elif value is not None:
                # Complete path worked but result is not a list - return it
                return value
            
            # Fall back to trying individual steps if complete path didn't work
            # Try first step first (most common case)
            result = self._evaluate_path_and_apply_predicate(
                steps[0], node.predicate, context, steps[1:] if len(steps) > 1 else None
            )
            if result is not None:
                return result
            
            # Try other steps if first didn't return a list
            for i in range(1, len(steps)):
                partial_path = '/'.join(steps[:i+1])
                result = self._evaluate_path_and_apply_predicate(
                    partial_path, node.predicate, context, steps[i+1:] if i+1 < len(steps) else None
                )
                if result is not None:
                    return result
        
        return self.evaluate_path('/'.join(node.steps), context)
    
    def _apply_predicate_to_value(self, value: List[Any], predicate: Any, context: Context) -> Any:
        """Apply a predicate to a list value, handling both numeric and filter predicates.
        
        This method tries numeric index first (fast path), then falls back to filter.
        
        Args:
            value: List to apply predicate to
            predicate: Predicate AST node
            context: Context for evaluation
            
        Returns:
            For numeric predicates: single element or None
            For filter predicates: filtered list
        """
        numeric_result = self._apply_numeric_predicate(value, predicate)
        if numeric_result is not None:
            return numeric_result
        return self._apply_predicate_to_list(value, predicate, context)
    
    def _apply_numeric_predicate(self, value: List[Any], predicate: Any) -> Optional[Any]:
        """Apply a numeric index predicate to a list.
        
        Args:
            value: List to index into
            predicate: Predicate node (should be LiteralNode with numeric value)
            
        Returns:
            Element at index, or None if invalid
        """
        if not isinstance(predicate, LiteralNode):
            return None
        idx = int(predicate.value) - 1  # XPath is 1-indexed
        if 0 <= idx < len(value):
            return value[idx]
        return None
    
    def evaluate_path_node(self, node: PathNode, context: Context) -> Any:
        """Evaluate a path node.
        
        Args:
            node: Path node to evaluate
            context: Context for evaluation
        """
        # Check for predicate with multiple steps first (before handling ..)
        if node.predicate and len(node.steps) > 1:
            return self._evaluate_path_with_predicate(node, context)
        
        # Handle relative paths with .. steps
        if node.steps and node.steps[0] == '..':
            up_levels = sum(1 for step in node.steps if step == '..')
            field_parts = [step for step in node.steps if step != '..']
            
            context_len = len(context.context_path) if context.context_path else 0
            if up_levels <= context_len:
                # Try going up the specified number of levels
                new_path = self._go_up_context_path(context.context_path, up_levels) + field_parts
                # Use root_data for navigation when we have a context path
                nav_context = context
                if context_len > 0 and isinstance(context.root_data, dict):
                    nav_context = context.with_data(context.root_data, context.context_path)
                value = self.get_path_value(new_path, nav_context)
                
                # If that didn't work, try two fallback strategies:
                # 1. Try going up one more semantic level by removing the list name
                #    (YANG semantics: .. from list item goes to parent of list, not the list itself)
                if value is None and field_parts and len(new_path) > len(field_parts):
                    # new_path includes field_parts at the end, so we need to remove field_parts first
                    # to get the base path, then remove the list name, then re-add field_parts
                    base_path = new_path[:-len(field_parts)] if len(field_parts) > 0 else new_path
                    if len(base_path) > 0 and isinstance(base_path[-1], str):
                        # Remove the list name and re-add field_parts
                        new_path_alt = base_path[:-1] + field_parts
                        value_alt = self.get_path_value(new_path_alt, nav_context)
                        if value_alt is not None:
                            value = value_alt
                
                # 2. Try going up fewer levels (in case we went up too far)
                # But only if the first fallback didn't work
                # (Don't try this if we already tried removing the list name)
                if value is None and field_parts and up_levels > 1:
                    # Only try going up one less level, not all the way down to 0
                    # This prevents finding wrong paths that happen to exist
                    alt_levels = up_levels - 1
                    new_path_alt = self._go_up_context_path(context.context_path, alt_levels) + field_parts
                    value_alt = self.get_path_value(new_path_alt, nav_context)
                    # Only use this result if it's not None
                    if value_alt is not None:
                        value = value_alt
            else:
                value = None
        else:
            path = '/' + '/'.join(node.steps) if node.is_absolute else '/'.join(node.steps)
            value = self.evaluate_path(path, context)
        
        # Apply predicate if present and value is a list
        if node.predicate and isinstance(value, list):
            return self._apply_predicate_to_value(value, node.predicate, context)
        
        return value
    
    def extract_path_from_binary_op(self, node: Any) -> List:
        """Extract path steps from a nested BinaryOpNode tree with / operators.
        
        Returns a list that can contain strings (path steps) or PathNode objects.
        """
        steps = []
        
        def traverse(n):
            if isinstance(n, PathNode):
                steps.extend(n.steps)
            elif isinstance(n, BinaryOpNode) and n.operator == '/':
                traverse(n.left)
                traverse(n.right)
            elif hasattr(n, 'evaluate'):
                steps.append(n)
        
        traverse(node)
        return steps
    
    def _get_default_value_from_schema_path(self, path_parts: List) -> Any:
        """Get default value from YANG schema for a given path.
        
        Args:
            path_parts: List of path parts (e.g., ['data-model', 'max_name_underscores'])
            
        Returns:
            Default value from schema, or None if not found or no default
        """
        if not self.evaluator.module:
            return None
        
        try:
            # Navigate through schema to find the leaf
            current = self.evaluator.module
            for part in path_parts:
                if isinstance(part, int):
                    continue  # Skip list indices in schema navigation
                if hasattr(current, 'statements'):
                    found = False
                    for stmt in current.statements:
                        if hasattr(stmt, 'name') and stmt.name == part:
                            current = stmt
                            found = True
                            break
                    if not found:
                        return None
                else:
                    return None
            
            # Check if current statement has a default value
            if hasattr(current, 'default'):
                value = current.default
                # Convert string numbers to int/float
                if isinstance(value, str):
                    try:
                        if '.' in value:
                            return float(value)
                        return int(value)
                    except ValueError:
                        return value
                return value
            # Also check statements for default keyword
            if hasattr(current, 'statements'):
                for stmt in current.statements:
                    if hasattr(stmt, 'keyword') and stmt.keyword == 'default' and hasattr(stmt, 'value'):
                        value = stmt.value
                        # Convert string numbers to int/float
                        if isinstance(value, str):
                            try:
                                return float(value) if '.' in value else int(value)
                            except ValueError:
                                return value
                        return value
            return None
        except (AttributeError, IndexError, ValueError):
            return None