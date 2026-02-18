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
            # Convert to boolean - optimized type checking
            if isinstance(result, bool):
                return result
            if isinstance(result, (int, float, str)):
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
                elif isinstance(arg_node, FunctionCallNode):
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
                # In XPath translate(), if to_chars is shorter, extra from_chars are deleted
                if not to_chars:
                    # Delete all from_chars - use set for faster lookup
                    if from_chars:
                        result = ''.join(c for c in source if c not in from_chars)
                    else:
                        result = source
                else:
                    # Map from_chars to to_chars, delete extras
                    trans_dict = {}
                    to_len = len(to_chars)
                    for i, char in enumerate(from_chars):
                        trans_dict[ord(char)] = to_chars[i] if i < to_len else None
                    result = source.translate(trans_dict)
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
                # Optimized: check most common cases first
                if operand is None or operand is False or operand == '':
                    return True
                if isinstance(operand, (list, dict)):
                    return len(operand) == 0
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
            # Optimized: check most common cases first
            if operand is None or operand is False or operand == '':
                return True
            if isinstance(operand, (list, dict)):
                return len(operand) == 0
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
            # YANG/JSON boolean strings - optimized comparison
            if value == 'true' or value == 'True':
                return True
            if value == 'false' or value == 'False':
                return False
            # Use lower() only if needed
            lower_val = value.lower()
            if lower_val == 'true':
                return True
            if lower_val == 'false':
                return False
            # Other strings are truthy
            return bool(value)
        # For other types, use Python's bool()
        return bool(value)

    def _evaluate_deref(self, path: str) -> Any:
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
            cache_key = f"{path}:{self.context_path}"
            if cache_key in self.leafref_cache:
                return self.leafref_cache[cache_key]
            
            # Step 1: Evaluate the path to get the leafref value
            ref_value = self._evaluate_path(path)
            
            if ref_value is None:
                # Referenced node doesn't exist - acceptable for optional references
                return None
            
            # Step 2: Find the schema node for the field at this path
            leafref_path = self._get_leafref_path_from_schema(path)
            
            if not leafref_path:
                # No leafref definition found - cannot resolve
                return None
            
            # Step 3: Use the leafref path to find the referenced node
            result = self._find_node_by_leafref_path(leafref_path, ref_value)
            
            if result is not None:
                self.leafref_cache[cache_key] = result
            
            return result
        except Exception:
            # If path evaluation fails, deref() returns None (referenced node doesn't exist)
            return None
    
    def _get_leafref_path_from_schema(self, path: str) -> str:
        """Get the leafref path definition from the schema for the field at the given path.
        
        Args:
            path: XPath expression pointing to a leafref field (e.g., "../entity", "current()")
            
        Returns:
            The leafref path string, or None if not found
        """
        # Resolve the path to find the schema node
        # First, resolve the path to an absolute schema path
        schema_path = self._resolve_path_to_schema_location(path)
        
        if not schema_path:
            return None
        
        # Find the schema node at that path
        schema_node = self._find_schema_node(schema_path)
        
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
    
    def _resolve_path_to_schema_location(self, path: str) -> List[str]:
        """Resolve an XPath expression to a schema location path.
        
        Args:
            path: XPath expression (e.g., "../entity", "current()", "./field")
            
        Returns:
            List of schema node names representing the full path from module root, or None
        """
        # Handle current() or .
        if path == 'current()' or path == '.':
            # Use current context path, but convert data path to schema path
            # Schema path is similar but may need adjustment
            return self._data_path_to_schema_path(self.context_path)
        
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
                data_path = self.context_path + field_parts
            elif up_levels <= len(self.context_path):
                # Navigate up 'up_levels' steps
                data_path = self.context_path[:-up_levels] + field_parts
            else:
                return None
            
            schema_path = self._data_path_to_schema_path(data_path)
            # Ensure we have the full path from root (should start with data-model)
            if schema_path and schema_path[0] != "data-model":
                # Prepend data-model if not present
                schema_path = ["data-model"] + schema_path
            return schema_path
        
        # Simple field name
        if path and not path.startswith('/'):
            data_path = self.context_path + [path]
            return self._data_path_to_schema_path(data_path)
        
        # Handle absolute paths
        if path.startswith('/'):
            # Remove leading / and convert to schema path
            parts = [p for p in path.split('/') if p]
            return parts
        
        return None
    
    def _data_path_to_schema_path(self, data_path: List) -> List[str]:
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
    
    def _find_schema_node(self, schema_path: List[str]) -> Any:
        """Find a schema node at the given path.
        
        Args:
            schema_path: List of schema node names
            
        Returns:
            The schema node (YangStatement), or None if not found
        """
        if not self.module or not schema_path:
            return None
        
        current_statements = self.module.statements
        last_node = None
        
        for part in schema_path:
            found = False
            for stmt in current_statements:
                if hasattr(stmt, 'name') and stmt.name == part:
                    last_node = stmt
                    if hasattr(stmt, 'statements'):
                        current_statements = stmt.statements
                    else:
                        current_statements = []
                    found = True
                    break
            if not found:
                return None
        
        return last_node
    
    def _find_node_by_leafref_path(self, leafref_path: str, ref_value: Any) -> Any:
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
            # Relative path - resolve relative to current context
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
            if up_levels > len(self.context_path):
                return None
            
            # Remove list indices when going up (they're not part of schema structure)
            context_without_indices = [p for p in self.context_path if not isinstance(p, int)]
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
        old_data = self.data
        try:
            self.data = self.root_data
            # For absolute paths, don't use context index (search in all entities)
            # For relative paths, use context index (search in specific entity)
            use_context_index = not leafref_path.startswith('/')
            container = self._walk_path_to_container(container_path_parts, use_context_index=use_context_index)
            
            if container is None:
                return None
            
            # Search for the node with key_field == ref_value
            return self._search_for_node(container, key_field, ref_value)
        finally:
            self.data = old_data
    
    def _walk_path_to_container(self, path_parts: List[str], use_context_index: bool = True) -> Any:
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
        if not path_parts:
            return self.root_data
        
        # Extract entity index from context if available and requested
        entity_idx = None
        if use_context_index and self.context_path:
            context_len = len(self.context_path)
            for j, p in enumerate(self.context_path):
                if p == "entities" and j + 1 < context_len:
                    next_item = self.context_path[j + 1]
                    if isinstance(next_item, int):
                        entity_idx = next_item
                        break
        
        current = self.root_data
        
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
                if self.context_path:
                    context_len = len(self.context_path)
                    for j, p in enumerate(self.context_path):
                        if p == part and j + 1 < context_len:
                            next_item = self.context_path[j + 1]
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
                                result = self._walk_path_from_node(item, remaining_parts)
                                if result is not None:
                                    return result
                    return None
            else:
                return None
        
        return current
    
    def _walk_path_from_node(self, node: Any, path_parts: List[str]) -> Any:
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
    
    def _search_for_node(self, container: Any, key_field: str, ref_value: Any) -> Any:
        """Search for a node in the container where key_field == ref_value.
        
        Args:
            container: The container to search in (dict, list, or nested structure)
            key_field: The field name to match
            ref_value: The value to search for
            
        Returns:
            The node containing the value, or None if not found
        """
        if container is None:
            return None
        
        if isinstance(container, list):
            # Search in list items
            for item in container:
                if isinstance(item, dict) and key_field in item:
                    if item[key_field] == ref_value:
                        return item
                # Also search recursively in nested structures
                result = self._search_for_node(item, key_field, ref_value)
                if result is not None:
                    return result
        elif isinstance(container, dict):
            # Check if container itself matches
            if key_field in container and container[key_field] == ref_value:
                return container
            # Search in nested structures
            for key, value in container.items():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and key_field in item:
                            if item[key_field] == ref_value:
                                return item
                        # Recursively search nested structures
                        result = self._search_for_node(item, key_field, ref_value)
                        if result is not None:
                            return result
                elif isinstance(value, dict):
                    # Recursively search in nested dicts
                    result = self._search_for_node(value, key_field, ref_value)
                    if result is not None:
                        return result
        
        return None
    
    def _resolve_leafref_path_to_absolute(self, path: str) -> str:
        """Resolve a relative leafref path to an absolute path.
        
        This attempts to resolve the path to understand where in the data
        structure the referenced node should be found. For generic implementation,
        this uses heuristics based on the path structure.
        
        Args:
            path: Leafref path (relative or absolute)
            
        Returns:
            Absolute path string (without leading /), or None if cannot be resolved
        """
        # If already absolute, return as-is (without leading /)
        if path.startswith('/'):
            return path.lstrip('/')
        
        # Handle relative paths
        if path.startswith('../') or path.startswith('./') or path == 'current()' or path == '.':
            parts = path.split('/')
            # Optimized: single pass through parts
            up_levels = 0
            field_parts = []
            for p in parts:
                if p == '..':
                    up_levels += 1
                elif p and p != '.' and p != 'current()':
                    field_parts.append(p)
            
            # Build absolute path from context_path
            if up_levels == 0:
                # No navigation up - use current context + field_parts
                absolute_parts = self.context_path + field_parts
                return '/'.join(str(p) for p in absolute_parts) if absolute_parts else None
            elif up_levels <= len(self.context_path):
                # Navigate up from context_path
                absolute_parts = self.context_path[:-up_levels] + field_parts
                return '/'.join(str(p) for p in absolute_parts) if absolute_parts else None
            elif field_parts:
                # Try relative to current context
                absolute_parts = self.context_path + field_parts
                return '/'.join(str(p) for p in absolute_parts) if absolute_parts else None
            else:
                # Path is just current() or . - use current context
                return '/'.join(str(p) for p in self.context_path) if self.context_path else None
        
        # Simple field name - relative to current context
        if path and not path.startswith('/'):
            absolute_parts = self.context_path + [path]
            return '/'.join(str(p) for p in absolute_parts)
        
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

        # Handle relative paths starting with ./
        if path.startswith('./'):
            # Remove leading ./ and evaluate relative to current context
            remaining_path = path[2:]  # Remove './'
            if remaining_path:
                # Build path from current context
                parts = remaining_path.split('/')
                full_path = self.context_path + parts
                return self._get_path_value(full_path)
            else:
                # Just './' means current node
                return self._get_current_value()

        # Handle relative paths
        if path.startswith('../'):
            return self._evaluate_relative_path(path)

        # Handle absolute paths
        if path.startswith('/'):
            return self._evaluate_absolute_path(path)

        # Handle filtering [predicate]
        bracket_idx = path.find('[')
        if bracket_idx >= 0:
            base_path = path[:bracket_idx]
            predicate = path[bracket_idx:]
            value = self._evaluate_path(base_path)
            if isinstance(value, list):
                return self._apply_predicate(value, predicate)
            return value

        # Simple field access - cache split result if path is simple
        if '/' not in path:
            return self._get_path_value([path])
        return self._get_path_value(path.split('/'))

    def _evaluate_relative_path(self, path: str) -> Any:
        """Evaluate a relative path like ../field or ../../field."""
        # Optimized: avoid split if path is simple
        if path == '..':
            up_levels = 1
            field_parts = []
        else:
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
            if isinstance(part, str):
                bracket_idx = part.find('[')
                if bracket_idx >= 0:
                    base_part = part[:bracket_idx]
                    predicate = part[bracket_idx:]

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
            op = '!=' if '!=' in pred_expr else '='
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
        # Fast path for same types
        if type(left) is type(right):
            return left == right
        # Handle string comparison with type coercion
        if isinstance(left, str) and isinstance(right, (int, float, bool)):
            return left == str(right)
        if isinstance(right, str) and isinstance(left, (int, float, bool)):
            return str(left) == right
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
