"""
deref() function node implementation.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..evaluator import XPathEvaluator
    from ..context import Context
    from . import JsonValue

from .function import FunctionCallNode
from .path import PathNode
from .binary_op import BinaryOpNode
from ..context import Context as ContextType

# Alias for FunctionCallNode to match schema_leafref_resolver.py pattern
FCN = FunctionCallNode


class DerefFunctionNode(FunctionCallNode):
    """deref() function node."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Handle deref() function - inlined evaluation logic."""
        if len(self.args) != 1:
            return self._cache_and_return(evaluator, None, self.args[0] if self.args else None)
        
        arg_node = self.args[0]
        deref_eval = evaluator.deref_evaluator
        context_path = context.context_path
        original_context_path = context.original_context_path
        
        # For cache key, use original_context_path if context_path is empty
        # This ensures consistent caching when evaluating from item contexts in predicates
        cache_path = context_path if context_path else (original_context_path or [])
        cache_key = self._make_cache_key(arg_node, cache_path)
        if cache_key in evaluator.leafref_cache:
            return evaluator.leafref_cache[cache_key]
        
        # Handle different argument types
        if isinstance(arg_node, BinaryOpNode) and arg_node.operator == '/':
            return self._handle_binary_op_path(
                evaluator, deref_eval, arg_node, context, cache_key, context_path, original_context_path
            )
        elif isinstance(arg_node, PathNode):
            return self._handle_path_node(
                evaluator, deref_eval, arg_node, context, cache_key, context_path, original_context_path
            )
        elif isinstance(arg_node, FCN):
            return self._handle_function_call(
                evaluator, deref_eval, arg_node, context, cache_key, context_path, original_context_path
            )
        else:
            # Fallback for other node types - just use evaluate_deref
            path = deref_eval.build_path_from_node(arg_node) if hasattr(deref_eval, 'build_path_from_node') else str(arg_node)
            result = deref_eval.evaluate_deref(path, context)
            return self._cache_and_return(evaluator, result, arg_node)
    
    def _make_cache_key(self, arg_node: Any, context_path: list) -> str:
        """Create cache key for deref() result."""
        # Use context_path if available, otherwise use empty list for cache key
        # This ensures consistent caching even when context_path is empty
        path_str = str(context_path) if context_path else "[]"
        return f"deref({id(arg_node)}):{path_str}"
    
    def _cache_and_return(
        self, evaluator: 'XPathEvaluator', result: Any, arg_node: Any = None
    ) -> 'JsonValue':
        """Cache result and return it."""
        if arg_node is not None:
            cache_key = self._make_cache_key(arg_node, evaluator.context_path)
            evaluator.leafref_cache[cache_key] = result
        return result
    
    def _store_result_with_path(
        self, evaluator: 'XPathEvaluator', result: Any, node_path: list | None, cache_key: str
    ) -> Any:
        """Store result in cache and node path mapping."""
        if node_path:
            evaluator._deref_node_paths[id(result)] = node_path
        evaluator.leafref_cache[cache_key] = result
        return result
    
    def _handle_binary_op_path(
        self, evaluator: 'XPathEvaluator', deref_eval: Any, arg_node: BinaryOpNode,
        context: 'Context', cache_key: str, context_path: list, original_context_path: list
    ) -> 'JsonValue':
        """Handle deref() with binary operator path (e.g., deref(./path/to/field))."""
        # Evaluate the entire path first
        path_value = arg_node.evaluate(evaluator, context)
        
        # If path evaluates to non-string, handle directly
        if path_value is not None and not isinstance(path_value, str):
            result = path_value if isinstance(path_value, dict) else None
            return self._cache_and_return(evaluator, result, arg_node)
        
        # Check if left side is a simple path - try evaluate_deref in original context
        if self._is_simple_path(arg_node.left):
            full_path = deref_eval.build_path_from_node(arg_node)
            if full_path:
                # Use evaluate_deref() which validates leafref and handles resolution
                result = deref_eval.evaluate_deref(full_path, context)
                if result is not None:
                    return self._cache_and_return(evaluator, result, arg_node)
        
        # If path_value is a string, try to resolve it as an entity name first
        # This handles cases like deref(deref(current())/foreignKeys[0]/entity)
        # where the expression evaluates to an entity name string
        if isinstance(path_value, str):
            from ..context import Context
            # Create a context at the root level where the string value can be resolved
            # as an entity name. We need to be at the root to resolve entity names.
            root_container = deref_eval._get_root_container_name() if hasattr(deref_eval, '_get_root_container_name') else 'data-model'
            root_path = [root_container] if root_container else []
            # Create a context at root level with the string value as current data
            # The context_path should point to where the entity name would be (entities/name)
            string_context = Context(
                data=path_value,
                context_path=root_path + ['entities', 0, 'name'],  # Point to entity name location
                original_context_path=root_path + ['entities', 0, 'name'],
                original_data=context.root_data,
                root_data=context.root_data
            )
            # Try to resolve the string as an entity name using the entity name leafref path
            # evaluate_deref will use the fallback logic to resolve entity names
            result = deref_eval.evaluate_deref('current()', string_context)
            if result is not None:
                return self._cache_and_return(evaluator, result, arg_node)
        
        # Fallback: treat as regular path
        path = deref_eval.build_path_from_node(arg_node)
        result = deref_eval.evaluate_deref(path, context)
        return self._cache_and_return(evaluator, result, arg_node)
    
    def _is_simple_path(self, node: Any) -> bool:
        """Check if node is a simple path (PathNode or current() call)."""
        return isinstance(node, PathNode) or (
            isinstance(node, FCN) and node.name == 'current' and len(node.args) == 0
        )
    
    def _handle_path_node(
        self, evaluator: 'XPathEvaluator', deref_eval: Any, arg_node: PathNode,
        context: 'Context', cache_key: str, context_path: list, original_context_path: list
    ) -> 'JsonValue':
        """Handle deref() with PathNode argument."""
        steps_str = '/'.join(seg.step for seg in arg_node.segments)
        path = '/' + steps_str if arg_node.is_absolute else steps_str
        
        # Use evaluate_deref() which validates leafref and handles resolution
        # This is the single entry point for all deref() validation
        result = deref_eval.evaluate_deref(path, context)
        return self._cache_and_return(evaluator, result, arg_node)
    
    def _handle_function_call(
        self, evaluator: 'XPathEvaluator', deref_eval: Any, arg_node: FCN,
        context: 'Context', cache_key: str, context_path: list, original_context_path: list
    ) -> 'JsonValue':
        """Handle deref() with function call argument."""
        value = arg_node.evaluate(evaluator, context)
        
        # If function returns a node, return as-is
        if isinstance(value, dict):
            return self._cache_and_return(evaluator, value, arg_node)
        
        # Handle current() function
        if arg_node.name == 'current' and len(arg_node.args) == 0:
            if value is not None and isinstance(value, dict):
                return self._cache_and_return(evaluator, value, arg_node)
            
            if isinstance(value, str) and (original_context_path or context_path):
                # Use evaluate_deref() to ensure require-instance validation is performed
                try:
                    result = deref_eval.evaluate_deref('current()', context)
                    if result is not None:
                        node_path = evaluator._deref_node_paths.get(id(result))
                        return self._store_result_with_path(evaluator, result, node_path, cache_key)
                    # If result is None and require-instance is true, evaluate_deref() would have raised an error
                    # So if we get here, require-instance is false or not set, return None
                    return self._cache_and_return(evaluator, None, arg_node)
                except Exception as e:
                    # Re-raise XPathEvaluationError from require-instance validation
                    from ...errors import XPathEvaluationError
                    if isinstance(e, XPathEvaluationError):
                        raise
                    # For other exceptions, return None
                    return self._cache_and_return(evaluator, None, arg_node)
            
            result = deref_eval.evaluate_deref('current()', context)
            return self._cache_and_return(evaluator, result, arg_node)
        
        # Other functions
        path = f"{arg_node.name}()"
        result = deref_eval.evaluate_deref(path, context)
        return self._cache_and_return(evaluator, result, arg_node)
    
