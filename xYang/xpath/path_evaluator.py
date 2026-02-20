"""
Path evaluation logic for XPath expressions.
"""

from contextlib import contextmanager
from typing import Any, List, Optional, Tuple

from .ast import BinaryOpNode, LiteralNode, PathNode


class PathEvaluator:
    """Handles path evaluation in XPath expressions."""
    
    def __init__(self, evaluator: Any):
        """Initialize path evaluator with reference to main evaluator.
        
        Args:
            evaluator: The main XPathEvaluator instance
        """
        self.evaluator = evaluator
    
    @contextmanager
    def _temporary_context(self, data: Any, context_path: Optional[List] = None):
        """Context manager for temporarily setting evaluator data and context.
        
        Args:
            data: Data to set as evaluator.data
            context_path: Context path to set (defaults to empty list)
        """
        old_data = self.evaluator.data
        old_context = self.evaluator.context_path
        try:
            self.evaluator.data = data if isinstance(data, dict) else {'value': data}
            self.evaluator._set_context_path(context_path if context_path is not None else [])
            yield
        finally:
            self.evaluator.data = old_data
            self.evaluator._set_context_path(old_context)
    
    def _navigate_from_result(self, result: Any, remaining_path: str) -> Any:
        """Navigate a path from a predicate result.
        
        Args:
            result: Result from predicate (list or dict)
            remaining_path: Path to navigate from result
            
        Returns:
            Value at the navigated path, or None
        """
        if isinstance(result, list) and len(result) > 0:
            with self._temporary_context(result[0]):
                return self.evaluate_path(remaining_path)
        elif isinstance(result, dict):
            with self._temporary_context(result):
                return self.evaluate_path(remaining_path)
        return None
    
    def _apply_predicate_to_list(self, items: List[Any], predicate_node: Any) -> List[Any]:
        """Apply a predicate node to a list of items.
        
        Args:
            items: List of items to filter
            predicate_node: Predicate AST node to evaluate
            
        Returns:
            Filtered list of items
        """
        from .utils import yang_bool
        
        filtered = []
        for item in items:
            with self._temporary_context(item):
                try:
                    pred_result = predicate_node.evaluate(self.evaluator)
                    if yang_bool(pred_result):
                        filtered.append(item)
                except Exception:
                    # If predicate evaluation fails, skip this item
                    pass
        return filtered
    
    def _find_matching_bracket(self, path: str, start_idx: int) -> Optional[int]:
        """Find the matching closing bracket for a predicate.
        
        Args:
            path: Path string
            start_idx: Index of opening bracket
            
        Returns:
            Index of matching closing bracket, or None if not found
        """
        depth = 1
        idx = start_idx + 1
        while idx < len(path) and depth > 0:
            if path[idx] == '[':
                depth += 1
            elif path[idx] == ']':
                depth -= 1
            idx += 1
        return idx - 1 if depth == 0 else None
    
    def _parse_predicate_path(self, path: str) -> Optional[Tuple[str, str, str]]:
        """Parse a path with predicate into base, predicate, and remaining parts.
        
        Args:
            path: Path string potentially containing predicate
            
        Returns:
            Tuple of (base_path, predicate, remaining_path) or None if no predicate
        """
        bracket_idx = path.find('[')
        if bracket_idx < 0:
            return None
        
        bracket_end = self._find_matching_bracket(path, bracket_idx)
        if bracket_end is None:
            return None
        
        base_path = path[:bracket_idx]
        predicate = path[bracket_idx:bracket_end + 1]
        remaining_path = path[bracket_end + 1:].lstrip('/')
        return (base_path, predicate, remaining_path)
    
    def _go_up_context_path(self, up_levels: int) -> List:
        """Navigate up the context path by the specified number of levels.
        
        Handles list indices properly:
        - For leaf-list elements: removes both the index and the leaf-list name together
          (because the indexed value is a scalar, not a container)
        - For list elements: removes only the index (leaving the list name, which is
          the list entry container)
        
        Args:
            up_levels: Number of levels to go up
            
        Returns:
            New context path after going up
        """
        new_path = list(self.evaluator.context_path)
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
        if not hasattr(self.evaluator, 'module') or not self.evaluator.module:
            return False
        
        try:
            from ..ast import YangLeafListStmt
            
            # Convert data path to schema path (remove indices)
            schema_path = [p for p in path_to_list if not isinstance(p, int)]
            
            # Navigate schema to find the node
            statements = self.evaluator.module.statements
            for step in schema_path:
                found = False
                for stmt in statements:
                    if hasattr(stmt, 'name') and stmt.name == step:
                        if isinstance(stmt, YangLeafListStmt):
                            return True
                        elif hasattr(stmt, 'statements'):
                            statements = stmt.statements
                            found = True
                            break
                if not found:
                    return False
            return False
        except Exception:
            return False
    
    def evaluate_path(self, path: str) -> Any:
        """Evaluate a path expression."""
        # Handle current node
        if path in ('.', 'current()'):
            val = self.evaluator._get_current_value()
            if val is not None:
                return val
        
        # Handle relative paths starting with ./
        if path.startswith('./'):
            remaining = path[2:]
            if not remaining:
                return self.evaluator._get_current_value()
            parts = remaining.split('/')
            return self.get_path_value(self.evaluator.context_path + parts)
        
        # Handle relative paths with ..
        if path.startswith('../'):
            return self.evaluate_relative_path(path)
        
        # Handle absolute paths
        if path.startswith('/'):
            return self.evaluate_absolute_path(path)
        
        # Handle paths with predicates
        parsed = self._parse_predicate_path(path)
        if parsed:
            base_path, predicate, remaining_path = parsed
            value = self.evaluate_path(base_path)
            if isinstance(value, list):
                result = self.evaluator.predicate_evaluator.apply_predicate(value, predicate)
                if remaining_path:
                    return self._navigate_from_result(result, remaining_path)
                return result
            return value
        
        # Simple field access - build path from context
        if '/' not in path:
            full_path = list(self.evaluator.context_path) + [path]
            return self.get_path_value(full_path)
        
        # Path with slashes
        parts = path.split('/')
        return self.get_path_value(list(self.evaluator.context_path) + parts)
    
    def evaluate_relative_path(self, path: str) -> Any:
        """Evaluate a relative path like ../field or ../../field."""
        if path == '..':
            up_levels, field_parts = 1, []
        else:
            parts = path.split('/')
            up_levels = sum(1 for p in parts if p == '..')
            field_parts = [p for p in parts if p and p != '..']
        
        context_len = self.evaluator._context_path_len
        
        # Special case: at node level (empty context_path)
        if up_levels > 0 and context_len == 0 and isinstance(self.evaluator.data, dict):
            if len(field_parts) == 1:
                return self.evaluator.data.get(field_parts[0])
            return self.get_path_value(field_parts)
        
        # Navigate up the context path
        if up_levels <= context_len:
            new_path = self._go_up_context_path(up_levels) + field_parts
            value = self.get_path_value(new_path)
            if value is not None:
                return value
        
        # Try from root if we need to go beyond context
        if up_levels > context_len:
            remaining_up = up_levels - context_len
            if remaining_up == 1 and field_parts:
                return self.evaluator._get_path_value(field_parts)
        
        return None
    
    def evaluate_absolute_path(self, path: str) -> Any:
        """Evaluate an absolute path like /data-model/entities."""
        path = path.lstrip('/')
        parts = path.split('/')
        
        old_data = self.evaluator.data
        try:
            self.evaluator.data = self.evaluator.root_data
            return self.get_path_value(parts)
        finally:
            self.evaluator.data = old_data
    
    def get_path_value(self, parts: List) -> Any:
        """Get value at path in data structure.
        
        Args:
            parts: List of path parts (strings for dict keys, ints for list indices)
        """
        current = self.evaluator.data
        
        for part in parts:
            if part in ('.', 'current()'):
                continue
            
            # Handle integer list indices
            if isinstance(part, int):
                if isinstance(current, list) and 0 <= part < len(current):
                    current = current[part]
                else:
                    return None
                continue
            
            # Handle predicates in path parts
            if isinstance(part, str):
                bracket_idx = part.find('[')
                if bracket_idx >= 0:
                    base_part = part[:bracket_idx]
                    predicate = part[bracket_idx:]
                    if isinstance(current, dict) and base_part in current:
                        value = current[base_part]
                        if isinstance(value, list):
                            return self.evaluator.predicate_evaluator.apply_predicate(value, predicate)
                        return value
                    return None
            
            # Navigate through dict or list
            if isinstance(current, dict):
                if part in current:
                    current = current[part]
                else:
                    return None
            elif isinstance(current, list):
                if part.isdigit():
                    idx = int(part)
                    if 0 <= idx < len(current):
                        current = current[idx]
                    else:
                        return None
                else:
                    return None
            else:
                return None
        
        return current
    
    def _evaluate_path_with_predicate(self, node: PathNode) -> Any:
        """Evaluate a path node that has a predicate with multiple steps.
        
        The predicate might be on the last step (due to parser merging),
        but should apply to the first step that returns a list.
        
        Args:
            node: PathNode with predicate and multiple steps
            
        Returns:
            Evaluated result
        """
        # Handle paths starting with .. when navigating from a node
        # In this case, .. means "stay at current node", so we skip it
        steps = list(node.steps)
        if steps and steps[0] == '..' and self.evaluator.context_path == []:
            # We're navigating from a node (empty context_path), so .. means stay here
            steps = steps[1:]
            if not steps:
                # Just .. with predicate - apply predicate to current data if it's a list
                if isinstance(self.evaluator.data, list):
                    return self._apply_predicate_to_list(self.evaluator.data, node.predicate)
                return None
        
        # Try first step first (most common case)
        if steps:
            first_value = self.evaluate_path(steps[0])
            if isinstance(first_value, list):
                # Check if predicate is numeric (index) or filter
                numeric_result = self._apply_numeric_predicate(first_value, node.predicate)
                if numeric_result is not None:
                    # Numeric predicate returned a single element
                    remaining_steps = steps[1:]
                    if remaining_steps:
                        return self._navigate_from_result(numeric_result, '/'.join(remaining_steps))
                    return numeric_result
                # Filter predicate - apply to list
                filtered = self._apply_predicate_to_list(first_value, node.predicate)
                remaining_steps = steps[1:]
                if remaining_steps:
                    return self._navigate_from_result(filtered, '/'.join(remaining_steps))
                return filtered
            
            # Try other steps if first didn't return a list
            for i in range(1, len(steps)):
                partial_path = '/'.join(steps[:i+1])
                partial_value = self.evaluate_path(partial_path)
                if isinstance(partial_value, list):
                    # Check if predicate is numeric (index) or filter
                    numeric_result = self._apply_numeric_predicate(partial_value, node.predicate)
                    if numeric_result is not None:
                        # Numeric predicate returned a single element
                        remaining_steps = steps[i+1:]
                        if remaining_steps:
                            return self._navigate_from_result(numeric_result, '/'.join(remaining_steps))
                        return numeric_result
                    # Filter predicate - apply to list
                    filtered = self._apply_predicate_to_list(partial_value, node.predicate)
                    remaining_steps = steps[i+1:]
                    if remaining_steps:
                        return self._navigate_from_result(filtered, '/'.join(remaining_steps))
                    return filtered
        
        # No step returned a list, evaluate as normal path
        path = '/'.join(node.steps)
        return self.evaluate_path(path)
    
    def _apply_numeric_predicate(self, value: List[Any], predicate: Any) -> Optional[Any]:
        """Apply a numeric index predicate to a list.
        
        Args:
            value: List to index into
            predicate: Predicate node (should be LiteralNode with numeric value)
            
        Returns:
            Element at index, or None if invalid
        """
        if isinstance(predicate, LiteralNode):
            try:
                idx = int(predicate.value) - 1  # XPath is 1-indexed
                if 0 <= idx < len(value):
                    return value[idx]
            except (ValueError, TypeError):
                pass
        else:
            # Check string representation
            pred_str = str(predicate)
            if pred_str.startswith('[') and pred_str.endswith(']'):
                pred_expr = pred_str[1:-1]
                if pred_expr.isdigit():
                    idx = int(pred_expr) - 1
                    if 0 <= idx < len(value):
                        return value[idx]
        return None
    
    def _apply_filter_predicate(self, value: List[Any], predicate: Any) -> List[Any]:
        """Apply a filter predicate to a list.
        
        Args:
            value: List to filter
            predicate: Predicate AST node
            
        Returns:
            Filtered list
        """
        return self._apply_predicate_to_list(value, predicate)
    
    def evaluate_path_node(self, node: PathNode) -> Any:
        """Evaluate a path node."""
        # Check for predicate with multiple steps first (before handling ..)
        if node.predicate and len(node.steps) > 1:
            value = self._evaluate_path_with_predicate(node)
            # _evaluate_path_with_predicate already applies the predicate, so return directly
            return value
        
        # Handle relative paths with .. steps
        if node.steps and node.steps[0] == '..':
            up_levels = sum(1 for step in node.steps if step == '..')
            field_parts = [step for step in node.steps if step != '..']
            
            context_len = self.evaluator._context_path_len
            if up_levels > 0 and context_len == 0 and isinstance(self.evaluator.data, dict):
                if not field_parts:
                    value = self.evaluator.data
                else:
                    value = self.get_path_value(field_parts)
            elif up_levels <= context_len:
                new_path = self._go_up_context_path(up_levels) + field_parts
                value = self.get_path_value(new_path)
            else:
                value = None
        elif node.is_absolute:
            path = '/' + '/'.join(node.steps)
            value = self.evaluate_path(path)
        else:
            path = '/'.join(node.steps)
            value = self.evaluate_path(path)
        
        # Apply predicate if present and value is a list
        if node.predicate and isinstance(value, list):
            # Try numeric index first (fast path)
            numeric_result = self._apply_numeric_predicate(value, node.predicate)
            if numeric_result is not None:
                return numeric_result
            
            # Apply filter predicate
            return self._apply_filter_predicate(value, node.predicate)
        
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
