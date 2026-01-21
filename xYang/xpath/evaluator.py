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

        elif func_name == 'deref':
            if len(args) == 1:
                path = str(args[0] or '')
                return self._evaluate_deref(path)
            return None

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
        right = node.right.evaluate(self)
        op = node.operator

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
        This implementation evaluates the path to get the leafref value, then finds
        the referenced node. For simplicity, we return the value directly.
        """
        try:
            # Check cache first
            if path in self.leafref_cache:
                return self.leafref_cache[path]
            
            # Evaluate the path to get the leafref value
            ref_value = self._evaluate_path(path)
            
            # If we got a value, cache and return it
            # In YANG, deref() returns the referenced node, but for validation purposes
            # we can return the value directly
            if ref_value is not None:
                self.leafref_cache[path] = ref_value
                return ref_value
            
            # Try to evaluate the path as an absolute or relative path
            if path.startswith('/'):
                result = self._evaluate_absolute_path(path)
                if result is not None:
                    self.leafref_cache[path] = result
                return result
            if path.startswith('../'):
                result = self._evaluate_relative_path(path)
                if result is not None:
                    self.leafref_cache[path] = result
                return result
            
            # If path evaluation returns None, deref() returns None
            # (referenced node doesn't exist - this is acceptable for optional references)
            return None
        except Exception:
            # If path evaluation fails, deref() returns None (referenced node doesn't exist)
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

    def _get_path_value(self, parts: List[str]) -> Any:
        """Get value at path in data structure."""
        current = self.data

        for part in parts:
            if part == '.' or part == 'current()':
                continue

            # Handle filtering
            if '[' in part:
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
        """Get the current node value."""
        # Navigate through context_path in data
        if self.context_path and isinstance(self.data, dict):
            current = self.data
            for part in self.context_path:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None
            return current

        # Fallback: if no context path, try to get from data directly
        if isinstance(self.data, dict):
            # If we have a single value, return it
            if len(self.data) == 1:
                return list(self.data.values())[0]

        return None

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
