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
from .utils import yang_bool
from .context import Context, JsonValue


class XPathEvaluator:
    """Minimal XPath evaluator for YANG expressions."""

    def __init__(self, data: Dict[str, Any], module: Any, context_path: Optional[List[str]] = None):
        """
        Initialize evaluator.
        
        Args:
            data: The data instance being validated
            module: The YANG module (for schema resolution)
            context_path: Current path in the data structure (for current() and relative paths)
        """
        self.module = module
        self.root_data = data  # Store root data for absolute path resolution
        self.leafref_cache: Dict[str, Any] = {}  # Cache for deref() results
        self._expression_cache: Dict[str, Any] = {}  # Cache for parsed expressions
        self._deref_node_paths: Dict[int, List] = {}  # Map node id to its path in data tree for navigation after deref()
        
        # Context state (set from Context object when evaluating)
        self.data = data
        self.context_path: List[str] = context_path or []
        self.original_context_path: List[str] = context_path.copy() if context_path else []
        self.original_data = data
        
        # Initialize sub-evaluators
        self.path_evaluator = PathEvaluator(self)
        self.function_evaluator = FunctionEvaluator(self)
        self.deref_evaluator = DerefEvaluator(self)
        self.predicate_evaluator = PredicateEvaluator(self)
        self.comparison_evaluator = ComparisonEvaluator(self)

    def evaluate(self, expression: str, context: Context, ast: Optional[XPathNode] = None) -> bool:
        """
        Evaluate an XPath expression and return boolean result.
        
        Args:
            expression: The XPath expression string (used for error messages and caching if ast not provided)
            context: Context for evaluation
            ast: Optional pre-parsed AST node to reuse (avoids double parsing).
                 If provided, expression string is only used for error messages.
        """
        try:
            result = self.evaluate_value(expression, context, ast)
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

    def evaluate_value(self, expression: str, context: Context, ast: Optional[XPathNode] = None) -> JsonValue:
        """
        Evaluate an XPath expression and return the raw value.
        
        Args:
            expression: The XPath expression string (used for error messages and caching if ast not provided)
            context: Context for evaluation
            ast: Optional pre-parsed AST node to reuse (avoids double parsing).
                 If provided, expression string is only used for error messages, not parsed again.
        
        Note:
            YANG must/when statements have pre-parsed ASTs stored in their .ast attribute.
            Always pass the AST when available to ensure expressions are only parsed once.
        """
        try:
            # Use provided AST if available - this ensures YANG expressions are only parsed once
            if ast is not None:
                return ast.evaluate(self, context)
            
            # AST not provided - parse expression (fallback for dynamically constructed expressions)
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
            return ast.evaluate(self, context)
        except XPathSyntaxError:
            # Re-raise syntax errors
            raise
        except Exception as e:
            # For other errors, raise a more specific exception
            from ..errors import XPathEvaluationError
            raise XPathEvaluationError(f"XPath evaluation failed: {e}") from e

    def _evaluate_function_node(self, node: FunctionCallNode, context: Context) -> JsonValue:
        """Evaluate a function call node.
        
        Args:
            node: Function call node
            context: Context for evaluation
        """
        return self.function_evaluator.evaluate_function(node, context)

    def _evaluate_binary_op(self, node: BinaryOpNode, context: Context) -> JsonValue:
        """Evaluate a binary operator node.
        
        Args:
            node: Binary operator node
            context: Context for evaluation
        """
        left = node.left.evaluate(self, context)
        op = node.operator

        # Special case: if left is a dict or list and op is '/', treat as path navigation
        # For lists, navigate from first element
        if op == '/' and isinstance(left, list) and len(left) > 0:
            # Left is a list - navigate from first element
            # Create new context with first element as data
            item_data = left[0] if isinstance(left[0], dict) else {'value': left[0]}
            new_context = context.with_data(item_data, [])
            # Evaluate right side as path
            if isinstance(node.right, PathNode):
                # It's a PathNode
                result = node.right.evaluate(self, new_context)
            else:
                # Try to evaluate and treat as path
                right_val = node.right.evaluate(self, new_context)
                if isinstance(right_val, str):
                    result = self.path_evaluator.evaluate_path(right_val, new_context)
                else:
                    result = right_val
            return result
        
        # Special case: if left is None and op is '/', return empty list (empty node-set)
        # This handles cases like deref(...)/../fields where deref() returns None
        # In XPath, navigating from an empty node-set results in an empty node-set
        if op == '/' and left is None:
            return []
        
        # Special case: if left is a dict and op is '/', treat as path navigation
        # Extract the full path from nested BinaryOpNodes and evaluate as a single path
        if op == '/' and isinstance(left, dict):
            # Check if this node was returned by deref() - if so, use its stored path
            node_id = id(left)
            stored_path = self._deref_node_paths.get(node_id)
            
            if stored_path:
                # Node was returned by deref() - navigate from its location in data tree
                nav_context = context.with_data(context.root_data, stored_path)
            else:
                # Set the node as the current data context
                # When navigating from a node (even without stored_path), ../field should mean ./field
                # This handles cases where deref() returns a node but stored_path wasn't set
                nav_context = context.with_data(left, [])
                
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
                        elif isinstance(part, PathNode):
                            # It's a PathNode - extract step names from segments
                            path_str_parts.extend(seg.step for seg in part.segments)
                        else:
                            # Try to evaluate (for function calls, etc.)
                            if hasattr(part, 'evaluate'):
                                try:
                                    val = part.evaluate(self, nav_context)
                                    if val:
                                        path_str_parts.append(str(val))
                                except:
                                    pass
                    if path_str_parts:
                        path_str = '/'.join(path_str_parts)
                        result = self.path_evaluator.evaluate_path(path_str, nav_context)
                    else:
                        result = None
                else:
                    result = None
            elif isinstance(node.right, PathNode):
                # It's a PathNode - evaluate it directly
                # Handle .. at the start (for both with and without predicates)
                segments = list(node.right.segments)
                if segments and segments[0].step == '..':
                    # When navigating from a deref() node (or any node), YANG semantics:
                    # ../field from node means ./field (field as child of node)
                    # This is because .. from a node's location would go to its parent (list),
                    # which doesn't have the field. So we interpret it as the field within the node.
                    # This applies whether or not stored_path is set, as long as left is a dict (node)
                    if len(segments) > 1:
                        # Remove .. and try field directly from the node's location
                        direct_segments = segments[1:]
                        direct_path = '/'.join(seg.step for seg in direct_segments)
                        # Rebuild path without ..
                        from .ast import PathSegment
                        direct_node = PathNode(direct_segments, node.right.is_absolute)
                        # When navigating from a deref() node, ../fields should mean ./fields
                        # (fields as a child of the entity node)
                        # Try evaluating from the node itself as data first
                        item_context = nav_context.with_data(left, [])
                        result = direct_node.evaluate(self, item_context)
                        # If that didn't work, try from the node's location in the tree
                        if result is None or (isinstance(result, list) and len(result) == 0):
                            result = direct_node.evaluate(self, nav_context)
                        if not result:
                            # Try evaluating from the node itself as data first
                            item_context = nav_context.with_data(left, [])
                            result = self.path_evaluator.evaluate_path(direct_path, item_context)
                        # If that fails, try with .. (go up then down) as fallback
                        if result is None or (isinstance(result, list) and len(result) == 0):
                            path_str = '/'.join(seg.step for seg in segments)
                            result = self.path_evaluator.evaluate_path(path_str, nav_context)
                    else:
                        # Just .. means go up from stored_path (if set) or return the node itself
                        if stored_path:
                            path_str = '/'.join(seg.step for seg in segments)
                            result = self.path_evaluator.evaluate_path(path_str, nav_context)
                        else:
                            # No stored_path - just return the node itself
                            result = left
                else:
                    # No .. at start - evaluate normally (handles predicates automatically)
                    result = node.right.evaluate(self, nav_context)
            else:
                # Try to evaluate and treat as path
                right_val = node.right.evaluate(self, nav_context)
                if isinstance(right_val, str):
                    result = self.path_evaluator.evaluate_path(right_val, nav_context)
                else:
                    result = right_val
            return result
        
        # Short-circuit evaluation for logical operators
        if op == 'or':
            # If left is truthy, short-circuit and return True without evaluating right
            if yang_bool(left):
                return True
            # Only evaluate right if left is falsy
            right = node.right.evaluate(self, context)
            return bool(right)
        if op == 'and':
            # If left is falsy, short-circuit and return False without evaluating right
            if not yang_bool(left):
                return False
            # Only evaluate right if left is truthy
            right = node.right.evaluate(self, context)
            return bool(right)
        
        # For other operations, evaluate right normally
        right = node.right.evaluate(self, context)
        # Get type context for coercion
        type_context = self._get_type_context(context)
        
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

    def _evaluate_unary_op(self, node: UnaryOpNode, context: Context) -> JsonValue:
        """Evaluate a unary operator node.
        
        Args:
            node: Unary operator node
            context: Context for evaluation
        """
        operand = node.operand.evaluate(self, context)
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

    def _evaluate_path_node(self, node: PathNode, context: Context) -> JsonValue:
        """Evaluate a path node.
    
        Args:
            node: Path node to evaluate
            context: Context for evaluation
        """
        return self.path_evaluator.evaluate_path_node(node, context)

    def _get_type_context(self, context: Context) -> Optional[Any]:
        """
        Get the schema type for the current context.
        
        Args:
            context: Context for evaluation
            
        Returns:
            YangTypeStmt if type can be resolved, None otherwise
        """
        if not self.module or not context.original_context_path:
            return None
        
        try:
            # Navigate schema to find the type for the current context
            statements = self.module.statements
            path = context.original_context_path.copy()
            
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