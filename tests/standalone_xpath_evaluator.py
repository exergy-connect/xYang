#!/usr/bin/env python3
"""
Standalone XPath evaluator for testing complex expressions.

This is a minimal, self-contained implementation that can evaluate the expression:
"/data-model/consolidated = false() or deref(current())/../type = /data-model/entities[name = deref(current())/../foreignKey/entity]/fields[name = deref(current())/../foreignKey/field]/type"

Features implemented:
- Absolute paths (/data-model/...)
- Relative paths (../)
- deref() function (resolves leafrefs)
- current() function (returns original context)
- Predicates ([name = ...])
- Logical operators (or)
- Comparison operators (=)
- Boolean literals (false())
"""

from typing import Any, Dict, List, Optional, Union
import re

JsonValue = Union[Dict[str, Any], List[Any], str, int, float, bool, None]


class Context:
    """Context for XPath evaluation."""
    
    def __init__(
        self,
        data: JsonValue,
        context_path: List[str],
        original_context_path: List[str],
        original_data: JsonValue,
        root_data: JsonValue
    ):
        self.data = data
        self.context_path = context_path
        self.original_context_path = original_context_path
        self.original_data = original_data
        self.root_data = root_data
    
    def current(self) -> JsonValue:
        """Get the current value from the original context path."""
        if not self.original_context_path:
            return ""
        
        current = self.original_data
        for part in self.original_context_path:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and isinstance(part, int) and 0 <= part < len(current):
                current = current[part]
            else:
                return ""
        
        return current if current is not None else ""
    
    def with_data(self, data: JsonValue, context_path: Optional[List[str]] = None) -> 'Context':
        """Create a new context with different data."""
        return Context(
            data=data,
            context_path=context_path if context_path is not None else [],
            original_context_path=self.original_context_path,
            original_data=self.original_data,
            root_data=self.root_data
        )


