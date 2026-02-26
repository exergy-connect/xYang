"""
Minimal XPath evaluator for YANG must/when expressions.

Implements only the XPath features used in meta-model.yang:
- Path navigation (../, ../../, etc.)
- Functions: string-length(), translate(), count(), deref(), current(), not(), true(), false(), bool(), contains(), substring-before(), substring-after()
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
from .schema_leafref_resolver import SchemaLeafrefResolver
from .predicate_evaluator import PredicateEvaluator
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
        self._current_cache: Dict[tuple, Any] = {}  # Cache for current() results (per-evaluator for thread safety)
        
        # Context state (set from Context object when evaluating)
        self.data = data
        self.context_path: List[str] = context_path or []
        self.original_context_path: List[str] = context_path.copy() if context_path else []
        self.original_data = data
        
        # Initialize sub-evaluators
        self.path_evaluator = PathEvaluator(self)
        self.deref_evaluator = SchemaLeafrefResolver(self)
        self.predicate_evaluator = PredicateEvaluator(self)

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
        # FunctionCallNode subclasses now handle their own evaluation
        return node.evaluate(self, context)


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