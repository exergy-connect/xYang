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
        
        # Special case: if left is a dict and op is '/', treat as path navigation
        # Extract the full path from nested BinaryOpNodes and evaluate as a single path
        if op == '/' and isinstance(left, dict):
            old_data = self.data
            old_context = self.context_path
            try:
                # Set the node as the current data context
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
                                # Try to evaluate
                                try:
                                    val = part.evaluate(self) if hasattr(part, 'evaluate') else str(part)
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
                    # If it has a predicate, we need to evaluate it properly (not convert to string)
                    if hasattr(node.right, 'predicate') and node.right.predicate:
                        # PathNode with predicate - evaluate directly to handle predicate correctly
                        result = node.right.evaluate(self)
                    else:
                        # Handle .. at the start - when navigating from a node, .. means stay at the node
                        steps = list(node.right.steps)
                        if steps and steps[0] == '..':
                            # Remove leading .. when navigating from a node (we're already at the node)
                            steps = steps[1:]
                            if steps:
                                # Build path string without the leading ..
                                path_str = '/'.join(steps)
                                result = self.path_evaluator.evaluate_path(path_str)
                            else:
                                # Just .. means the current node
                                result = self.data
                        else:
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
                    self._set_context_path([])
                    # Extract path from right side - handle nested BinaryOpNodes
                    if isinstance(node.right, BinaryOpNode) and node.right.operator == '/':
                        # Build full path by extracting from nested structure
                        path_parts = self.path_evaluator.extract_path_from_binary_op(node.right)
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
                            result = self.path_evaluator.evaluate_path(path_str)
                        else:
                            result = None
                    elif hasattr(node.right, 'steps'):
                        # It's a PathNode - evaluate it directly
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
        
        # For other operations, evaluate right normally
        right = node.right.evaluate(self)

        if op == 'or':
            return bool(left) or bool(right)
        if op == 'and':
            return bool(left) and bool(right)
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

    def _evaluate_path(self, path: str) -> Any:
        """Evaluate a path expression."""
        return self.path_evaluator.evaluate_path(path)

    def _evaluate_relative_path(self, path: str) -> Any:
        """Evaluate a relative path like ../field or ../../field."""
        return self.path_evaluator.evaluate_relative_path(path)

    def _evaluate_absolute_path(self, path: str) -> Any:
        """Evaluate an absolute path like /data-model/entities."""
        return self.path_evaluator.evaluate_absolute_path(path)

    def _get_path_value(self, parts: List) -> Any:
        """Get value at path in data structure."""
        return self.path_evaluator.get_path_value(parts)

    def _apply_predicate(self, items: List[Any], predicate: str) -> Any:
        """Apply a predicate filter to a list of items."""
        return self.predicate_evaluator.apply_predicate(items, predicate)

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
                self._set_context_path(self.original_context_path)
                value = self.path_evaluator.get_path_value(self.original_context_path)
                # Return empty string if None (XPath spec for current())
                return value if value is not None else ""
            finally:
                self.data = old_data
                self._set_context_path(old_context)
        # If no original context path, try to get value from current data
        if isinstance(self.data, (str, int, float, bool)):
            return self.data
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