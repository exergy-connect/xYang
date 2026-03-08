"""
Path evaluation logic for XPath expressions.
"""

from typing import Any, List, Optional, Union

from .ast import BinaryOpNode, LiteralNode, PathNode, PathSegment, CurrentNode
from ..ast import YangLeafStmt, YangContainerStmt, YangListStmt, YangChoiceStmt
from .parser import XPathTokenizer, XPathParser
from .context import Context


class PathEvaluator:
    """Handles path evaluation in XPath expressions.

    Path strings are parsed once into an AST (PathNode), then evaluation walks
    the AST only; no re-parsing of path parts or predicates.
    """
    
    def __init__(self, evaluator: Any):
        """Initialize path evaluator with reference to main evaluator.
        
        Args:
            evaluator: The main XPathEvaluator instance
        """
        self.evaluator = evaluator
        self._path_ast_cache: dict = {}  # path_str -> PathNode/CurrentNode, for parse-once
    
    
    
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
        new_context = context.for_item(result[0])
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
            item_context = context.for_item(item)
            
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
                    else:
                        # For regular lists: YANG semantics say .. from list item goes to parent of list
                        # So we should remove both the index (already removed) and the list name
                        # This applies even when the parent is a list item (nested lists)
                        # From entities[1]/fields[1], going up from fields[1] removes both
                        # the index (1) and the list name (fields) to get to entities[1]
                        new_path.pop()
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

    def _parse_path_expression(self, path: str) -> Any:
        """Parse a path string once into an AST (PathNode or CurrentNode)."""
        if len(path) < 80 and path in self._path_ast_cache:
            return self._path_ast_cache[path]
        try:
            tokenizer = XPathTokenizer(path)
            tokens = tokenizer.tokenize()
            parser = XPathParser(tokens, expression=path)
            node = parser.parse()
            if len(path) < 80:
                self._path_ast_cache[path] = node
            return node
        except Exception:
            return None

    def _evaluate_path_ast(self, node: Any, context: Context) -> Any:
        """Evaluate a path AST node (PathNode or CurrentNode) without re-parsing."""
        if isinstance(node, PathNode):
            return self.evaluate_path_node(node, context)
        if isinstance(node, CurrentNode):
            return node.evaluate(self.evaluator, context)
        if node is not None and hasattr(node, 'evaluate'):
            return node.evaluate(self.evaluator, context)
        return None

    def evaluate_path(self, path: str, context: Context) -> Any:
        """Evaluate a path expression. Parses the path once, then walks the AST."""
        node = self._parse_path_expression(path)
        if node is None:
            return None
        return self._evaluate_path_ast(node, context)
    def evaluate_relative_path(self, path: str, context: Context) -> Any:
        """Evaluate a relative path. Parses once, then walks AST."""
        node = self._parse_path_expression(path)
        return self._evaluate_path_ast(node, context) if node is not None else None

    def evaluate_absolute_path(self, path: str, context: Context) -> Any:
        """Evaluate an absolute path. Parses once (path must start with /), then walks AST."""
        node = self._parse_path_expression(path) if path else None
        return self._evaluate_path_ast(node, context) if node is not None else None
    
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
        
        # Check if path starts with context path prefix (compare step names)
        min_len = min(len(parts), len(context_path))
        path_matches_context = all(
            self._step_from_part(parts[i]) == context_path[i] for i in range(min_len)
        )
        if not path_matches_context:
            return False
        first_step = self._step_from_part(parts[0]) if parts else None
        return not (first_step and isinstance(first_step, str) and
                    isinstance(context.data, dict) and first_step in context.data)
    
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
    
    def _step_from_part(self, part: Any) -> str:
        """Return the step name for navigation (string)."""
        return part.step if isinstance(part, PathSegment) else part

    def get_path_value(self, parts: List, context: Context, predicate_context: Context = None) -> Any:
        """Get value at path in data structure.

        Args:
            parts: List of path parts: strings (step names), ints (list indices),
                   or PathSegment (step + optional predicate AST). No re-parsing.
            context: Context for evaluation
            predicate_context: Optional context for predicate evaluation
        """
        pred_ctx = predicate_context if predicate_context is not None else context
        context_path = context.context_path
        current = context.data

        if self._should_use_root_data(parts, context):
            current = context.root_data
            parts = self._adjust_parts_for_root_data(parts, context_path)
        elif (context_path and
              isinstance(context.data, dict) and
              context.data is not context.root_data and
              len(parts) > 0):
            first_step = self._step_from_part(parts[0])
            if isinstance(first_step, str) and first_step and (
                    (len(context_path) > 0 and first_step == context_path[0]) or
                    first_step not in context.data):
                current = context.root_data

        for i, part in enumerate(parts):
            if isinstance(part, int):
                if isinstance(current, list) and 0 <= part < len(current):
                    current = current[part]
                else:
                    return None
                continue

            step = self._step_from_part(part)
            step_pred = part.predicate if isinstance(part, PathSegment) else None

            if isinstance(current, dict):
                if step in current:
                    value = current[step]
                    if step_pred is not None and isinstance(value, list):
                        filtered = self.evaluator.predicate_evaluator.apply_predicate(
                            value, step_pred, pred_ctx)
                        if filtered is None or (isinstance(filtered, list) and len(filtered) == 0):
                            return None
                        current = filtered[0] if isinstance(filtered, list) else filtered
                        if i < len(parts) - 1:
                            continue
                        if self._is_empty_type_leaf_at_path(parts[:i + 1]):
                            return True
                        return current
                    current = value
                    continue
                else:
                    schema_path = [self._step_from_part(p) for p in parts[:i + 1]
                                 if not isinstance(p, int)]
                    default_value = self._get_default_value_from_schema_path(schema_path)
                    if default_value is not None:
                        return default_value
                    return None
            elif isinstance(current, list):
                if isinstance(step, str) and step.isdigit():
                    idx = int(step)
                    if 0 <= idx < len(current):
                        current = current[idx]
                    else:
                        return None
                else:
                    collected = []
                    for item in current:
                        if isinstance(item, dict) and step in item:
                            value = item[step]
                            if isinstance(value, list):
                                collected.extend(value)
                            else:
                                collected.append(value)
                    if collected and i < len(parts) - 1:
                        current = collected[0] if len(collected) == 1 else collected[0]
                    else:
                        result = collected if len(collected) > 1 else (collected[0] if collected else None)
                        if result is not None and self._is_empty_type_leaf_at_path(parts[:i + 1]):
                            return True
                        return result
                    continue
            else:
                return None

        if self._is_empty_type_leaf_at_path(parts):
            return True
        return current

    def _is_empty_type_leaf_at_path(self, path_parts: List) -> bool:
        """Return True if the schema leaf at path_parts has type empty."""
        if not self.evaluator.module or not path_parts:
            return False
        schema_path = [self._step_from_part(p) for p in path_parts if not isinstance(p, int)]
        if not schema_path:
            return False
        statements = self.evaluator.module.statements
        for i, part in enumerate(schema_path):
            if not isinstance(part, str):
                continue
            found = None
            for stmt in statements:
                if hasattr(stmt, 'name') and stmt.name == part:
                    found = stmt
                    break
            if found is None:
                return False
            if isinstance(found, YangLeafStmt):
                return (
                    i == len(schema_path) - 1
                    and hasattr(found, 'type')
                    and found.type
                    and getattr(found.type, 'name', None) == 'empty'
                )
            if isinstance(found, YangListStmt) and hasattr(found, 'statements'):
                statements = found.statements
            elif isinstance(found, YangContainerStmt) and hasattr(found, 'statements'):
                statements = found.statements
            elif isinstance(found, YangChoiceStmt) and hasattr(found, 'cases'):
                statements = []
                for case in found.cases:
                    if hasattr(case, 'statements'):
                        statements.extend(case.statements)
            else:
                return False
        return False

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
        segments = list(node.segments)
        if segments and segments[0].step == '..' and context.context_path == []:
            segments = segments[1:]
        
        # Special case: if all steps are .., use _go_up_context_path
        if segments and all(seg.step == '..' for seg in segments):
            up_levels = len(segments)
            context_len = len(context.context_path) if context.context_path else 0
            if up_levels <= context_len:
                new_path = self._go_up_context_path(context.context_path, up_levels)
                nav_context = context.with_data(context.root_data, context.context_path)
                value = self.get_path_value(new_path, nav_context)
                return value
        
        # Try the complete path first (predicate should apply to the final list)
        if segments:
            complete_path = '/'.join(seg.step for seg in segments)
            value = self.evaluate_path(complete_path, context)
            if value is not None:
                # Complete path worked but result is not a list - return it
                return value
            
        
        return self.evaluate_path('/'.join(seg.step for seg in node.segments), context)
    
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
        pred_value = int(predicate.value)
        # Handle [0] as 0-based indexing for convenience, [1] and above as 1-based (XPath standard)
        if pred_value == 0:
            idx = 0
        else:
            idx = pred_value - 1  # XPath is 1-indexed
        if 0 <= idx < len(value):
            return value[idx]
        return None
    
    def evaluate_path_node(self, node: PathNode, context: Context) -> Any:
        """Evaluate a path node.
        
        Args:
            node: Path node to evaluate
            context: Context for evaluation
        """
        # Handle relative paths with .. steps
        if node.segments and node.segments[0].step == '..':
            up_levels = sum(1 for seg in node.segments if seg.step == '..')
            # Get non-.. segments, preserving predicates
            field_segments = [seg for seg in node.segments if seg.step != '..']
            field_parts = [seg.step for seg in field_segments]
            
            # Use original_context_path if context_path is empty (e.g., in predicates)
            # This ensures relative paths in predicates work from the original constraint location
            path_to_use = context.context_path if context.context_path else context.original_context_path
            context_len = len(path_to_use) if path_to_use else 0
            if up_levels <= context_len:
                # Try going up the specified number of levels
                new_path = self._go_up_context_path(path_to_use, up_levels)
                # Use root_data for navigation when we have a context path
                nav_context = context
                if context_len > 0 and isinstance(context.root_data, dict):
                    nav_context = context.with_data(context.root_data, path_to_use)
                
                # If we went past the root (empty path), handle it specially
                if not new_path:
                    if field_segments:
                        value = self.get_path_value(field_segments, nav_context, predicate_context=context)
                        if value is None and isinstance(context.root_data, dict) and len(context.root_data) == 1:
                            top_level_key = list(context.root_data.keys())[0]
                            value = self.get_path_value([top_level_key] + field_segments, nav_context, predicate_context=context)
                    else:
                        value = context.root_data
                else:
                    value = self.get_path_value(new_path + field_segments, nav_context, predicate_context=context)
                
                # If that didn't work, try two fallback strategies:
                # 1. Try going up one more semantic level by removing the list name
                if value is None and field_segments and len(new_path) > len(field_segments):
                    base_path = new_path[:-len(field_segments)] if field_segments else new_path
                    if len(base_path) > 0 and isinstance(base_path[-1], str):
                        new_path_alt = base_path[:-1] + field_segments
                        value_alt = self.get_path_value(new_path_alt, nav_context, predicate_context=context)
                        if value_alt is not None:
                            value = value_alt
                # 2. Try going up fewer levels (in case we went up too far)
                if value is None and field_segments and up_levels > 1:
                    alt_levels = up_levels - 1
                    new_path_alt = self._go_up_context_path(path_to_use, alt_levels) + field_segments
                    value_alt = self.get_path_value(new_path_alt, nav_context, predicate_context=context)
                    if value_alt is not None:
                        value = value_alt
            else:
                value = None
        else:
            # Check if any segments have predicates
            has_segment_predicates = any(seg.predicate is not None for seg in node.segments)
            
            if has_segment_predicates:
                # We have predicates on intermediate steps - evaluate step by step
                if node.is_absolute:
                    nav_context = context.with_data(context.root_data, [])
                    value = self._evaluate_path_with_segments(node.segments, None, nav_context, context)
                else:
                    value = self._evaluate_path_with_segments(node.segments, None, context, context)
            else:
                # No segment predicates - walk AST segments only (no path string, no re-parse)
                if node.is_absolute:
                    nav_context = context.with_data(context.root_data, [])
                    value = self.get_path_value(node.segments, nav_context, predicate_context=context)
                else:
                    value = self.get_path_value(node.segments, context)
        
        return value
    
    def _evaluate_path_with_segments(self, segments: List[Any], final_predicate: Any, nav_context: Context, predicate_context: Context) -> Any:
        """Evaluate path segments with predicates on intermediate steps.
        
        Args:
            segments: List of PathSegment objects, each with an optional predicate
            final_predicate: Final predicate to apply (if any)
            nav_context: Context for navigation
            predicate_context: Context for predicate evaluation (preserves original context)
        """
        from .ast import PathSegment
        
        current = nav_context.data
        current_context = nav_context
        
        for segment in segments:
            if not isinstance(segment, PathSegment):
                # Fallback for backward compatibility
                step = segment if isinstance(segment, str) else segment.step
                step_pred = None
            else:
                step = segment.step
                step_pred = segment.predicate
            
            # Navigate to the step
            if isinstance(current, dict) and step in current:
                value = current[step]
                # If this step has a predicate and value is a list, apply it
                if step_pred is not None and isinstance(value, list):
                    filtered = self.evaluator.predicate_evaluator.apply_predicate(value, step_pred, predicate_context)
                    if filtered is None or (isinstance(filtered, list) and len(filtered) == 0):
                        return None
                    # If this is the last segment, return the full filtered list
                    # Otherwise, take the first item to continue navigation
                    is_last_segment = (segment == segments[-1])
                    if isinstance(filtered, list):
                        if is_last_segment:
                            # Last segment with predicate - return the full filtered list
                            return filtered
                        else:
                            # Not the last segment - take first item to continue navigation
                            current = filtered[0] if len(filtered) > 0 else None
                    else:
                        current = filtered
                    if current is None:
                        return None
                else:
                    current = value
                current_context = current_context.with_data(current, [])
            elif isinstance(current, list) and step.isdigit():
                idx = int(step)
                if 0 <= idx < len(current):
                    current = current[idx]
                    current_context = current_context.with_data(current, [])
                else:
                    return None
            else:
                return None
        
        # Apply final predicate if present
        if final_predicate and isinstance(current, list):
            return self._apply_predicate_to_value(current, final_predicate, predicate_context)
        
        return current
    
    def _evaluate_path_steps_with_predicates(self, steps: List[str], final_predicate: Any, nav_context: Context, predicate_context: Context) -> Any:
        """Evaluate path steps one by one, applying predicates at list steps.
        
        Args:
            steps: List of path steps
            final_predicate: Predicate to apply at the end (if any)
            nav_context: Context for navigation
            predicate_context: Context for predicate evaluation (preserves original context)
            
        Returns:
            Evaluated result
        """
        current = nav_context.data
        current_context = nav_context
        
        for i, step in enumerate(steps):
            # Check if this step has a predicate (e.g., "entities[name = ...]")
            if '[' in step and ']' in step:
                # Parse the step to extract base name and predicate
                bracket_start = step.find('[')
                base_step = step[:bracket_start]
                predicate_str = step[bracket_start:]
                
                # Navigate to the list
                if isinstance(current, dict) and base_step in current:
                    value = current[base_step]
                    if isinstance(value, list):
                        # Parse and evaluate the predicate
                        from .parser import XPathTokenizer, XPathParser
                        tokenizer = XPathTokenizer(predicate_str)
                        tokens = tokenizer.tokenize()
                        parser = XPathParser(tokens, predicate_str)
                        predicate_ast = parser.parse()
                        
                        # Apply predicate to filter the list
                        filtered = self.evaluator.predicate_evaluator.apply_predicate(value, predicate_ast, predicate_context)
                        
                        # Continue navigation from filtered result
                        if filtered is None or (isinstance(filtered, list) and len(filtered) == 0):
                            return None
                        if isinstance(filtered, list):
                            current = filtered[0] if len(filtered) > 0 else None
                        else:
                            current = filtered
                        if current is None:
                            return None
                        # Update context for next step
                        current_context = predicate_context.with_data(current, [])
                        continue
                    current = value
                else:
                    return None
            else:
                # Regular step navigation
                if isinstance(current, dict) and step in current:
                    current = current[step]
                    current_context = current_context.with_data(current, [])
                elif isinstance(current, list) and step.isdigit():
                    idx = int(step)
                    if 0 <= idx < len(current):
                        current = current[idx]
                        current_context = current_context.with_data(current, [])
                    else:
                        return None
                else:
                    return None
        
        # Apply final predicate if present and value is a list
        if final_predicate and isinstance(current, list):
            return self._apply_predicate_to_value(current, final_predicate, predicate_context)
        
        return current
    
    def extract_path_from_binary_op(self, node: Any) -> List:
        """Extract path steps from a nested BinaryOpNode tree with / operators.
        
        Returns a list that can contain strings (path steps) or PathNode objects.
        """
        steps = []
        
        def traverse(n):
            if isinstance(n, PathNode):
                # Extract step names from segments
                steps.extend(seg.step for seg in n.segments)
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