class StandaloneXPathEvaluator:
    """Standalone XPath evaluator for testing."""
    
    def __init__(self, data: Dict[str, Any], context_path: Optional[List[str]] = None):
        self.root_data = data
        self.data = data
        self.context_path = context_path or []
        self.original_context_path = self.context_path.copy()
        self.original_data = data
        self.leafref_cache: Dict[str, Any] = {}
    
    def _create_context(self) -> Context:
        """Create a context object."""
        return Context(
            data=self.data,
            context_path=self.context_path,
            original_context_path=self.original_context_path,
            original_data=self.original_data,
            root_data=self.root_data
        )
    
    def evaluate(self, expression: str) -> bool:
        """Evaluate an XPath expression and return boolean result."""
        result = self.evaluate_value(expression)
        return self._to_bool(result)
    
    def evaluate_value(self, expression: str) -> JsonValue:
        """Evaluate an XPath expression and return the raw value."""
        context = self._create_context()
        return self._evaluate_expression(expression.strip(), context)
    
    def _evaluate_expression(self, expr: str, context: Context) -> JsonValue:
        """Evaluate an XPath expression."""
        expr = expr.strip()
        
        # Handle logical OR
        if ' or ' in expr:
            parts = self._split_logical_or(expr)
            for part in parts:
                result = self._evaluate_expression(part.strip(), context)
                if self._to_bool(result):
                    return True
            return False
        
        # Handle comparison operators
        if ' = ' in expr:
            left, right = expr.split(' = ', 1)
            left_val = self._evaluate_expression(left.strip(), context)
            right_val = self._evaluate_expression(right.strip(), context)
            return self._compare_equal(left_val, right_val)
        
        # Handle function calls
        if expr.endswith('()'):
            func_name = expr[:-2]
            if func_name == 'false':
                return False
            elif func_name == 'true':
                return True
            elif func_name == 'current':
                return context.current()
            else:
                raise ValueError(f"Unknown function: {func_name}()")
        
        # Handle paths that start with deref() followed by relative navigation
        # e.g., "deref(current())/../type"
        if 'deref(' in expr and '/../' in expr:
            return self._evaluate_deref_path(expr, context)
        
        # Handle absolute paths
        if expr.startswith('/'):
            return self._evaluate_absolute_path(expr, context)
        
        # Handle deref() function (standalone, without path navigation)
        if expr.startswith('deref(') and '/' not in expr:
            node, _ = self._evaluate_deref(expr, context)
            return node
        
        # Handle relative paths with ../
        if expr.startswith('../'):
            return self._evaluate_relative_path(expr, context)
        
        # Handle path navigation
        if '/' in expr or '[' in expr:
            return self._evaluate_path(expr, context)
        
        # Literal value
        return expr
    
    def _evaluate_deref_path(self, expr: str, context: Context) -> JsonValue:
        """Evaluate a path starting with deref() followed by relative navigation.
        
        Example: "deref(current())/../type"
        """
        # Find where deref() ends
        paren_count = 0
        deref_end = 0
        for i, char in enumerate(expr):
            if char == '(':
                paren_count += 1
            elif char == ')':
                paren_count -= 1
                if paren_count == 0:
                    deref_end = i + 1
                    break
        
        if deref_end == 0:
            raise ValueError(f"Invalid deref() expression: {expr}")
        
        # Extract deref expression and remaining path
        deref_expr = expr[:deref_end]
        remaining_path = expr[deref_end:].lstrip('/')
        
        # Evaluate deref to get the node and its path
        deref_node, node_path = self._evaluate_deref(deref_expr, context)
        
        if not isinstance(deref_node, dict) or not node_path:
            return None
        
        # Navigate relative to the node's location
        # For "../type", we go up one level from the node, then to "type"
        if remaining_path.startswith('../'):
            # Count ../ levels
            up_levels = 0
            path_after_up = remaining_path
            while path_after_up.startswith('../'):
                up_levels += 1
                path_after_up = path_after_up[3:]
            
            # Go up from node_path
            if up_levels > len(node_path):
                return None
            
            # Special case: if we're going up from a field and then accessing a property,
            # we might want to access the property from the field itself, not from the parent
            # But XPath semantics say ../ means parent, so let's follow that
            
            parent_path = node_path[:-up_levels] if up_levels > 0 else node_path
            parent_data = self._get_value_at_path(context.root_data, parent_path)
            
            # If path_after_up is empty, return parent
            if not path_after_up:
                return parent_data
            
            # Navigate the remaining path
            # Special case: if we're going up one level and then accessing a property,
            # and that property exists in the deref'd node itself, use it
            # This handles cases like deref(current())/../type where type is a property of the field
            if up_levels == 1 and path_after_up:
                parts = [p for p in path_after_up.split('/') if p]
                # First try from the deref'd node itself
                current = deref_node
                for part in parts:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    else:
                        break
                else:
                    # Successfully navigated from deref'd node
                    return current
                
                # If that didn't work, try from parent
                current = parent_data
                for part in parts:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    elif isinstance(current, list):
                        # Try to find by name
                        found = False
                        for item in current:
                            if isinstance(item, dict) and item.get('name') == part:
                                current = item
                                found = True
                                break
                        if not found:
                            return None
                    else:
                        return None
                return current
            else:
                # Navigate from parent
                parts = [p for p in path_after_up.split('/') if p]
                current = parent_data
                for part in parts:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    elif isinstance(current, list):
                        # Try to find by name
                        found = False
                        for item in current:
                            if isinstance(item, dict) and item.get('name') == part:
                                current = item
                                found = True
                                break
                        if not found:
                            return None
                    else:
                        return None
                return current
        else:
            # Navigate from the deref'd node itself
            parts = [p for p in remaining_path.split('/') if p]
            current = deref_node
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None
            return current
    
    def _split_logical_or(self, expr: str) -> List[str]:
        """Split expression by logical OR, respecting parentheses."""
        parts = []
        depth = 0
        current = []
        
        i = 0
        while i < len(expr):
            if expr[i] == '(':
                depth += 1
                current.append(expr[i])
            elif expr[i] == ')':
                depth -= 1
                current.append(expr[i])
            elif expr[i:i+4] == ' or ' and depth == 0:
                parts.append(''.join(current))
                current = []
                i += 3  # Skip ' or '
            else:
                current.append(expr[i])
            i += 1
        
        if current:
            parts.append(''.join(current))
        
        return parts
    
    def _evaluate_absolute_path(self, path: str, context: Context) -> JsonValue:
        """Evaluate an absolute path starting with /."""
        # Remove leading /
        path = path.lstrip('/')
        
        # Check for predicates
        if '[' in path:
            return self._evaluate_path_with_predicate(path, context, is_absolute=True)
        
        # Simple absolute path navigation
        parts = path.split('/')
        current = context.root_data
        
        for part in parts:
            if not part:
                continue
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list):
                # Try to find by index or by name field
                if part.isdigit():
                    idx = int(part)
                    if 0 <= idx < len(current):
                        current = current[idx]
                    else:
                        return None
                else:
                    # Look for item with matching name
                    for item in current:
                        if isinstance(item, dict) and item.get('name') == part:
                            current = item
                            break
                    else:
                        return None
            else:
                return None
        
        return current
    
    def _evaluate_relative_path(self, path: str, context: Context) -> JsonValue:
        """Evaluate a relative path starting with ../."""
        # Count ../ levels
        up_levels = 0
        remaining = path
        while remaining.startswith('../'):
            up_levels += 1
            remaining = remaining[3:]
        
        # Navigate up from original context path (for current() context)
        path_to_use = context.original_context_path if context.original_context_path else context.context_path
        if up_levels > len(path_to_use):
            return None
        
        # Go up the specified number of levels
        new_path = path_to_use[:-up_levels] if up_levels > 0 else path_to_use
        
        # Start from original_data
        current = context.original_data
        
        # Navigate to the parent using new_path
        for i, part in enumerate(new_path):
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and isinstance(part, int):
                if 0 <= part < len(current):
                    current = current[part]
                else:
                    return None
            else:
                return None
        
        # Navigate down the remaining path
        if remaining:
            parts = [p for p in remaining.split('/') if p]
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
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
    
    def _evaluate_deref(self, expr: str, context: Context) -> tuple:
        """Evaluate deref() function. Returns (node, path) tuple."""
        # Extract argument
        match = re.match(r'deref\((.*)\)', expr)
        if not match:
            raise ValueError(f"Invalid deref() expression: {expr}")
        
        arg = match.group(1).strip()
        
        # Evaluate the argument to get the leafref value
        leafref_value = self._evaluate_expression(arg, context)
        
        if not isinstance(leafref_value, str):
            return (None, None)
        
        # Cache key
        cache_key = f"deref:{leafref_value}"
        if cache_key in self.leafref_cache:
            cached = self.leafref_cache[cache_key]
            if isinstance(cached, tuple):
                return cached
            return (cached, None)
        
        # Resolve leafref: find the node where this value is used as a key
        # For entity names, look in /data-model/entities[name = value]
        # For field names, look in /data-model/entities/.../fields[name = value]
        
        # Try to find in entities
        if 'data-model' in self.root_data:
            entities = self.root_data['data-model'].get('entities', [])
            for entity_idx, entity in enumerate(entities):
                if isinstance(entity, dict) and entity.get('name') == leafref_value:
                    path = ['data-model', 'entities', entity_idx]
                    result = (entity, path)
                    self.leafref_cache[cache_key] = result
                    return result
                
                # Try fields
                fields = entity.get('fields', [])
                for field_idx, field in enumerate(fields):
                    if isinstance(field, dict) and field.get('name') == leafref_value:
                        path = ['data-model', 'entities', entity_idx, 'fields', field_idx]
                        result = (field, path)
                        self.leafref_cache[cache_key] = result
                        return result
        
        return (None, None)
    
    def _evaluate_path_with_predicate(self, path: str, context: Context, is_absolute: bool = False) -> JsonValue:
        """Evaluate a path with predicates like /data-model/entities[name = ...]/fields[...]."""
        # Split path into segments with predicates
        segments = []
        current_seg = []
        depth = 0
        in_predicate = False
        
        i = 0
        while i < len(path):
            char = path[i]
            if char == '[':
                if depth == 0:
                    # Start of predicate
                    segments.append(('path', ''.join(current_seg).strip('/')))
                    current_seg = []
                    in_predicate = True
                depth += 1
                current_seg.append(char)
            elif char == ']':
                depth -= 1
                current_seg.append(char)
                if depth == 0:
                    # End of predicate
                    predicate_expr = ''.join(current_seg)
                    segments.append(('predicate', predicate_expr[1:-1]))  # Remove [ and ]
                    current_seg = []
                    in_predicate = False
            else:
                current_seg.append(char)
            i += 1
        
        if current_seg:
            segments.append(('path', ''.join(current_seg).strip('/')))
        
        # Evaluate segments
        current = context.root_data if is_absolute else context.data
        current_path = [] if is_absolute else context.context_path.copy()
        
        i = 0
        while i < len(segments):
            seg_type, seg_value = segments[i]
            
            if seg_type == 'path':
                # Navigate the path
                parts = [p for p in seg_value.split('/') if p]
                for part in parts:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                        current_path.append(part)
                    elif isinstance(current, list):
                        # For lists, we need to wait for predicate to filter
                        pass
                    else:
                        return None
                
                # If next segment is a predicate, apply it
                if i + 1 < len(segments) and segments[i + 1][0] == 'predicate':
                    i += 1
                    continue
            elif seg_type == 'predicate':
                # Apply predicate to current list
                if isinstance(current, list):
                    filtered = []
                    for item in current:
                        # Create a context for this item
                        item_context = context.with_data(item, current_path + [len(filtered)])
                        # Evaluate predicate
                        pred_result = self._evaluate_expression(seg_value, item_context)
                        if self._to_bool(pred_result):
                            filtered.append(item)
                    
                    if filtered:
                        current = filtered[0] if len(filtered) == 1 else filtered
                    else:
                        return None
                else:
                    # Predicate on non-list - evaluate and check
                    pred_result = self._evaluate_expression(seg_value, context)
                    if not self._to_bool(pred_result):
                        return None
            
            i += 1
        
        return current
    
    def _evaluate_path(self, path: str, context: Context) -> JsonValue:
        """Evaluate a general path expression."""
        # Simple path navigation
        parts = path.split('/')
        current = context.data
        
        for part in parts:
            if not part:
                continue
            if '[' in part:
                # Has predicate
                base_part, pred_expr = part.split('[', 1)
                pred_expr = pred_expr.rstrip(']')
                
                if isinstance(current, dict) and base_part in current:
                    value = current[base_part]
                    if isinstance(value, list):
                        # Apply predicate
                        filtered = []
                        for item in value:
                            item_context = context.with_data(item, context.context_path + [base_part, len(filtered)])
                            if self._to_bool(self._evaluate_expression(pred_expr, item_context)):
                                filtered.append(item)
                        if filtered:
                            current = filtered[0] if len(filtered) == 1 else filtered
                        else:
                            return None
                    else:
                        current = value
                else:
                    return None
            else:
                if isinstance(current, dict) and part in current:
                    current = current[part]
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
    
    def _compare_equal(self, left: JsonValue, right: JsonValue) -> bool:
        """Compare two values for equality."""
        # Handle None/empty
        if left is None or left == "":
            return right is None or right == ""
        if right is None or right == "":
            return False
        
        # Type coercion for XPath
        if isinstance(left, bool) or isinstance(right, bool):
            return self._to_bool(left) == self._to_bool(right)
        
        return left == right
    
    def _find_node_path(self, node: Dict[str, Any], data: JsonValue, path: List[str] = None) -> Optional[List[str]]:
        """Find the path to a node in the data structure."""
        if path is None:
            path = []
        
        if data is node:
            return path
        
        if isinstance(data, dict):
            for key, value in data.items():
                result = self._find_node_path(node, value, path + [key])
                if result:
                    return result
        elif isinstance(data, list):
            for i, item in enumerate(data):
                result = self._find_node_path(node, item, path + [i])
                if result:
                    return result
        
        return None
    
    def _get_value_at_path(self, data: JsonValue, path: List[str]) -> JsonValue:
        """Get value at a specific path."""
        current = data
        for part in path:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and isinstance(part, int) and 0 <= part < len(current):
                current = current[part]
            else:
                return None
        return current
    
    def _to_bool(self, value: JsonValue) -> bool:
        """Convert value to boolean (XPath truthiness)."""
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, str):
            return len(value) > 0
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, (dict, list)):
            return len(value) > 0
        return bool(value)


