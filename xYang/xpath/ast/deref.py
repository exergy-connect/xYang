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
            return self._handle_other_node(
                evaluator, deref_eval, arg_node, context, cache_key
            )
    
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
    
    def _resolve_leafref(
        self, deref_eval: Any, leafref_path: str, value: Any, context: 'Context',
        evaluator: 'XPathEvaluator', cache_key: str
    ) -> Any:
        """Resolve a leafref path and cache the result."""
        result_tuple = deref_eval.find_node_by_leafref_path(leafref_path, value, context)
        if result_tuple:
            result, node_path = result_tuple
            return self._store_result_with_path(evaluator, result, node_path, cache_key)
        return self._cache_and_return(evaluator, None, None)
    
    def _create_schema_context(
        self, context: 'Context', context_path: list
    ) -> 'Context':
        """Create a new context for schema resolution."""
        from ..context import Context
        return Context(
            data=context.data,
            context_path=context_path,
            original_context_path=context_path,
            original_data=context.original_data,
            root_data=context.root_data
        )
    
    def _find_node_context(
        self, deref_eval: Any, node: dict, evaluator: 'XPathEvaluator',
        fallback_path: list
    ) -> list | None:
        """Find the context path for a node."""
        node_id = id(node)
        stored_path = evaluator._deref_node_paths.get(node_id)
        if stored_path:
            return stored_path
        
        found_path = deref_eval._find_node_location_in_data(node, fallback_path)
        return found_path if found_path is not None else fallback_path
    
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
        
        # Check if left side is a simple path - try leafref in original context
        if self._is_simple_path(arg_node.left):
            full_path = deref_eval.build_path_from_node(arg_node)
            if full_path:
                leafref_path = deref_eval.get_leafref_path_from_schema(full_path, context)
                if leafref_path:
                    if path_value is None:
                        path_value = arg_node.evaluate(evaluator, context)
                    if path_value is not None:
                        return self._resolve_leafref(
                            deref_eval, leafref_path, path_value, context, evaluator, cache_key
                        )
        
        # Evaluate left side
        left_result = arg_node.left.evaluate(evaluator, context)
        
        # Handle string path value with node left side
        if isinstance(path_value, str) and isinstance(left_result, dict):
            return self._handle_string_path_from_node(
                evaluator, deref_eval, arg_node, path_value, left_result,
                context, cache_key, context_path, original_context_path
            )
        
        # Handle node left side
        if isinstance(left_result, dict):
            return self._handle_node_navigation(
                evaluator, deref_eval, arg_node, left_result, context, cache_key,
                context_path, original_context_path
            )
        
        # Handle string left side
        if isinstance(left_result, str):
            return self._handle_string_left_side(
                evaluator, deref_eval, arg_node, left_result, context, cache_key,
                context_path, original_context_path
            )
        
        # Fallback: treat as regular path
        path = deref_eval.build_path_from_node(arg_node)
        result = deref_eval.evaluate_deref(path, context)
        return self._cache_and_return(evaluator, result, arg_node)
    
    def _is_simple_path(self, node: Any) -> bool:
        """Check if node is a simple path (PathNode or current() call)."""
        return isinstance(node, PathNode) or (
            isinstance(node, FCN) and node.name == 'current' and len(node.args) == 0
        )
    
    def _handle_string_path_from_node(
        self, evaluator: 'XPathEvaluator', deref_eval: Any, arg_node: BinaryOpNode,
        path_value: str, left_result: dict, context: 'Context', cache_key: str,
        context_path: list, original_context_path: list
    ) -> 'JsonValue':
        """Handle case where path evaluates to string and left side is a node."""
        context_to_use = self._find_node_context(
            deref_eval, left_result, evaluator,
            original_context_path if original_context_path else context_path
        )
        
        if not context_to_use:
            return self._cache_and_return(evaluator, None, arg_node)
        
        right_path = deref_eval.build_path_from_node(arg_node.right)
        if not right_path:
            return self._cache_and_return(evaluator, None, arg_node)
        
        # For nested deref, we need to resolve the right_path relative to context_to_use
        # to find where it ends in the data structure, then get the leafref schema from there
        field_schema_context = self._create_schema_context(context, context_to_use)
        
        # Resolve the right_path to get the full schema path where it ends
        # Strip predicates first (e.g., "foreignKeys[0]/entity" -> "foreignKeys/entity")
        right_path_stripped = deref_eval._strip_predicates(right_path) if hasattr(deref_eval, '_strip_predicates') else right_path
        full_schema_path = deref_eval.resolve_path_to_schema_location(right_path_stripped, field_schema_context)
        
        if full_schema_path:
            # Create a context at the end location to get the leafref schema
            end_schema_context = self._create_schema_context(context, full_schema_path)
            leafref_path = deref_eval.get_leafref_path_from_schema("current()", end_schema_context)
        else:
            # Fallback: try with the field node context and the stripped path
            leafref_path = deref_eval.get_leafref_path_from_schema(right_path_stripped, field_schema_context)
        
        if leafref_path:
            return self._resolve_leafref(
                deref_eval, leafref_path, path_value, context, evaluator, cache_key
            )
        
        # If we still don't have a leafref path, try the fallback for entity names
        if isinstance(path_value, str):
            root_container = deref_eval._get_root_container_name()
            if root_container:
                entity_path = f"/{root_container}/entities/name"
                result_tuple = deref_eval.find_node_by_leafref_path(entity_path, path_value, context)
                if result_tuple:
                    result, node_path = result_tuple
                    return self._store_result_with_path(evaluator, result, node_path, cache_key)
        
        return self._cache_and_return(evaluator, None, arg_node)
    
    def _handle_node_navigation(
        self, evaluator: 'XPathEvaluator', deref_eval: Any, arg_node: BinaryOpNode,
        left_result: dict, context: 'Context', cache_key: str,
        context_path: list, original_context_path: list
    ) -> 'JsonValue':
        """Handle navigation from a node (left side is a dict)."""
        left_node_context = self._find_node_context(
            deref_eval, left_result, evaluator, original_context_path or context_path
        )
        
        if left_node_context is None:
            return self._cache_and_return(evaluator, None, arg_node)
        
        # Navigate from the node
        nav_context = context.with_data(left_result, [])
        right_node = arg_node.right
        path_value, right_path = self._evaluate_right_side(
            evaluator, deref_eval, right_node, nav_context
        )
        
        if path_value is None or not right_path:
            return self._cache_and_return(evaluator, None, arg_node)
        
        # Convert path for schema resolution
        schema_path = self._normalize_path_for_schema(deref_eval, right_path)
        schema_context = context.with_context_path(
            left_node_context if left_node_context else context_path
        )
        
        leafref_path = deref_eval.get_leafref_path_from_schema(schema_path, schema_context)
        if leafref_path:
            result_tuple = deref_eval.find_node_by_leafref_path(leafref_path, path_value, context)
            if result_tuple:
                result, node_path = result_tuple
                return self._store_result_with_path(evaluator, result, node_path, cache_key)
        
        return self._cache_and_return(evaluator, None, arg_node)
    
    def _evaluate_right_side(
        self, evaluator: 'XPathEvaluator', deref_eval: Any,
        right_node: Any, nav_context: 'Context'
    ) -> tuple[Any, str | None]:
        """Evaluate right side of binary op and return (value, path_string)."""
        if isinstance(right_node, PathNode):
            path_value = evaluator.path_evaluator.evaluate_path_node(right_node, nav_context)
            if right_node.is_absolute:
                right_path = '/' + '/'.join(seg.step for seg in right_node.segments)
            else:
                right_path = '/'.join(seg.step for seg in right_node.segments)
            return path_value, right_path
        
        if isinstance(right_node, BinaryOpNode) and right_node.operator == '/':
            path_parts = evaluator.path_evaluator.extract_path_from_binary_op(right_node)
            if path_parts:
                path_str = '/'.join(str(p) for p in path_parts if p)
                path_value = evaluator.path_evaluator.evaluate_path(path_str, nav_context)
                return path_value, path_str
            return None, None
        
        # Try to evaluate as path
        path_value = right_node.evaluate(evaluator, nav_context)
        right_path = deref_eval.build_path_from_node(right_node)
        return path_value, right_path
    
    def _normalize_path_for_schema(self, deref_eval: Any, path: str) -> str:
        """Normalize path for schema resolution (convert ../ to ./)."""
        if path.startswith('../'):
            # Extract remaining path after .. using parser
            steps, _, _ = deref_eval._parse_path_steps(path)
            remaining_path = '/'.join(steps)
            return './' + remaining_path if remaining_path else '.'
        elif not path.startswith('./') and not path.startswith('/'):
            return './' + path
        return path
    
    def _handle_string_left_side(
        self, evaluator: 'XPathEvaluator', deref_eval: Any, arg_node: BinaryOpNode,
        left_result: str, context: 'Context', cache_key: str,
        context_path: list, original_context_path: list
    ) -> 'JsonValue':
        """Handle case where left side evaluates to a string."""
        right_path = deref_eval.build_path_from_node(arg_node.right)
        context_to_use = self._find_context_for_left_node(
            evaluator, deref_eval, arg_node.left, context, context_path, original_context_path
        )
        
        if not right_path or not context_to_use:
            return self._cache_and_return(evaluator, None, arg_node)
        
        schema_context = self._create_schema_context(context, context_to_use)
        leafref_path = deref_eval.get_leafref_path_from_schema(right_path, schema_context)
        
        if leafref_path:
            return self._resolve_leafref(
                deref_eval, leafref_path, left_result, context, evaluator, cache_key
            )
        
        return self._cache_and_return(evaluator, None, arg_node)
    
    def _find_context_for_left_node(
        self, evaluator: 'XPathEvaluator', deref_eval: Any, left_node: Any,
        context: 'Context', context_path: list, original_context_path: list
    ) -> list:
        """Find context path for left node of binary op."""
        fallback = original_context_path if original_context_path else context_path
        
        if isinstance(left_node, FCN) and left_node.name == 'deref' and len(left_node.args) == 1:
            inner_result = left_node.evaluate(evaluator, context)
            if isinstance(inner_result, dict):
                return self._find_node_context(deref_eval, inner_result, evaluator, fallback)
            return fallback
        
        if isinstance(left_node, PathNode):
            path_value = left_node.evaluate(evaluator, context)
            if isinstance(path_value, dict):
                return self._find_node_context(deref_eval, path_value, evaluator, fallback)
            return fallback
        
        return fallback
    
    def _handle_path_node(
        self, evaluator: 'XPathEvaluator', deref_eval: Any, arg_node: PathNode,
        context: 'Context', cache_key: str, context_path: list, original_context_path: list
    ) -> 'JsonValue':
        """Handle deref() with PathNode argument."""
        steps_str = '/'.join(seg.step for seg in arg_node.segments)
        path = '/' + steps_str if arg_node.is_absolute else steps_str
        
        # Check if this is a leafref
        leafref_path = deref_eval.get_leafref_path_from_schema(path, context)
        if leafref_path:
            path_value = arg_node.evaluate(evaluator, context)
            if path_value is not None:
                return self._resolve_leafref(
                    deref_eval, leafref_path, path_value, context, evaluator, cache_key
                )
            return self._cache_and_return(evaluator, None, arg_node)
        
        # Not a leafref - evaluate path
        path_value = arg_node.evaluate(evaluator, context)
        
        # If it's a node, return as-is
        if isinstance(path_value, dict):
            return self._cache_and_return(evaluator, path_value, arg_node)
        
        # Try to resolve string value as leafref
        if isinstance(path_value, str) and (original_context_path or context_path):
            context_to_use = original_context_path if original_context_path else context_path
            if context_to_use:
                schema_path = deref_eval.resolve_path_to_schema_location(path, context)
                if schema_path:
                    schema_node = deref_eval.find_schema_node(schema_path)
                    if schema_node:
                        from ...ast import YangLeafStmt
                        if isinstance(schema_node, YangLeafStmt):
                            type_obj = schema_node.type
                            if type_obj and type_obj.name == 'leafref':
                                leafref_path = getattr(type_obj, 'path', None)
                                if leafref_path:
                                    return self._resolve_leafref(
                                        deref_eval, leafref_path, path_value, context, evaluator, cache_key
                                    )
        
        # Fallback
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
                schema_path = deref_eval.resolve_path_to_schema_location('current()', context)
                if schema_path:
                    schema_node = deref_eval.find_schema_node(schema_path)
                    if schema_node:
                        from ...ast import YangLeafStmt
                        if isinstance(schema_node, YangLeafStmt):
                            type_obj = schema_node.type
                            if type_obj and type_obj.name == 'leafref':
                                leafref_path = getattr(type_obj, 'path', None)
                                if leafref_path:
                                    return self._resolve_leafref(
                                        deref_eval, leafref_path, value, context, evaluator, cache_key
                                    )
            
            result = deref_eval.evaluate_deref('current()', context)
            return self._cache_and_return(evaluator, result, arg_node)
        
        # Other functions
        path = f"{arg_node.name}()"
        result = deref_eval.evaluate_deref(path, context)
        return self._cache_and_return(evaluator, result, arg_node)
    
    def _handle_other_node(
        self, evaluator: 'XPathEvaluator', deref_eval: Any, arg_node: Any,
        context: 'Context', cache_key: str
    ) -> 'JsonValue':
        """Handle deref() with other node types."""
        if hasattr(arg_node, 'evaluate'):
            value = arg_node.evaluate(evaluator, context)
            if isinstance(value, dict):
                return self._cache_and_return(evaluator, value, arg_node)
            path = str(arg_node) if hasattr(arg_node, '__str__') else ''
        else:
            path = str(arg_node)
        
        result = deref_eval.evaluate_deref(path, context)
        return self._cache_and_return(evaluator, result, arg_node)
