"""
Minimal XPath evaluator for YANG must/when expressions.

Implements only the XPath features used in meta-model.yang:
- Path navigation (../, ../../, etc.)
- Functions: string-length(), translate(), count(), deref(), current(), not(), true(), false(), bool()
- Comparisons: =, !=, <=, >=, <, >
- Logical operators: or, and
- Filtering: [predicate]
- String concatenation: +
"""

from typing import Any, Dict, List

from .parser import XPathTokenizer, XPathParser
from .ast import PathNode, FunctionCallNode, BinaryOpNode, UnaryOpNode
from ..errors import XPathSyntaxError


class XPathEvaluator:
    """Minimal XPath evaluator for YANG expressions."""

    def __init__(self, data: Dict[str, Any], module: Any, context_path: List[str] = None):
        """
        Initialize evaluator.
        
        Args:
            data: The data instance being validated
            module: The YANG module (for schema resolution)
            context_path: Current path in the data structure (for current() and relative paths)
        """
        self.data = data
        self.root_data = data  # Store root data for absolute path resolution
        self.module = module
        self.context_path = context_path or []
        self.original_context_path = context_path or []  # Preserve original context for current()
        self.original_data = data  # Preserve original data for current()
        self.leafref_cache: Dict[str, Any] = {}  # Cache for deref() results

    def evaluate(self, expression: str) -> bool:
        """Evaluate an XPath expression and return boolean result."""
        try:
            result = self.evaluate_value(expression)
            # Convert to boolean
            if isinstance(result, bool):
                return result
            if isinstance(result, (int, float)):
                return bool(result)
            if isinstance(result, str):
                return bool(result)
            return False
        except XPathSyntaxError:
            # Re-raise syntax errors
            raise
        except Exception as e:
            # For other errors, raise a more specific exception
            from ..errors import XPathEvaluationError
            raise XPathEvaluationError(f"XPath evaluation failed: {e}") from e

    def evaluate_value(self, expression: str) -> Any:
        """Evaluate an XPath expression and return the raw value."""
        try:
            # Parse expression into AST
            tokenizer = XPathTokenizer(expression)
            tokens = tokenizer.tokenize()
            parser = XPathParser(tokens, expression=expression)
            ast = parser.parse()

            # Evaluate AST
            return ast.evaluate(self)
        except XPathSyntaxError:
            # Re-raise syntax errors
            raise
        except Exception as e:
            # For other errors, raise a more specific exception
            from ..errors import XPathEvaluationError
            raise XPathEvaluationError(f"XPath evaluation failed: {e}") from e


    def _evaluate_function_node(self, node: FunctionCallNode) -> Any:
        """Evaluate a function call node."""
        func_name = node.name

        # For count, we need to evaluate the path node directly to get the filtered list
        if func_name == 'count':
            if len(node.args) == 1:
                arg_node = node.args[0]
                # If it's a path node, evaluate it directly
                if isinstance(arg_node, PathNode):
                    path_value = self._evaluate_path_node(arg_node)
                    if isinstance(path_value, list):
                        return len(path_value)
                    return 0
                # Otherwise evaluate normally
                arg_value = arg_node.evaluate(self)
                if isinstance(arg_value, list):
                    return len(arg_value)
                return 0

        # For deref(), we need the path expression, not the evaluated value
        if func_name == 'deref':
            if len(node.args) == 1:
                arg_node = node.args[0]
                # Extract path string from PathNode before evaluating
                if isinstance(arg_node, PathNode):
                    # It's a PathNode - build path string from steps
                    if arg_node.is_absolute:
                        path = '/' + '/'.join(arg_node.steps)
                    else:
                        path = '/'.join(arg_node.steps)
                else:
                    # Evaluate to get the path value, then use as path string
                    arg_value = arg_node.evaluate(self) if hasattr(arg_node, 'evaluate') else str(arg_node)
                    path = str(arg_value) if arg_value is not None else ''
                return self._evaluate_deref(path)
            return None

        # For other functions, evaluate arguments normally
        args = [arg.evaluate(self) for arg in node.args]

        if func_name == 'string-length':
            if len(args) == 1:
                return len(str(args[0] or ''))

        elif func_name == 'translate':
            if len(args) == 3:
                source = str(args[0] or '')
                from_chars = str(args[1] or '').strip("'\"")
                to_chars = str(args[2] or '').strip("'\"")
                result = source
                # In XPath translate(), if to_chars is shorter, extra from_chars are deleted
                if not to_chars:
                    # Delete all from_chars
                    for char in from_chars:
                        result = result.replace(char, '')
                else:
                    # Map from_chars to to_chars, delete extras
                    trans_dict = {}
                    for i, char in enumerate(from_chars):
                        if i < len(to_chars):
                            trans_dict[ord(char)] = to_chars[i]
                        else:
                            trans_dict[ord(char)] = None  # Delete
                    result = result.translate(trans_dict)
                return result


        if func_name == 'current':
            return self._get_current_value()

        if func_name == 'true':
            return True

        if func_name == 'false':
            return False

        if func_name == 'bool':
            if len(args) == 1:
                return self._yang_bool(args[0])
            return False

        if func_name == 'number':
            if len(args) == 1:
                return self._xpath_number(args[0])
            # number() with no args converts current context node to number
            return self._xpath_number(self._get_current_value())

        if func_name == 'not':
            if len(args) == 1:
                operand = args[0]
                # In XPath, not() returns true if value is false/empty/None, false if value exists
                if operand is None or operand == '' or operand is False or (isinstance(operand, (list, dict)) and len(operand) == 0):
                    return True
                return False
            return True

        return None
    
    def _xpath_number(self, value: Any) -> float:
        """Convert a value to a number following XPath number() function rules."""
        if value is None:
            return float('nan')
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, str):
            # Try to parse as number
            try:
                return float(value)
            except ValueError:
                return float('nan')
        # For other types, try to convert
        try:
            return float(value)
        except (ValueError, TypeError):
            return float('nan')

    def _evaluate_binary_op(self, node: BinaryOpNode) -> Any:
        """Evaluate a binary operator node."""
        left = node.left.evaluate(self)
        op = node.operator

        # Special case: if left is a dict and op is '/', treat as path navigation
        # Extract the full path from nested BinaryOpNodes and evaluate as a single path
        if op == '/' and isinstance(left, dict):
            old_data = self.data
            old_context = self.context_path
            try:
                # Set the node as the current data context
                self.data = left
                self.context_path = []
                # Extract path from nested binary ops or evaluate as path node
                if isinstance(node.right, BinaryOpNode) and node.right.operator == '/':
                    # Nested path - extract all path parts from the right side
                    path_parts = self._extract_path_from_binary_op(node.right)
                    if path_parts:
                        # Build path string, handling PathNode objects
                        path_str_parts = []
                        for part in path_parts:
                            if isinstance(part, str):
                                path_str_parts.append(part)
                            elif hasattr(part, 'steps'):
                                # It's a PathNode
                                path_str_parts.extend(part.steps)
                            else:
                                # Try to evaluate
                                try:
                                    val = part.evaluate(self) if hasattr(part, 'evaluate') else str(part)
                                    if val:
                                        path_str_parts.append(str(val))
                                except:
                                    pass
                        if path_str_parts:
                            path_str = '/'.join(path_str_parts)
                            result = self._evaluate_path(path_str)
                        else:
                            result = None
                    else:
                        result = None
                elif hasattr(node.right, 'steps'):
                    # It's a PathNode - evaluate it directly
                    result = node.right.evaluate(self)
                else:
                    # Try to evaluate and treat as path
                    right_val = node.right.evaluate(self)
                    if isinstance(right_val, str):
                        result = self._evaluate_path(right_val)
                    else:
                        result = right_val
                return result
            finally:
                self.data = old_data
                self.context_path = old_context
        
        # Also handle nested BinaryOpNodes: if left is a BinaryOpNode that evaluates to a dict
        if op == '/' and isinstance(node.left, BinaryOpNode):
            # Evaluate left first to see if it's a dict
            left_result = node.left.evaluate(self)
            if isinstance(left_result, dict):
                # Left evaluated to a dict (node), treat / as path navigation
                old_data = self.data
                old_context = self.context_path
                try:
                    self.data = left_result
                    self.context_path = []
                    # Extract path from right side - handle nested BinaryOpNodes
                    if isinstance(node.right, BinaryOpNode) and node.right.operator == '/':
                        # Build full path by extracting from nested structure
                        path_parts = self._extract_path_from_binary_op(node.right)
                        # Convert path parts to string steps
                        path_steps = []
                        for part in path_parts:
                            if isinstance(part, str):
                                path_steps.append(part)
                            elif hasattr(part, 'steps'):
                                path_steps.extend(part.steps)
                            elif hasattr(part, 'evaluate'):
                                # Evaluate in current context
                                try:
                                    val = part.evaluate(self)
                                    if val is not None:
                                        path_steps.append(str(val))
                                except:
                                    pass
                        if path_steps:
                            path_str = '/'.join(path_steps)
                            result = self._evaluate_path(path_str)
                        else:
                            result = None
                    elif hasattr(node.right, 'steps'):
                        # It's a PathNode - evaluate it directly
                        result = node.right.evaluate(self)
                    else:
                        # Try to evaluate and treat as path
                        right_val = node.right.evaluate(self)
                        if isinstance(right_val, str):
                            result = self._evaluate_path(right_val)
                        else:
                            result = right_val
                    return result
                finally:
                    self.data = old_data
                    self.context_path = old_context
        
        # For other operations, evaluate right normally
        right = node.right.evaluate(self)

        if op == 'or':
            return bool(left) or bool(right)
        if op == 'and':
            return bool(left) and bool(right)
        if op == '=':
            return self._compare_equal(left, right)
        if op == '!=':
            return not self._compare_equal(left, right)
        if op == '<=':
            return self._compare_less_equal(left, right)
        if op == '>=':
            return self._compare_greater_equal(left, right)
        if op == '<':
            return self._compare_less(left, right)
        if op == '>':
            return self._compare_greater(left, right)
        if op == '+':
            # String concatenation or arithmetic
            try:
                return float(left) + float(right)
            except (ValueError, TypeError):
                return str(left) + str(right)
        if op == '-':
            try:
                return float(left) - float(right)
            except (ValueError, TypeError):
                return None
        if op == '*':
            try:
                return float(left) * float(right)
            except (ValueError, TypeError):
                return None
        if op == '/':
            # Normal division (left is not a dict, already handled above)
            try:
                return float(left) / float(right)
            except (ValueError, TypeError, ZeroDivisionError):
                return None

        return None

    def _evaluate_unary_op(self, node: UnaryOpNode) -> Any:
        """Evaluate a unary operator node."""
        operand = node.operand.evaluate(self)
        op = node.operator

        if op == 'not':
            # In XPath, not() returns true if value is false/empty/None, false if value exists
            if operand is None or operand == '' or operand is False or (isinstance(operand, (list, dict)) and len(operand) == 0):
                return True
            return False
        if op == '-':
            try:
                return -float(operand)
            except (ValueError, TypeError):
                return None

        return None

    def _evaluate_path_node(self, node: PathNode) -> Any:
        """Evaluate a path node."""
        # Handle relative paths with .. steps
        if node.steps and node.steps[0] == '..':
            # This is a relative path, evaluate it directly
            up_levels = sum(1 for step in node.steps if step == '..')
            field_parts = [step for step in node.steps if step != '..']

            # Special case: if we're at a node level (context_path is empty) and path starts with ..,
            # treat it as direct field access or return current node if no fields
            if up_levels > 0 and len(self.context_path) == 0 and isinstance(self.data, dict):
                if len(field_parts) == 0:
                    # Just ".." means stay at current node
                    return self.data
                # ../field means access 'field' from current node
                return self._get_path_value(field_parts)

            # Navigate up the context path
            if up_levels <= len(self.context_path):
                new_path = self.context_path[:-up_levels] + field_parts
                value = self._get_path_value(new_path)
            else:
                value = None
        elif node.is_absolute:
            # Absolute path
            path = '/' + '/'.join(node.steps)
            value = self._evaluate_path(path)
        else:
            # Simple relative path without ..
            path = '/'.join(node.steps)
            value = self._evaluate_path(path)

        # Apply predicate if present
        if node.predicate and isinstance(value, list):
            # Evaluate predicate for each item
            filtered = []
            for item in value:
                # Evaluate predicate in context of item
                old_data = self.data
                old_context = self.context_path
                self.data = item if isinstance(item, dict) else {'value': item}
                self.context_path = []

                try:
                    pred_result = node.predicate.evaluate(self)
                    if self._yang_bool(pred_result):
                        filtered.append(item)
                finally:
                    self.data = old_data
                    self.context_path = old_context

            return filtered

        return value

    def _yang_bool(self, value: Any) -> bool:
        """Convert a value to boolean following YANG rules.

        In YANG/JSON context:
        - String "true" -> True
        - String "false" -> False
        - Boolean true -> True
        - Boolean false -> False
        - Other values -> truthy/falsy
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            # YANG/JSON boolean strings
            if value.lower() == 'true':
                return True
            if value.lower() == 'false':
                return False
            # Other strings are truthy
            return bool(value)
        # For other types, use Python's bool()
        return bool(value)

    def _evaluate_deref(self, path: str) -> Any:
        """Evaluate deref() - resolve a leafref path.
        
        In YANG, deref() takes a leafref path and returns the node it references.
        This allows further path navigation from that node.
        
        For example: deref(../entity)/../fields/field[name = current()]
        - deref(../entity) should return the entity node (not just the value "parent")
        - Then /../fields/... can navigate from that entity node
        """
        try:
            # Check cache first
            cache_key = f"{path}:{self.context_path}"
            if cache_key in self.leafref_cache:
                return self.leafref_cache[cache_key]
            
            # Evaluate the path to get the leafref value (e.g., "parent")
            ref_value = self._evaluate_path(path)
            
            if ref_value is None:
                # Referenced node doesn't exist - acceptable for optional references
                return None
            
            # Now find the node that contains this value
            # The path tells us where to look (e.g., ../entity means look in parent's entity field)
            # We need to find the node that has this value
            
            # Parse the path to understand the structure
            # For ../entity, we need to:
            # 1. Go up one level from current context
            # 2. Find the entity list/container
            # 3. Find the entity node with name == ref_value
            
            # Handle relative paths like ../entity
            if path.startswith('../'):
                # Get the path parts
                parts = path.split('/')
                up_levels = sum(1 for p in parts if p == '..')
                field_parts = [p for p in parts if p and p != '..']
                
                # Navigate up from current context to get the leafref value (e.g., "parent")
                if up_levels <= len(self.context_path):
                    value_path = self.context_path[:-up_levels] + field_parts
                    ref_value = self._get_path_value(value_path)
                    
                    if ref_value is not None:
                        # Find the node that contains this value
                        # The field name (e.g., "entity") tells us what type of node to find
                        # Common pattern: if field is "entity", look in entities.entity list
                        field_name = field_parts[-1] if field_parts else None
                        
                        if field_name == "entity":
                            # Look in /data-model/entities/entity for entity with name == ref_value
                            # Use root_data to ensure we search from the root
                            old_data = self.data
                            try:
                                self.data = self.root_data
                                entities_list = self._get_path_value(["data-model", "entities", "entity"])
                                if isinstance(entities_list, list):
                                    for entity in entities_list:
                                        if isinstance(entity, dict) and "name" in entity:
                                            if entity["name"] == ref_value:
                                                result = entity
                                                self.leafref_cache[cache_key] = result
                                                return result
                            finally:
                                self.data = old_data
                        
                        # Generic fallback: search for any node with field_name == ref_value
                        # Use "name" as the key field (common pattern)
                        result = self._find_node_by_key(self.root_data, "name", ref_value, field_name)
                        if result is not None:
                            self.leafref_cache[cache_key] = result
                            return result
            
            # Handle absolute paths like /data-model/entities/entity/name
            elif path.startswith('/'):
                # Remove leading /
                abs_path = path.lstrip('/')
                parts = abs_path.split('/')
                
                # Navigate to the container that should contain the value
                # The last part is usually the key field (e.g., "name")
                if len(parts) >= 2:
                    container_path = parts[:-1]  # All but last
                    key_field = parts[-1]  # Last part is the key field
                    
                    container = self._evaluate_absolute_path('/' + '/'.join(container_path))
                    
                    if container is not None:
                        # Find the node in the container
                        if isinstance(container, list):
                            for item in container:
                                if isinstance(item, dict) and key_field in item:
                                    if item[key_field] == ref_value:
                                        result = item
                                        self.leafref_cache[cache_key] = result
                                        return result
                        elif isinstance(container, dict):
                            # Check if it's a dict keyed by the value
                            if key_field in container and container[key_field] == ref_value:
                                result = container
                                self.leafref_cache[cache_key] = result
                                return result
                            # Or check nested lists
                            for key, value in container.items():
                                if isinstance(value, list):
                                    for item in value:
                                        if isinstance(item, dict) and key_field in item:
                                            if item[key_field] == ref_value:
                                                result = item
                                                self.leafref_cache[cache_key] = result
                                                return result
            
            # Fallback: if we can't find the node, return None
            # This is acceptable for optional references
            return None
        except Exception:
            # If path evaluation fails, deref() returns None (referenced node doesn't exist)
            return None
    
    def _extract_path_from_binary_op(self, node: Any) -> List:
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
    
    def _find_node_by_key(self, data: Any, key_field: str, key_value: Any, node_type: str = None) -> Any:
        """Recursively find a node where key_field == key_value.
        
        If node_type is provided, only search in containers/lists with that name.
        """
        if isinstance(data, dict):
            # Check if this dict has the key_field with matching value
            if key_field in data and data[key_field] == key_value:
                # If node_type specified, check if this is the right type
                if node_type is None or node_type in str(data):
                    return data
            # Recursively search in values
            for key, value in data.items():
                # If node_type specified, prioritize searching in matching containers
                if node_type and key == node_type and isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and key_field in item:
                            if item[key_field] == key_value:
                                return item
                result = self._find_node_by_key(value, key_field, key_value, node_type)
                if result is not None:
                    return result
        elif isinstance(data, list):
            # Search in list items
            for item in data:
                result = self._find_node_by_key(item, key_field, key_value, node_type)
                if result is not None:
                    return result
        return None

    def _evaluate_path(self, path: str) -> Any:
        """Evaluate a path expression."""
        # Handle current node
        if path == '.' or path == 'current()':
            val = self._get_current_value()
            if val is not None:
                return val

        # Handle relative paths
        if path.startswith('../'):
            return self._evaluate_relative_path(path)

        # Handle absolute paths
        if path.startswith('/'):
            return self._evaluate_absolute_path(path)

        # Handle filtering [predicate]
        if '[' in path:
            base_path = path[:path.index('[')]
            predicate = path[path.index('['):]
            value = self._evaluate_path(base_path)
            if isinstance(value, list):
                return self._apply_predicate(value, predicate)
            return value

        # Simple field access
        return self._get_path_value(path.split('/'))

    def _evaluate_relative_path(self, path: str) -> Any:
        """Evaluate a relative path like ../field or ../../field."""
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
        if up_levels > 0 and len(self.context_path) == 0 and isinstance(self.data, dict):
            # We're at a node, and path wants to go up then down
            # In this case, just access the field directly from the node
            if len(field_parts) == 1:
                # Simple case: ../field means just access 'field' from current node
                return self.data.get(field_parts[0])
            # Multi-level: ../fields/field means access fields.field from current node
            return self._get_path_value(field_parts)

        # Navigate up the context path
        if up_levels <= len(self.context_path):
            new_path = self.context_path[:-up_levels] + field_parts
            value = self._get_path_value(new_path)
            if value is not None:
                return value

        # If we need to go up beyond context, try from root data
        # Save current data and try from root
        if up_levels > len(self.context_path):
            # We need to go to root - get root data from module if available
            # For now, try to navigate from current data's root
            remaining_up = up_levels - len(self.context_path)
            if remaining_up == 1 and field_parts:
                # We're at root, get the field
                # Try to get root data - if we have module, use it to find root
                root_data = self.data
                # Navigate up to find root (go up remaining_up levels)
                for _ in range(remaining_up - 1):
                    # This is a simplification - in full implementation would track root
                    pass
                return self._get_path_value(field_parts)

        return None

    def _evaluate_absolute_path(self, path: str) -> Any:
        """Evaluate an absolute path like /data-model/entities."""
        # Remove leading /
        path = path.lstrip('/')
        parts = path.split('/')
        
        # Use root_data for absolute paths
        old_data = self.data
        try:
            self.data = self.root_data
            return self._get_path_value(parts)
        finally:
            self.data = old_data

    def _get_path_value(self, parts: List) -> Any:
        """Get value at path in data structure.
        
        Args:
            parts: List of path parts (strings for dict keys, ints for list indices)
        """
        current = self.data

        for part in parts:
            if part == '.' or part == 'current()':
                continue

            # Handle integer list indices
            if isinstance(part, int):
                if isinstance(current, list) and 0 <= part < len(current):
                    current = current[part]
                else:
                    return None
                continue

            # Handle filtering
            if isinstance(part, str) and '[' in part:
                base_part = part[:part.index('[')]
                predicate = part[part.index('['):]

                if isinstance(current, dict) and base_part in current:
                    value = current[base_part]
                    if isinstance(value, list):
                        return self._apply_predicate(value, predicate)
                    return value
                return None

            if isinstance(current, dict):
                if part in current:
                    current = current[part]
                else:
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

    def _apply_predicate(self, items: List[Any], predicate: str) -> List[Any]:
        """Apply a predicate filter to a list of items."""
        if not predicate.startswith('[') or not predicate.endswith(']'):
            return items

        pred_expr = predicate[1:-1]

        # Handle index access [1]
        if pred_expr.isdigit():
            idx = int(pred_expr) - 1  # XPath is 1-indexed
            if 0 <= idx < len(items):
                return [items[idx]]
            return []

        # Handle comparisons like [name = current()] or [type != 'array']
        if '=' in pred_expr or '!=' in pred_expr:
            op = '=' if '=' in pred_expr else '!='
            parts = pred_expr.split(op, 1)
            if len(parts) == 2:
                left_expr = parts[0].strip()
                right_expr = parts[1].strip()

                filtered = []
                for item in items:
                    # Evaluate in the context of this item
                    left_val = self._evaluate_value_in_context(left_expr, item)
                    right_val = self._evaluate_value_in_context(right_expr, item)

                    if op == '=':
                        if self._compare_equal(left_val, right_val):
                            filtered.append(item)
                    else:  # !=
                        if not self._compare_equal(left_val, right_val):
                            filtered.append(item)

                return filtered

        return items

    def _evaluate_value_in_context(self, expr: str, context: Any) -> Any:
        """Evaluate a value expression in a specific context."""
        # Save current context
        old_data = self.data
        old_context_path = self.context_path
        # Set context - if it's a dict, use it directly; otherwise wrap it
        if isinstance(context, dict):
            self.data = context
        else:
            self.data = {'value': context}
        self.context_path = []  # Reset context path for item evaluation

        try:
            # Parse and evaluate using AST
            tokenizer = XPathTokenizer(expr)
            tokens = tokenizer.tokenize()
            parser = XPathParser(tokens)
            ast = parser.parse()
            result = ast.evaluate(self)
        finally:
            self.data = old_data
            self.context_path = old_context_path

        return result

    def _get_current_value(self) -> Any:
        """Get the current value from the context path.
        
        In XPath, current() always refers to the original context node where
        the expression is being evaluated, not the current iteration context.
        """
        # Always use original context for current()
        if self.original_context_path:
            # Temporarily use original data and context
            old_data = self.data
            old_context = self.context_path
            try:
                self.data = self.original_data
                self.context_path = self.original_context_path
                value = self._get_path_value(self.original_context_path)
                # Return empty string if None (XPath spec for current())
                return value if value is not None else ""
            finally:
                self.data = old_data
                self.context_path = old_context
        # If no original context path, try to get value from current data
        if isinstance(self.data, (str, int, float, bool)):
            return self.data
        return ""

    def _compare_equal(self, left: Any, right: Any) -> bool:
        """Compare two values for equality."""
        # Handle string comparison with type coercion
        if isinstance(left, str) and isinstance(right, (int, float, bool)):
            right = str(right)
        elif isinstance(right, str) and isinstance(left, (int, float, bool)):
            left = str(left)

        return left == right

    def _compare_less_equal(self, left: Any, right: Any) -> bool:
        """Compare left <= right."""
        try:
            return float(left) <= float(right)
        except (ValueError, TypeError):
            return str(left) <= str(right)

    def _compare_greater_equal(self, left: Any, right: Any) -> bool:
        """Compare left >= right."""
        try:
            return float(left) >= float(right)
        except (ValueError, TypeError):
            return str(left) >= str(right)

    def _compare_less(self, left: Any, right: Any) -> bool:
        """Compare left < right."""
        try:
            return float(left) < float(right)
        except (ValueError, TypeError):
            return str(left) < str(right)

    def _compare_greater(self, left: Any, right: Any) -> bool:
        """Compare left > right."""
        try:
            return float(left) > float(right)
        except (ValueError, TypeError):
            return str(left) > str(right)