def test_expression():
    """Test the complex XPath expression."""
    # Test data matching the test case
    test_data = {
        "data-model": {
            "consolidated": True,
            "entities": [
                {
                    "name": "parent",
                    "fields": [
                        {"name": "id", "type": "string"}
                    ]
                },
                {
                    "name": "child",
                    "fields": [
                        {
                            "name": "parent_id",
                            "type": "string",
                            "foreignKey": {
                                "entity": "parent",
                                "field": "id"
                            }
                        }
                    ],
                    "parents": [
                        {
                            "child_fk": "parent_id"
                        }
                    ]
                }
            ]
        }
    }
    
    # Context: child_fk leaf
    context_path = ["data-model", "entities", 1, "parents", 0, "child_fk"]
    
    evaluator = StandaloneXPathEvaluator(test_data, context_path)
    
    # The complex expression
    expression = (
        "/data-model/consolidated = false() or deref(current())/../type = " +
        "/data-model/entities[name = deref(current())/../foreignKey/entity]/fields[name = deref(current())/../foreignKey/field]/type"
    )
    
    print("Testing XPath expression:")
    print(f"  {expression}")
    print(f"\nContext path: {context_path}")
    print(f"Current value: {evaluator._create_context().current()}")
    
    try:
        result = evaluator.evaluate(expression)
        print(f"\nResult: {result}")
        
        # Step-by-step evaluation for debugging
        print("\n=== Step-by-step evaluation ===")
        context = evaluator._create_context()
        
        print(f"1. current() = {context.current()}")
        
        node, path = evaluator._evaluate_deref('deref(current())', context)
        print(f"2. deref(current()) = {node} (at path: {path})")
        
        print(f"3. deref(current())/../type = {evaluator._evaluate_expression('deref(current())/../type', context)}")
        
        print(f"4. deref(current())/../foreignKey/entity = {evaluator._evaluate_expression('deref(current())/../foreignKey/entity', context)}")
        
        print(f"5. /data-model/consolidated = false() = {evaluator._evaluate_expression('/data-model/consolidated = false()', context)}")
        
        return result
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    test_expression()
