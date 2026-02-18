"""
Path evaluation logic for XPath expressions.
"""

from typing import Any, List

from .ast import PathNode, BinaryOpNode


class PathEvaluator:
    """Handles path evaluation in XPath expressions."""
    
    def __init__(self, evaluator: Any):
        """Initialize path evaluator with reference to main evaluator.
        
        Args:
            evaluator: The main XPathEvaluator instance
        """
        self.evaluator = evaluator
    
    def evaluate_path(self, path: str) -> Any:
        """Evaluate a path expression."""
        # Handle current node
        if path == '.' or path == 'current()':
            val = self.evaluator._get_current_value()
            if val is not None:
                return val

        # Handle relative paths starting with ./
        if path.startswith('./'):
            # Remove leading ./ and evaluate relative to current context
            remaining_path = path[2:]  # Remove './'
            if remaining_path:
                # Build path from current context
                parts = remaining_path.split('/')
                full_path = self.evaluator.context_path + parts
                return self.get_path_value(full_path)
            else:
                # Just './' means current node
                return self.evaluator._get_current_value()

        # Handle relative paths
        if path.startswith('../'):
            return self.evaluate_relative_path(path)

        # Handle absolute paths
        if path.startswith('/'):
            return self.evaluate_absolute_path(path)

        # Handle filtering [predicate] - use find() instead of index() to avoid exceptions
        bracket_idx = path.find('[')
        if bracket_idx >= 0:
            base_path = path[:bracket_idx]
            predicate = path[bracket_idx:]
            value = self.evaluate_path(base_path)
            if isinstance(value, list):
                return self.evaluator.predicate_evaluator.apply_predicate(value, predicate)
            return value

        # Simple field access - cache split result if path is simple
        if '/' not in path:
            return self.get_path_value([path])
        return self.get_path_value(path.split('/'))
    
    def evaluate_relative_path(self, path: str) -> Any:
        """Evaluate a relative path like ../field or ../../field."""
        # Optimized: avoid split if path is simple
        if path == '..':
            up_levels = 1
            field_parts = []
        else:
            # Optimized: single pass through path string
            parts = path.split('/')
            up_levels = 0
            field_parts = []
            for part in parts:
                if part == '..':
                    up_levels += 1
                elif part:
                    field_parts.append(part)

        # Special case: if we're at a node level (context_path is empty) and path starts with ..,
        # treat it as direct field access (the .. is a quirk of YANG path syntax)
        # This handles: deref(../entity)/../fields where we're already at the entity node
        context_len = self.evaluator._context_path_len
        if up_levels > 0 and context_len == 0 and isinstance(self.evaluator.data, dict):
            # We're at a node, and path wants to go up then down
            # In this case, just access the field directly from the node
            if len(field_parts) == 1:
                # Simple case: ../field means just access 'field' from current node
                return self.evaluator.data.get(field_parts[0])
            # Multi-level: ../fields/field means access fields.field from current node
            return self.get_path_value(field_parts)

        # Navigate up the context path - use cached length
        context_len = self.evaluator._context_path_len
        if up_levels <= context_len:
            new_path = self.evaluator.context_path[:-up_levels] + field_parts
            value = self.get_path_value(new_path)
            if value is not None:
                return value

        # If we need to go up beyond context, try from root data
        # Save current data and try from root
        if up_levels > context_len:
            # We need to go to root - get root data from module if available
            # For now, try to navigate from current data's root
            remaining_up = up_levels - context_len
            if remaining_up == 1 and field_parts:
                # We're at root, get the field
                # Try to get root data - if we have module, use it to find root
                root_data = self.evaluator.data
                # Navigate up to find root (go up remaining_up levels)
                for _ in range(remaining_up - 1):
                    # This is a simplification - in full implementation would track root
                    pass
                return self.evaluator._get_path_value(field_parts)

        return None

    def evaluate_absolute_path(self, path: str) -> Any:
        """Evaluate an absolute path like /data-model/entities."""
        # Remove leading /
        path = path.lstrip('/')
        parts = path.split('/')
        
        # Use root_data for absolute paths
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
        parts_len = len(parts)

        for i, part in enumerate(parts):
            if part == '.' or part == 'current()':
                continue

            # Handle integer list indices - optimized type check
            if isinstance(part, int):
                if isinstance(current, list):
                    if 0 <= part < len(current):
                        current = current[part]
                    else:
                        return None
                else:
                    return None
                continue

            # Handle filtering - use find() instead of index()
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

            # Optimized: type check once, then access
            if isinstance(current, dict):
                if part in current:
                    current = current[part]
                else:
                    return None
            elif isinstance(current, list):
                # Check if part is numeric before calling isdigit()
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
    
    def evaluate_path_node(self, node: PathNode) -> Any:
        """Evaluate a path node."""
        # Handle relative paths with .. steps
        if node.steps and node.steps[0] == '..':
            # This is a relative path, evaluate it directly
            # Optimized: single pass through steps
            up_levels = 0
            field_parts = []
            for step in node.steps:
                if step == '..':
                    up_levels += 1
                else:
                    field_parts.append(step)

            # Special case: if we're at a node level (context_path is empty) and path starts with ..,
            # treat it as direct field access or return current node if no fields
            context_len = self.evaluator._context_path_len
            if up_levels > 0 and context_len == 0 and isinstance(self.evaluator.data, dict):
                if len(field_parts) == 0:
                    # Just ".." means stay at current node
                    return self.evaluator.data
                # ../field means access 'field' from current node
                return self.get_path_value(field_parts)

            # Navigate up the context path - use cached length
            context_len = self.evaluator._context_path_len
            if up_levels <= context_len:
                new_path = self.evaluator.context_path[:-up_levels] + field_parts
                value = self.get_path_value(new_path)
            else:
                value = None
        elif node.is_absolute:
            # Absolute path
            path = '/' + '/'.join(node.steps)
            value = self.evaluate_path(path)
        else:
            # Simple relative path without ..
            path = '/'.join(node.steps)
            value = self.evaluate_path(path)

        # Apply predicate if present
        if node.predicate and isinstance(value, list):
            # Check if it's a simple index predicate like [1]
            pred_str = str(node.predicate)
            if pred_str.startswith('[') and pred_str.endswith(']'):
                pred_expr = pred_str[1:-1]
                # Handle simple numeric index
                if pred_expr.isdigit():
                    idx = int(pred_expr) - 1  # XPath is 1-indexed
                    if 0 <= idx < len(value):
                        return value[idx]  # Return element directly
                    return None
            
            # For other predicates, evaluate for each item (filtering)
            filtered = []
            for item in value:
                # Evaluate predicate in context of item
                old_data = self.evaluator.data
                old_context = self.evaluator.context_path
                self.evaluator.data = item if isinstance(item, dict) else {'value': item}
                self.evaluator._set_context_path([])

                try:
                    pred_result = node.predicate.evaluate(self.evaluator)
                    from .utils import yang_bool
                    if yang_bool(pred_result):
                        filtered.append(item)
                finally:
                    self.evaluator.data = old_data
                    self.evaluator.context_path = old_context

            return filtered

        return value
    
    def extract_path_from_binary_op(self, node: Any) -> List:
        """Extract path steps from a nested BinaryOpNode tree with / operators.
        
        Returns a list that can contain strings (path steps) or PathNode objects.
        """
        from .ast import BinaryOpNode, PathNode
        steps = []
        
        def traverse(n):
            if isinstance(n, PathNode):
                # Add all steps from the path node
                steps.extend(n.steps)
            elif isinstance(n, BinaryOpNode) and n.operator == '/':
                # Recursively traverse left and right
                traverse(n.left)
                traverse(n.right)
            elif hasattr(n, 'evaluate'):
                # For other nodes, we'll evaluate them in context
                # For now, add the node itself so we can evaluate it later
                steps.append(n)
        
        traverse(node)
        return steps
