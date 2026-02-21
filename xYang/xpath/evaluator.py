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

from typing import Any, Dict, List, Optional

from .parser import XPathTokenizer, XPathParser
from .ast import PathNode, FunctionCallNode, BinaryOpNode, UnaryOpNode, XPathNode
from ..errors import XPathSyntaxError

from .path_evaluator import PathEvaluator
from .function_evaluator import FunctionEvaluator
from .deref_evaluator import DerefEvaluator
from .predicate_evaluator import PredicateEvaluator
from .comparison_evaluator import ComparisonEvaluator
from .utils import yang_bool, compare_equal


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
        self._expression_cache: Dict[str, Any] = {}  # Cache for parsed expressions
        self._context_path_len: int = len(self.context_path)  # Cache context path length
        self._deref_node_paths: Dict[int, List] = {}  # Map node id to its path in data tree for navigation after deref()
        
        # Initialize sub-evaluators
        self.path_evaluator = PathEvaluator(self)
        self.function_evaluator = FunctionEvaluator(self)
        self.deref_evaluator = DerefEvaluator(self)
        self.predicate_evaluator = PredicateEvaluator(self)
        self.comparison_evaluator = ComparisonEvaluator(self)
    
    def _set_context_path(self, path: List[str]) -> None:
        """Set context path and update cached length.
        
        Args:
            path: New context path
        """
        self.context_path = path
        self._context_path_len = len(path) if path else 0

    def evaluate(self, expression: str, ast: Optional[XPathNode] = None) -> bool:
        """
        Evaluate an XPath expression and return boolean result.
        
        Args:
            expression: The XPath expression string (used for caching if ast not provided)
            ast: Optional pre-parsed AST node to reuse (avoids double parsing)
        """
        try:
            result = self.evaluate_value(expression, ast)
            # Convert to boolean using yang_bool for proper XPath truthiness
            from .utils import yang_bool
            return yang_bool(result)
        except XPathSyntaxError:
            # Re-raise syntax errors
            raise
        except Exception as e:
            # For other errors, raise a more specific exception
            from ..errors import XPathEvaluationError
            raise XPathEvaluationError(f"XPath evaluation failed: {e}") from e

    def evaluate_value(self, expression: str, ast: Optional[XPathNode] = None) -> Any:
        """
        Evaluate an XPath expression and return the raw value.
        
        Args:
            expression: The XPath expression string (used for caching if ast not provided)
            ast: Optional pre-parsed AST node to reuse (avoids double parsing)
        """
        try:
            # Use provided AST if available
            if ast is not None:
                return ast.evaluate(self)
            
            # Check cache first (only for simple expressions to avoid memory bloat)
            if len(expression) < 100 and expression in self._expression_cache:
                ast = self._expression_cache[expression]
            else:
                # Parse expression into AST
                tokenizer = XPathTokenizer(expression)
                tokens = tokenizer.tokenize()
                parser = XPathParser(tokens, expression=expression)
                ast = parser.parse()
                # Cache only short expressions
                if len(expression) < 100:
                    self._expression_cache[expression] = ast

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
        return self.function_evaluator.evaluate_function(node)

    def _evaluate_binary_op(self, node: BinaryOpNode) -> Any:
        """Evaluate a binary operator node."""
        left = node.left.evaluate(self)
        op = node.operator

        # Special case: if left is a dict or list and op is '/', treat as path navigation
        # For lists, navigate from first element
        if op == '/' and isinstance(left, list) and len(left) > 0:
            # Left is a list - navigate from first element
            old_data = self.data
            old_context = self.context_path
            try:
                self.data = left[0] if isinstance(left[0], dict) else {'value': left[0]}
                self._set_context_path([])
                # Evaluate right side as path
                if hasattr(node.right, 'steps'):
                    # It's a PathNode
                    result = node.right.evaluate(self)
                else:
                    # Try to evaluate and treat as path
                    right_val = node.right.evaluate(self)
                    if isinstance(right_val, str):
                        result = self.path_evaluator.evaluate_path(right_val)
                    else:
                        result = right_val
                return result
            finally:
                self.data = old_data
                self._set_context_path(old_context)
        
        # Special case: if left is None and op is '/', return empty list (empty node-set)
        # This handles cases like deref(...)/../fields where deref() returns None
        # In XPath, navigating from an empty node-set results in an empty node-set
        if op == '/' and left is None:
            return []
        
        # Special case: if left is a dict and op is '/', treat as path navigation
        # Extract the full path from nested BinaryOpNodes and evaluate as a single path
        if op == '/' and isinstance(left, dict):
            old_data = self.data
            old_context = self.context_path
            try:
                # Check if this node was returned by deref() - if so, use its stored path
                node_id = id(left)
                stored_path = self._deref_node_paths.get(node_id)
                
                if stored_path:
                    # Node was returned by deref() - navigate from its location in data tree
                    self.data = self.root_data
                    self._set_context_path(stored_path)
                else:
                    # Set the node as the current data context
                    # When navigating from a node (even without stored_path), ../field should mean ./field
                    # This handles cases where deref() returns a node but stored_path wasn't set
                    self.data = left
                    self._set_context_path([])
                
                # Extract path from nested binary ops or evaluate as path node
                if isinstance(node.right, BinaryOpNode) and node.right.operator == '/':
                    # Nested path - extract all path parts from the right side
                    path_parts = self.path_evaluator.extract_path_from_binary_op(node.right)
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
                                # Try to evaluate (for function calls, etc.)
                                if hasattr(part, 'evaluate'):
                                    try:
                                        val = part.evaluate(self)
                                        if val:
                                            path_str_parts.append(str(val))
                                    except:
                                        pass
                        if path_str_parts:
                            path_str = '/'.join(path_str_parts)
                            result = self.path_evaluator.evaluate_path(path_str)
                        else:
                            result = None
                    else:
                        result = None
                elif hasattr(node.right, 'steps'):
                    # It's a PathNode - evaluate it directly
                    # Handle .. at the start (for both with and without predicates)
                    steps = list(node.right.steps)
                    if steps and steps[0] == '..':
                        # When navigating from a deref() node (or any node), YANG semantics:
                        # ../field from node means ./field (field as child of node)
                        # This is because .. from a node's location would go to its parent (list),
                        # which doesn't have the field. So we interpret it as the field within the node.
                        # This applies whether or not stored_path is set, as long as left is a dict (node)
                        if len(steps) > 1:
                            # Remove .. and try field directly from the node's location
                            direct_path = '/'.join(steps[1:])
                            # If there's a predicate, we need to preserve it
                            if hasattr(node.right, 'predicate') and node.right.predicate:
                                # Rebuild path with predicate but without ..
                                from ..xpath.ast import PathNode
                                direct_node = PathNode(steps[1:], node.right.is_absolute)
                                direct_node.predicate = node.right.predicate
                                # When navigating from a deref() node, ../fields should mean ./fields
                                # (fields as a child of the entity node)
                                # Try evaluating from the node itself as data first
                                old_data_temp = self.data
                                old_context_temp = self.context_path
                                # Preserve original context for current() in predicates
                                old_original_context_path = self.original_context_path
                                old_original_data = self.original_data
                                try:
                                    self.data = left
                                    self._set_context_path([])
                                    # Ensure original context is preserved for current() in predicates
                                    self.original_context_path = old_original_context_path
                                    self.original_data = old_original_data
                                    result = direct_node.evaluate(self)
                                finally:
                                    self.data = old_data_temp
                                    self._set_context_path(old_context_temp)
                                    self.original_context_path = old_original_context_path
                                    self.original_data = old_original_data
                                # If that didn't work, try from the node's location in the tree
                                if result is None or (isinstance(result, list) and len(result) == 0):
                                    result = direct_node.evaluate(self)
                            else:
                                # Try evaluating from the node itself as data first
                                old_data_temp = self.data
                                old_context_temp = self.context_path
                                # Preserve original context for current() in predicates
                                old_original_context_path = self.original_context_path
                                old_original_data = self.original_data
                                try:
                                    self.data = left
                                    self._set_context_path([])
                                    # Ensure original context is preserved for current() in predicates
                                    self.original_context_path = old_original_context_path
                                    self.original_data = old_original_data
                                    result = self.path_evaluator.evaluate_path(direct_path)
                                finally:
                                    self.data = old_data_temp
                                    self._set_context_path(old_context_temp)
                                    self.original_context_path = old_original_context_path
                                    self.original_data = old_original_data
                            # If that fails, try with .. (go up then down) as fallback
                            if result is None or (isinstance(result, list) and len(result) == 0):
                                if hasattr(node.right, 'predicate') and node.right.predicate:
                                    result = node.right.evaluate(self)
                                else:
                                    path_str = '/'.join(steps)
                                    result = self.path_evaluator.evaluate_path(path_str)
                        else:
                            # Just .. means go up from stored_path (if set) or return the node itself
                            if stored_path:
                                if hasattr(node.right, 'predicate') and node.right.predicate:
                                    result = node.right.evaluate(self)
                                else:
                                    path_str = '/'.join(steps)
                                    result = self.path_evaluator.evaluate_path(path_str)
                            else:
                                # No stored_path - just return the node itself
                                result = left
                    else:
                        # No .. at start - evaluate normally (handles predicates automatically)
                        result = node.right.evaluate(self)
                else:
                    # Try to evaluate and treat as path
                    right_val = node.right.evaluate(self)
                    if isinstance(right_val, str):
                        result = self.path_evaluator.evaluate_path(right_val)
                    else:
                        result = right_val
                return result
            finally:
                self.data = old_data
                self._set_context_path(old_context)
        
        # Short-circuit evaluation for logical operators
        if op == 'or':
            # If left is truthy, short-circuit and return True without evaluating right
            if yang_bool(left):
                return True
            # Only evaluate right if left is falsy
            right = node.right.evaluate(self)
            return bool(right)
        if op == 'and':
            # If left is falsy, short-circuit and return False without evaluating right
            if not yang_bool(left):
                return False
            # Only evaluate right if left is truthy
            right = node.right.evaluate(self)
            return bool(right)
        
        # For other operations, evaluate right normally
        right = node.right.evaluate(self)
        # Get type context for coercion
        type_context = self._get_type_context()
        
        if op == '=':
            return self.comparison_evaluator.evaluate_comparison('=', left, right, type_context)
        if op == '!=':
            return self.comparison_evaluator.evaluate_comparison('!=', left, right, type_context)
        if op == '<=':
            return self.comparison_evaluator.evaluate_comparison('<=', left, right, type_context)
        if op == '>=':
            return self.comparison_evaluator.evaluate_comparison('>=', left, right, type_context)
        if op == '<':
            return self.comparison_evaluator.evaluate_comparison('<', left, right, type_context)
        if op == '>':
            return self.comparison_evaluator.evaluate_comparison('>', left, right, type_context)
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
        return self.path_evaluator.evaluate_path_node(node)

    def _get_current_value(self) -> Any:
        """Get the current value from the context path.
        
        In XPath, current() always refers to the original context node where
        the expression is being evaluated, not the current iteration context.
        """
        # Always use original context for current()
        if self.original_context_path:
            # Navigate directly from original_data using the original_context_path
            # This avoids issues with get_path_value's context-aware navigation
            current = self.original_data
            path_to_use = list(self.original_context_path)
            
            # If the first part of the path doesn't exist in original_data, try without it
            # This handles the case where root_data is data['data-model'] but context_path includes 'data-model'
            if (path_to_use and isinstance(current, dict) and 
                isinstance(path_to_use[0], str) and path_to_use[0] not in current):
                # Try navigating from root_data instead (which might be the full data structure)
                if hasattr(self, 'root_data') and self.root_data is not current:
                    # Check if root_data has the first part
                    if isinstance(self.root_data, dict) and path_to_use[0] in self.root_data:
                        current = self.root_data
                    else:
                        # Remove the first part and try again
                        path_to_use = path_to_use[1:]
            
            for part in path_to_use:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                elif isinstance(current, list) and isinstance(part, int) and 0 <= part < len(current):
                    current = current[part]
                else:
                    # Path not found - return empty string (XPath spec for current())
                    return ""
            # Return the value, or empty string if None (XPath spec for current())
            return current if current is not None else ""
        # If no original context path, try to get value from current data
        if isinstance(self.data, (str, int, float, bool)):
            return self.data
        # If data is a dict and we're at a leaf, try to get the value
        if isinstance(self.data, dict) and self.context_path:
            last_part = self.context_path[-1]
            if isinstance(last_part, str) and last_part in self.data:
                return self.data[last_part]
        return ""
    
    def _get_type_context(self) -> Optional[Any]:
        """
        Get the schema type for the current context.
        
        Returns:
            YangTypeStmt if type can be resolved, None otherwise
        """
        if not self.module or not self.original_context_path:
            return None
        
        try:
            # Navigate schema to find the type for the current context
            statements = self.module.statements
            path = self.original_context_path.copy()
            
            # Remove list indices from path (they're not in schema)
            schema_path = [p for p in path if not isinstance(p, int)]
            
            # Navigate schema
            for step in schema_path:
                found = False
                for stmt in statements:
                    if hasattr(stmt, 'name') and stmt.name == step:
                        if hasattr(stmt, 'type') and stmt.type:
                            # Found a leaf or leaf-list with a type
                            return stmt.type
                        elif hasattr(stmt, 'statements'):
                            # Recurse into composite statement
                            statements = stmt.statements
                            found = True
                            break
                if not found:
                    return None
            
            return None
        except Exception:
            return None