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
    
    @contextmanager
    def _temporary_root_data(self, path: List):
        """Context manager for temporarily switching to root_data when needed.
        
        Args:
            path: Path that may require root_data navigation
        """
        old_data = self.evaluator.data
        try:
            if (path and isinstance(path[0], str) and
                isinstance(self.evaluator.data, dict) and
                path[0] not in self.evaluator.data and
                isinstance(self.evaluator.root_data, dict)):
                self.evaluator.data = self.evaluator.root_data
            yield
        finally:
            self.evaluator.data = old_data
    
    def _navigate_from_result(self, result: Any, remaining_path: str) -> Any:
        """Navigate a path from a predicate result.
        
        Args:
            result: Result from predicate (list or dict)
            remaining_path: Path to navigate from result
            
        Returns:
            Value at the navigated path, or None
        """
        if not remaining_path:
            return result
        
        if isinstance(result, list) and len(result) > 0:
            with self._temporary_context(result[0]):
                return self.evaluate_path(remaining_path)
        elif isinstance(result, dict):
            with self._temporary_context(result):
                return self.evaluate_path(remaining_path)
        return None
    
    def _evaluate_path_and_apply_predicate(self, path: str, predicate: Any, remaining_steps: List[str] = None) -> Any:
        """Evaluate a path, apply predicate if value is a list, then navigate remaining steps.
        
        Args:
            path: Path to evaluate
            predicate: Predicate to apply (if value is list)
            remaining_steps: Additional path steps to navigate after predicate
            
        Returns:
            Evaluated result after predicate and navigation
        """
        value = self.evaluate_path(path)
        if isinstance(value, list) and predicate:
            result = self._apply_predicate_to_value(value, predicate)
            if remaining_steps:
                remaining_path = '/'.join(remaining_steps)
                return self._navigate_from_result(result, remaining_path)
            return result
        return value
    
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
    
    def _should_use_root_data(self, parts: List, context_path: List) -> bool:
        """Determine if navigation should use root_data instead of current data.
        
        Args:
            parts: Path parts to navigate
            context_path: Current context path
            
        Returns:
            True if root_data should be used
        """
        if not (context_path and any(isinstance(p, int) for p in context_path) and
                len(parts) > 0 and isinstance(self.evaluator.root_data, dict)):
            return False
        
        # Check if path starts with context path prefix
        min_len = min(len(parts), len(context_path))
        if min_len == 0:
            return False
        
        path_matches_context = all(parts[i] == context_path[i] for i in range(min_len))
        if not path_matches_context:
            return False
        
        # Check if we can navigate from current data
        first_part = parts[0] if parts else None
        return not (first_part and isinstance(first_part, str) and
                   isinstance(self.evaluator.data, dict) and first_part in self.evaluator.data)
    
    def _adjust_parts_for_root_data(self, parts: List, context_path: List) -> List:
        """Adjust path parts when navigating from root_data.
        
        Args:
            parts: Original path parts
            context_path: Current context path
            
        Returns:
            Adjusted path parts for root_data navigation
        """
        # If root_data is at container level, skip first part if not in root_data
        if (parts and isinstance(parts[0], str) and parts[0] not in self.evaluator.root_data):
            return parts[1:]
        
        if len(parts) < len(context_path):
            # Path is a prefix of context_path
            if (context_path and isinstance(context_path[0], str) and
                context_path[0] not in self.evaluator.root_data):
                return context_path[1:len(parts)+1] if len(context_path) > 1 and len(parts) > 0 else []
        elif len(parts) > len(context_path):
            # Path extends beyond context_path
            remaining_parts = parts[len(context_path):]
            if (context_path and isinstance(context_path[0], str) and
                context_path[0] not in self.evaluator.root_data):
                return context_path[1:] + remaining_parts if len(context_path) > 1 else remaining_parts
            return remaining_parts
        
        return parts
    
    def get_path_value(self, parts: List) -> Any:
        """Get value at path in data structure.
        
        Args:
            parts: List of path parts (strings for dict keys, ints for list indices)
        """
        context_path = self.evaluator.context_path
        current = self.evaluator.data
        
        # Special case: when in a list item context and path was built from context_path,
        # navigate from root_data instead of evaluator.data
        if self._should_use_root_data(parts, context_path):
            current = self.evaluator.root_data
            parts = self._adjust_parts_for_root_data(parts, context_path)
        
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
        steps = list(node.steps)
        if steps and steps[0] == '..' and self.evaluator.context_path == []:
            # We're navigating from a node (empty context_path), so .. means stay here
            steps = steps[1:]
            if not steps:
                # Just .. with predicate - apply predicate to current data if it's a list
                if isinstance(self.evaluator.data, list):
                    return self._apply_predicate_to_value(self.evaluator.data, node.predicate)
                return None
        
        # Special case: if all steps are .., use _go_up_context_path
        if steps and all(step == '..' for step in steps):
            up_levels = len(steps)
            context_len = len(self.evaluator.context_path) if self.evaluator.context_path else 0
            if up_levels <= context_len:
                new_path = self._go_up_context_path(up_levels)
                with self._temporary_root_data(new_path):
                    value = self.get_path_value(new_path)
                    if isinstance(value, list) and node.predicate:
                        return self._apply_predicate_to_value(value, node.predicate)
                    return value
        
        # Try each step to find first that returns a list
        if steps:
            # Try first step first (most common case)
            result = self._evaluate_path_and_apply_predicate(
                steps[0], node.predicate, steps[1:] if len(steps) > 1 else None
            )
            if result is not None:
                return result
            
            # Try other steps if first didn't return a list
            for i in range(1, len(steps)):
                partial_path = '/'.join(steps[:i+1])
                result = self._evaluate_path_and_apply_predicate(
                    partial_path, node.predicate, steps[i+1:] if i+1 < len(steps) else None
                )
                if result is not None:
                    return result
        
        # No step returned a list, evaluate as normal path
        return self.evaluate_path('/'.join(node.steps))
    
    def _apply_predicate_to_value(self, value: List[Any], predicate: Any) -> Any:
        """Apply a predicate to a list value, handling both numeric and filter predicates.
        
        This method tries numeric index first (fast path), then falls back to filter.
        
        Args:
            value: List to apply predicate to
            predicate: Predicate AST node
            
        Returns:
            For numeric predicates: single element or None
            For filter predicates: filtered list
        """
        # Try numeric index first (fast path)
        numeric_result = self._apply_numeric_predicate(value, predicate)
        if numeric_result is not None:
            return numeric_result
        
        # Apply filter predicate
        return self._apply_predicate_to_list(value, predicate)
    
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
    
    def evaluate_path_node(self, node: PathNode) -> Any:
        """Evaluate a path node."""
        # Check for predicate with multiple steps first (before handling ..)
        if node.predicate and len(node.steps) > 1:
            return self._evaluate_path_with_predicate(node)
        
        # Handle relative paths with .. steps
        if node.steps and node.steps[0] == '..':
            up_levels = sum(1 for step in node.steps if step == '..')
            field_parts = [step for step in node.steps if step != '..']
            
            context_len = len(self.evaluator.context_path) if self.evaluator.context_path else 0
            if up_levels > 0 and context_len == 0 and isinstance(self.evaluator.data, dict):
                value = self.evaluator.data if not field_parts else self.get_path_value(field_parts)
            elif up_levels <= context_len:
                new_path = self._go_up_context_path(up_levels) + field_parts
                with self._temporary_root_data(new_path):
                    value = self.get_path_value(new_path)
            else:
                value = None
        elif node.is_absolute:
            value = self.evaluate_path('/' + '/'.join(node.steps))
        else:
            value = self.evaluate_path('/'.join(node.steps))
        
        # Apply predicate if present and value is a list
        if node.predicate and isinstance(value, list):
            return self._apply_predicate_to_value(value, node.predicate)
        
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
