"""
Deref evaluation logic for XPath expressions.
"""

from typing import Any, List

from .ast import FunctionCallNode, PathNode, BinaryOpNode, FunctionCallNode as FCN
from .parser import XPathTokenizer, XPathParser
from .context import Context


class DerefEvaluator:
    """Handles deref() function evaluation and leafref resolution."""
    
    def __init__(self, evaluator: Any):
        """Initialize deref evaluator with reference to main evaluator.
        
        Args:
            evaluator: The main XPathEvaluator instance
        """
        self.evaluator = evaluator
        self._visited_nodes: set = set()  # Track visited nodes for cycle detection
    
    def _parse_path_steps(self, path: str) -> tuple[List[str], bool, int]:
        """Parse a path string using AST parser and extract steps.
        
        Args:
            path: Path string to parse
            
        Returns:
            Tuple of (steps, is_absolute, up_levels)
            - steps: List of path steps (excluding '..')
            - is_absolute: True if path starts with '/'
            - up_levels: Number of '..' steps
            
        Raises:
            XPathSyntaxError: If the path cannot be parsed
        """
        tokenizer = XPathTokenizer(path)
        tokens = tokenizer.tokenize()
        parser = XPathParser(tokens, path)
        path_node = parser.parse()
        
        from ..errors import XPathSyntaxError
        
        if not isinstance(path_node, PathNode):
            raise XPathSyntaxError(f"Expected path expression, got {type(path_node).__name__}")
        
        steps = []
        up_levels = 0
        for segment in path_node.segments:
            if segment.step == '..':
                up_levels += 1
            elif segment.step and segment.step != '.':
                steps.append(segment.step)
        return steps, path_node.is_absolute, up_levels
    
    def evaluate_deref_function(self, node: FunctionCallNode, context: Context) -> Any:
        """Evaluate a deref() function call.
        
        Args:
            node: Function call node
            context: Context for evaluation
        """
        if len(node.args) == 1:
            arg_node = node.args[0]
            
            # Cache context paths to avoid repeated attribute access
            context_path = context.context_path
            original_context_path = context.original_context_path
            
            # Create cache key - use string representation of context path for efficiency
            context_str = str(context_path)
            cache_key = f"deref({id(arg_node)}):{context_str}"
            if cache_key in self.evaluator.leafref_cache:
                return self.evaluator.leafref_cache[cache_key]
            
            # Check if argument is a BinaryOpNode with '/' (path navigation from a node)
            # This handles cases like deref(deref(current())/../foreignKey/entity) and deref(./foreignKey/entity)
            if isinstance(arg_node, BinaryOpNode) and arg_node.operator == '/':
                # First, try evaluating the entire path to see if it returns a string
                # This handles cases like deref(deref(current())/../foreignKey/entity) where
                # the path evaluates to a string that needs to be resolved
                path_value = arg_node.evaluate(self.evaluator, context)
                if isinstance(path_value, str):
                    # The path evaluated to a string - we need to find the schema context
                    # from the left side node's location to resolve the leafref
                    # This will be handled by the code below that evaluates left_result
                    # So we continue to the next section
                    pass
                elif path_value is not None:
                    # Path evaluated to something else (node, list, etc.) - not a string to resolve
                    # This shouldn't happen for leafref resolution, but handle it
                    result = path_value if isinstance(path_value, dict) else None
                    self.evaluator.leafref_cache[cache_key] = result
                    return result
                
                # First check if left side is a simple path (not a function call that returns a node)
                # If so, try to check for leafref in original context first
                left_is_simple_path = isinstance(arg_node.left, PathNode) or (
                    isinstance(arg_node.left, FCN) and arg_node.left.name == 'current' and len(arg_node.left.args) == 0
                )
                
                if left_is_simple_path:
                    # Build the full path string to check for leafref in original context
                    # This handles cases like ./foreignKey/entity where we need schema context from original path
                    full_path = self.build_path_from_node(arg_node)
                    if full_path:
                        # Check if this full path points to a leafref in the original context
                        leafref_path = self.get_leafref_path_from_schema(full_path, context)
                        if leafref_path:
                            # This is a leafref - evaluate the path to get the value, then resolve
                            if path_value is None:
                                path_value = arg_node.evaluate(self.evaluator, context)
                            if path_value is not None:
                                result_tuple = self.find_node_by_leafref_path(leafref_path, path_value, context)
                                if result_tuple:
                                    result, node_path = result_tuple
                                    if node_path:
                                        self.evaluator._deref_node_paths[id(result)] = node_path
                                    self.evaluator.leafref_cache[cache_key] = result
                                else:
                                    result = None
                                    self.evaluator.leafref_cache[cache_key] = result
                            return result
                
                # Not a leafref in original context - try navigating from left side if it's a node
                # Evaluate left side (might be nested deref() or other expression)
                left_result = arg_node.left.evaluate(self.evaluator, context)
                
                # If the path already evaluated to a string, we need to resolve it using the left side's context
                if isinstance(path_value, str) and isinstance(left_result, dict):
                    # Path evaluated to a string, and left side is a node
                    # Find where the node came from to get the schema context
                    node_id = id(left_result)
                    node_path = self.evaluator._deref_node_paths.get(node_id)
                    if node_path:
                        context_to_use = node_path
                    else:
                        context_to_use = self._find_node_location_in_data(left_result, original_context_path if original_context_path else context_path)
                        if context_to_use is None:
                            context_to_use = original_context_path if original_context_path else context_path
                    
                    if context_to_use:
                        right_path = self.build_path_from_node(arg_node.right)
                        if right_path:
                            # Create a new Context for schema resolution with both paths set to context_to_use
                            schema_context = Context(
                                data=context.data,
                                context_path=context_to_use,
                                original_context_path=context_to_use,
                                original_data=context.original_data,
                                root_data=context.root_data
                            )
                            
                            # Use the right_path with the schema context
                            leafref_path = self.get_leafref_path_from_schema(right_path, schema_context)
                            if leafref_path:
                                # This is a leafref - resolve it
                                result_tuple = self.find_node_by_leafref_path(leafref_path, path_value, context)
                                if result_tuple:
                                    result, node_path = result_tuple
                                    if node_path:
                                        self.evaluator._deref_node_paths[id(result)] = node_path
                                    self.evaluator.leafref_cache[cache_key] = result
                                    return result
                
                # If left side is a node (dict), navigate from it
                if isinstance(left_result, dict):
                    # CRITICAL: When left_result is a node from deref(), we need to find where it came from
                    # deref() stores the path when it resolves a node, so check that first
                    left_node_context = None
                    node_id = id(left_result)
                    stored_path = self.evaluator._deref_node_paths.get(node_id)
                    if stored_path:
                        # Use the path that deref() stored when it resolved this node
                        left_node_context = stored_path
                    else:
                        # Node wasn't from a known deref() call - find its location
                        left_node_context = self._find_node_location_in_data(left_result, original_context_path or context_path)
                        if left_node_context is None:
                            # Cannot determine node location - cannot proceed
                            return None
                    
                    # Create new context with left_result as data and empty context_path
                    # so that .. navigates within the node structure, not up the global context path
                    # Preserve original context for schema resolution
                    nav_context = context.with_data(left_result, [])
                    
                    # Evaluate right side (path navigation)
                    right_node = arg_node.right
                    if isinstance(right_node, PathNode):
                        # It's a PathNode - navigate from the node
                        path_value = self.evaluator.path_evaluator.evaluate_path_node(right_node, nav_context)
                        # Build right_path efficiently
                        if right_node.is_absolute:
                            right_path = '/' + '/'.join(seg.step for seg in right_node.segments)
                        else:
                            right_path = '/'.join(seg.step for seg in right_node.segments)
                    elif isinstance(right_node, BinaryOpNode) and right_node.operator == '/':
                        # Nested path - extract and evaluate
                        path_parts = self.evaluator.path_evaluator.extract_path_from_binary_op(right_node)
                        if path_parts:
                            path_str = '/'.join(str(p) for p in path_parts if p)
                            path_value = self.evaluator.path_evaluator.evaluate_path(path_str, nav_context)
                            right_path = path_str
                        else:
                            path_value = None
                            right_path = None
                    else:
                        # Try to evaluate as path
                        path_value = right_node.evaluate(self.evaluator, nav_context)
                        right_path = self.build_path_from_node(right_node)
                    
                    # Now deref() the resulting value
                    # CRITICAL: deref() requires schema context - check if the path points to a leafref
                    # When navigating from a node (left_result), paths with .. are evaluated within the node
                    # (due to empty context_path), but for schema resolution we need the path relative to
                    # where the node is located (left_node_context)
                    if path_value is not None and right_path:
                        # Convert the path for schema resolution:
                        # - If path starts with .., it was evaluated within the node (empty context_path)
                        # - For schema resolution, we need it relative to left_node_context
                        # - From a field node, ../foreignKey/entity should be ./foreignKey/entity
                        if right_path.startswith('../'):
                            # Extract remaining path after .. using AST parser
                            steps, _, _ = self._parse_path_steps(right_path)
                            remaining_path = '/'.join(steps)
                            # Convert to relative path from the node's location
                            schema_path = './' + remaining_path if remaining_path else '.'
                        elif not right_path.startswith('./') and not right_path.startswith('/'):
                            # Make it explicitly relative
                            schema_path = './' + right_path
                        else:
                            schema_path = right_path
                        
                        # Check if this path is a leafref in the left_node_context
                        # Create a new Context for schema resolution instead of modifying the original
                        schema_context = context.with_context_path(
                            left_node_context if left_node_context else context_path
                        )
                        # Use the new context for schema resolution - original_context_path is preserved
                        leafref_path = self.get_leafref_path_from_schema(schema_path, schema_context)
                        if leafref_path:
                            # This is a leafref - use schema-aware resolution
                            result_tuple = self.find_node_by_leafref_path(leafref_path, path_value, context)
                            if result_tuple:
                                result, node_path = result_tuple
                                if node_path:
                                    self.evaluator._deref_node_paths[id(result)] = node_path
                            else:
                                # Not a leafref - deref() requires schema context, return None
                                result = None
                    else:
                        result = None
                    
                    # Cache the result
                    self.evaluator.leafref_cache[cache_key] = result
                    return result
                    # Context object automatically preserves original_context_path
                elif isinstance(left_result, str):
                    # Left side evaluated to a string - this happens when navigating from a node
                    # and the path returns a string value (e.g., entity name from foreignKey.entity)
                    # Example: deref(deref(current())/../foreignKey/entity)
                    # - deref(current()) returns field node
                    # - /../foreignKey/entity returns "parent" (string)
                    # - deref() needs to resolve "parent" using the leafref path for foreignKey.entity
                    # Build the path string from the right side of the binary op (the navigation part)
                    right_path = self.build_path_from_node(arg_node.right)
                    
                    # Find the schema context for the path that produced this string
                    # If left side was a deref() call, find where that node came from
                    left_node = arg_node.left
                    context_to_use = None
                    
                    # If left side is a deref() call, find where the node came from
                    if isinstance(left_node, FCN) and left_node.name == 'deref' and len(left_node.args) == 1:
                        # Evaluate the inner deref() to get the node
                        inner_deref_result = left_node.evaluate(self.evaluator, context)
                        if isinstance(inner_deref_result, dict):
                            # We have the node - find where it came from
                            node_id = id(inner_deref_result)
                            node_path = self.evaluator._deref_node_paths.get(node_id)
                            if node_path:
                                # Use the node's path as the context
                                context_to_use = node_path
                            else:
                                # Try to find the node's location
                                context_to_use = self._find_node_location_in_data(inner_deref_result, original_context_path if original_context_path else context_path)
                                if context_to_use is None:
                                    # Fall back to original context
                                    context_to_use = original_context_path if original_context_path else context_path
                        else:
                            # Not a node - use original context
                            context_to_use = original_context_path if original_context_path else context_path
                    elif isinstance(left_node, PathNode):
                        # Left side is a path - evaluate it to find the context
                        path_value = left_node.evaluate(self.evaluator, context)
                        if isinstance(path_value, dict):
                            # It's a node - find its location
                            node_id = id(path_value)
                            node_path = self.evaluator._deref_node_paths.get(node_id)
                            if node_path:
                                context_to_use = node_path
                            else:
                                context_to_use = self._find_node_location_in_data(path_value, original_context_path if original_context_path else context_path)
                                if context_to_use is None:
                                    context_to_use = original_context_path if original_context_path else context_path
                        else:
                            # Use the path's context
                            context_to_use = original_context_path if original_context_path else context_path
                    else:
                        # Use original context
                        context_to_use = left_node_context if left_node_context else (original_context_path if original_context_path else context_path)
                    
                    if right_path and context_to_use:
                        # Build schema path from context + right_path
                        # Create a new Context for schema resolution with both paths set to context_to_use
                        # This ensures resolve_path_to_schema_location uses the correct context
                        schema_context = Context(
                            data=context.data,
                            context_path=context_to_use,
                            original_context_path=context_to_use,  # Set both for schema resolution
                            original_data=context.original_data,
                            root_data=context.root_data
                        )
                        
                        # Use the right_path directly with the schema context
                        # The get_leafref_path_from_schema will resolve relative paths correctly
                        leafref_path = self.get_leafref_path_from_schema(right_path, schema_context)
                        if leafref_path:
                            # This is a leafref - resolve it
                            result_tuple = self.find_node_by_leafref_path(leafref_path, left_result, context)
                            if result_tuple:
                                result, node_path = result_tuple
                                if node_path:
                                    self.evaluator._deref_node_paths[id(result)] = node_path
                                self.evaluator.leafref_cache[cache_key] = result
                                return result
                    
                    # Not a leafref or couldn't resolve - return None
                    result = None
                    self.evaluator.leafref_cache[cache_key] = result
                    return result
                else:
                    # Left side is not a node or string - treat as regular path expression
                    # Build path string from the binary op
                    path = self.build_path_from_node(arg_node)
                    result = self.evaluate_deref(path, context)
                    self.evaluator.leafref_cache[cache_key] = result
                    return result
            
            # Handle simple path expressions
            if isinstance(arg_node, PathNode):
                # Build path string first to check if it points to a leafref (optimized: avoid conditional)
                steps_str = '/'.join(seg.step for seg in arg_node.segments)
                path = '/' + steps_str if arg_node.is_absolute else steps_str
                
                # CRITICAL: For leafref nodes, deref() MUST use the schema definition's path
                # Check if this path points to a leafref field in the schema
                leafref_path = self.get_leafref_path_from_schema(path, context)
                if leafref_path:
                    # This is a leafref - use schema-aware resolution
                    # Step 1: Evaluate the path to get the leafref value
                    path_value = arg_node.evaluate(self.evaluator, context)
                    if path_value is None:
                        result = None
                    else:
                        # Step 2: Use the leafref path from schema to find the referenced node
                        result_tuple = self.find_node_by_leafref_path(leafref_path, path_value, context)
                        if result_tuple:
                            result, node_path = result_tuple
                            if node_path:
                                self.evaluator._deref_node_paths[id(result)] = node_path
                            self.evaluator.leafref_cache[cache_key] = result
                            return result
                        else:
                            self.evaluator.leafref_cache[cache_key] = None
                            return None
                
                # Not a leafref - evaluate the path to get the value
                path_value = arg_node.evaluate(self.evaluator, context)
                # If it's a dict (node), return it as-is (identity)
                if isinstance(path_value, dict):
                    result = path_value
                    self.evaluator.leafref_cache[cache_key] = result
                    return result
                # If it's a string and we have context, try to find if it's a field name or entity name
                # by checking the schema for leafref paths that could resolve it
                if isinstance(path_value, str) and (context.original_context_path or context.context_path):
                    # Try to find a leafref that could resolve this string value
                    # Check the current context path to see if we're at a field that references this
                    context_to_use = context.original_context_path if context.original_context_path else context.context_path
                    if context_to_use:
                        # Try to find a leafref path that could resolve this value
                        # For field names, the leafref might be relative like ../../fields/name
                        # For entity names, the leafref might be absolute like /data-model/entities/name
                        # We'll try both the current context and common patterns
                        schema_path = self.resolve_path_to_schema_location(path, context)
                        if schema_path:
                            schema_node = self.find_schema_node(schema_path)
                            if schema_node:
                                # Check if this field has a leafref that could resolve the value
                                from ..ast import YangLeafStmt
                                if isinstance(schema_node, YangLeafStmt):
                                    type_obj = schema_node.type
                                    if type_obj and type_obj.name == 'leafref':
                                        leafref_path = getattr(type_obj, 'path', None)
                                        if leafref_path:
                                            result_tuple = self.find_node_by_leafref_path(leafref_path, path_value, context)
                                            if result_tuple:
                                                result, node_path = result_tuple
                                                if node_path:
                                                    self.evaluator._deref_node_paths[id(result)] = node_path
                                                self.evaluator.leafref_cache[cache_key] = result
                                                return result
                
                # For non-leafref paths, deref() requires schema context
                # Fallback to evaluate_deref (which will check for leafref and return None if not found)
                result = self.evaluate_deref(path, context)
                self.evaluator.leafref_cache[cache_key] = result
                return result
            elif isinstance(arg_node, FCN):
                # It's a function call - evaluate it first to get the value
                # This handles nested calls like deref(deref(current()))
                value = arg_node.evaluate(self.evaluator, context)
                
                # If the function call returned a dict (node), deref() should return it as-is (identity)
                # This handles cases like deref(deref(current())) where inner deref() returns a node
                if isinstance(value, dict):
                    result = value
                    self.evaluator.leafref_cache[cache_key] = result
                    return result
                
                # For current(), evaluate to get the value, then find the field/node by that value
                if arg_node.name == 'current' and len(arg_node.args) == 0:
                    # CRITICAL: If current() points to a leafref field, deref() MUST use the schema definition's path
                    # Use original_context_path to find the schema node for current()
                    if value is not None:
                        # If current() returns a dict (node), deref() should return it as-is (identity)
                        # This handles the case where we're already at a field node
                        if isinstance(value, dict):
                            result = value
                            self.evaluator.leafref_cache[cache_key] = result
                            return result
                        
                        # For string values, try to resolve using leafref path
                        if isinstance(value, str) and (context.original_context_path or context.context_path):
                            # Resolve the schema path from original_context_path
                            schema_path = self.resolve_path_to_schema_location('current()', context)
                            if schema_path:
                                # Find the schema node at this path
                                schema_node = self.find_schema_node(schema_path)
                                if schema_node:
                                    # Check if it's a leafref
                                    from ..ast import YangLeafStmt
                                    if isinstance(schema_node, YangLeafStmt):
                                        type_obj = schema_node.type
                                        if type_obj and type_obj.name == 'leafref':
                                            leafref_path = getattr(type_obj, 'path', None)
                                            if leafref_path:
                                                # This is a leafref - use schema-aware resolution
                                                result_tuple = self.find_node_by_leafref_path(leafref_path, value, context)
                                                if result_tuple:
                                                    result, node_path = result_tuple
                                                    if node_path:
                                                        self.evaluator._deref_node_paths[id(result)] = node_path
                                                    self.evaluator.leafref_cache[cache_key] = result
                                                    return result
                                                else:
                                                    self.evaluator.leafref_cache[cache_key] = None
                                                    return None
                    
                    # Fallback to evaluate_deref (which will check for leafref and return None if not found)
                    result = self.evaluate_deref('current()', context)
                    self.evaluator.leafref_cache[cache_key] = result
                    return result
                else:
                    # For other functions, deref() requires schema context
                    # Try as path (which will check for leafref and return None if not found)
                    path = f"{arg_node.name}()"
                    result = self.evaluate_deref(path, context)
                    self.evaluator.leafref_cache[cache_key] = result
                    return result
            else:
                # For other node types, deref() requires schema context
                # Build path string and use evaluate_deref (which will check for leafref)
                if hasattr(arg_node, 'evaluate'):
                    # Evaluate to get the value first
                    value = arg_node.evaluate(self.evaluator, context)
                    # If it's a dict (node), return it as-is (identity)
                    if isinstance(value, dict):
                        result = value
                        self.evaluator.leafref_cache[cache_key] = result
                        return result
                    # Otherwise, try as path expression
                    path = str(arg_node) if hasattr(arg_node, '__str__') else ''
                else:
                    path = str(arg_node)
                result = self.evaluate_deref(path, context)
                self.evaluator.leafref_cache[cache_key] = result
                return result
        
        # No args or invalid - cache None
        result = None
        if len(node.args) == 1:
            context_str = str(self.evaluator.context_path)
            cache_key = f"deref({id(node.args[0])}):{context_str}"
            self.evaluator.leafref_cache[cache_key] = result
        return result
    
    def evaluate_deref(self, path: str, context: Context) -> Any:
        """Evaluate deref() - resolve a leafref path.
        
        In YANG, deref() takes a leafref path and returns the node it references.
        This follows the YANG specification strictly:
        1. Evaluate the path to get the leafref value
        2. Find the schema node for the field at that path
        3. Get the leafref path definition from the schema
        4. Use that path to find the referenced node in the data
        
        Args:
            path: Path expression to evaluate (e.g., "current()", "../entity")
            context: Context for evaluation (required, never None)
        
        For example: deref(../entity)
        - Evaluates ../entity to get value (e.g., "company")
        - Finds the schema leaf for "entity" field
        - Gets its leafref path (e.g., "/data-model/entities/name")
        - Uses that path to find the node where name="company"
        """
        try:
            # Check cache first (cache context path string to avoid repeated conversion)
            context_str = str(context.context_path)
            cache_key = f"{path}:{context_str}"
            if cache_key in self.evaluator.leafref_cache:
                return self.evaluator.leafref_cache[cache_key]
            
            # Step 1: Evaluate the path to get the leafref value
            ref_value = self.evaluator.path_evaluator.evaluate_path(path, context)
            
            if ref_value is None:
                # Referenced node doesn't exist - acceptable for optional references
                return None
            
            # Step 2: Find the schema node for the field at this path
            leafref_path = self.get_leafref_path_from_schema(path, context)
            
            if not leafref_path:
                # No leafref definition found - cannot resolve
                return None
            
            # Step 3: Use the leafref path to find the referenced node
            result_tuple = self.find_node_by_leafref_path(leafref_path, ref_value, context)
            if result_tuple:
                result, node_path = result_tuple
                if node_path:
                    self.evaluator._deref_node_paths[id(result)] = node_path
                self.evaluator.leafref_cache[cache_key] = result
                return result
            self.evaluator.leafref_cache[cache_key] = None
            return None
        except Exception:
            # If path evaluation fails, deref() returns None (referenced node doesn't exist)
            return None
    
    def build_path_from_node(self, node: Any) -> str:
        """Build a path string from an AST node.
        
        Args:
            node: AST node (PathNode, FunctionCallNode, BinaryOpNode, etc.)
            
        Returns:
            Path string representation
        """
        if isinstance(node, PathNode):
            # Optimized: use join directly, avoid conditional string concatenation
            steps_str = '/'.join(seg.step for seg in node.segments)
            return '/' + steps_str if node.is_absolute else steps_str
        
        if isinstance(node, FCN):
            # Optimized: early return for common case
            if node.name == 'current' and len(node.args) == 0:
                return 'current()'
            return f"{node.name}()"
        
        if isinstance(node, BinaryOpNode) and node.operator == '/':
            # Build path from binary op
            left_path = self.build_path_from_node(node.left)
            right_path = self.build_path_from_node(node.right)
            if left_path and right_path:
                return f"{left_path}/{right_path}"
            return left_path or right_path or ''
        
        # Fallback to string representation
        return str(node) if hasattr(node, '__str__') else ''
    
    def get_leafref_path_from_schema(self, path: str, context: Context) -> str:
        """Get the leafref path definition from the schema for the field at the given path.
        
        Args:
            path: XPath expression pointing to a leafref field (e.g., "../entity", "current()")
            context: Context to use for schema resolution (required, never None)
            
        Returns:
            The leafref path string, or None if not found
        """
        # Resolve the path to find the schema node
        schema_path = self.resolve_path_to_schema_location(path, context)
        if not schema_path:
            return None
        
        # Find the schema node at that path
        schema_node = self.find_schema_node(schema_path)
        
        if not schema_node:
            # If we can't find the schema node, try alternative approaches
            # For current(), the path might need adjustment
            if path == 'current()':
                # Cache context paths to avoid repeated attribute access
                original_context = context.original_context_path
                context_to_use = original_context if original_context else context.context_path
                if context_to_use:
                    # Try to find the schema node by matching the last element of the context
                    last_part = context_to_use[-1]
                    if last_part and not isinstance(last_part, int):
                        # Try to find a schema node with this name in the parent context
                        parent_schema_path = self.data_path_to_schema_path(context_to_use[:-1])
                        if parent_schema_path:
                            parent_node = self.find_schema_node(parent_schema_path)
                            if parent_node:
                                # Search for a child with the matching name (optimized: early return)
                                statements = getattr(parent_node, 'statements', [])
                                for stmt in statements:
                                    if getattr(stmt, 'name', None) == last_part:
                                        schema_node = stmt
                                        break
            
            if not schema_node:
                return None
        
        # If schema_node is a container, try to find a 'name' leaf inside it
        # This handles cases like ../child_fk where child_fk is a container with a name leaf
        from ..ast import YangContainerStmt
        if isinstance(schema_node, YangContainerStmt):
            # Look for a 'name' leaf inside the container
            statements = getattr(schema_node, 'statements', [])
            for stmt in statements:
                from ..ast import YangLeafStmt
                if isinstance(stmt, YangLeafStmt) and getattr(stmt, 'name', None) == 'name':
                    schema_node = stmt
                    break
        
        # Check if it's a leaf with leafref type (optimized: early returns)
        from ..ast import YangLeafStmt
        if not isinstance(schema_node, YangLeafStmt):
            return None
        
        type_obj = schema_node.type
        if not type_obj or type_obj.name != 'leafref':
            return None
        
        # Get the leafref path (optimized: single attribute check)
        return getattr(type_obj, 'path', None)
    
    def resolve_path_to_schema_location(self, path: str, context: Context) -> List[str]:
        """Resolve an XPath expression to a schema location path.
        
        Args:
            path: XPath expression (e.g., "../entity", "current()", "./field")
            context: Context to use for schema resolution (required, never None)
            
        Returns:
            List of schema node names representing the full path from module root, or None
        """
        # Cache context paths to avoid repeated attribute access
        original_context = context.original_context_path
        context_to_use = original_context if original_context else context.context_path
        context_len = len(context_to_use) if context_to_use else 0
        
        # Handle current() or .
        if path == 'current()' or path == '.':
            schema_path = self.data_path_to_schema_path(context_to_use)
            # Ensure we have the full path from root
            if schema_path:
                root_container = self._get_root_container_name()
                if not root_container:
                    return None
                if schema_path[0] != root_container:
                    schema_path = [root_container] + schema_path
            return schema_path
        
        # Handle relative paths using AST parser
        if path.startswith('../') or path.startswith('./'):
            field_parts, _, up_levels = self._parse_path_steps(path)
            
            # Navigate up from context
            if up_levels == 0:
                data_path = context_to_use + field_parts
            elif up_levels <= context_len:
                data_path = context_to_use[:-up_levels] + field_parts
            else:
                return None
            
            schema_path = self.data_path_to_schema_path(data_path)
            # Ensure we have the full path from root
            if schema_path:
                root_container = self._get_root_container_name()
                if not root_container:
                    return None
                if schema_path[0] != root_container:
                    schema_path = [root_container] + schema_path
            return schema_path
        
        # Simple field name
        if path and not path.startswith('/'):
            data_path = context_to_use + [path]
            return self.data_path_to_schema_path(data_path)
        
        # Handle absolute paths using AST parser
        if path.startswith('/'):
            steps, _, _ = self._parse_path_steps(path)
            return steps
        
        return None
    
    def data_path_to_schema_path(self, data_path: List) -> List[str]:
        """Convert a data structure path to a schema path.
        
        Removes list indices and converts to schema node names.
        
        Args:
            data_path: Path in data structure (may contain integers for list indices)
            
        Returns:
            Schema path (list of node names, no indices)
        """
        # Optimized: use list comprehension with filter
        # Skip list indices (integers) and special XPath parts
        skip_parts = {'.', '..', 'current()'}
        return [str(part) for part in data_path 
                if not isinstance(part, int) and part not in skip_parts]
    
    def _get_root_container_name(self) -> str | None:
        """Get the root container name from the module.
        
        Returns:
            The name of the root container, or None if not found
        """
        module = self.evaluator.module
        if not module:
            return None
        
        # Look for the first top-level container in the module
        from ..ast import YangContainerStmt
        for stmt in module.statements:
            if isinstance(stmt, YangContainerStmt):
                return getattr(stmt, 'name', None)
        
        return None
    
    def find_schema_node(self, schema_path: List[str]) -> Any:
        """Find a schema node at the given path.
        
        Args:
            schema_path: List of schema node names
            
        Returns:
            The schema node (YangStatement), or None if not found
        """
        # Optimized: early return
        module = self.evaluator.module
        if not module or not schema_path:
            return None
        
        current_statements = module.statements
        last_node = None
        
        # Optimized: iterate through path parts with early return
        for part in schema_path:
            found = False
            # Optimized: iterate statements directly
            for stmt in current_statements:
                # Optimized: check name attribute existence once
                stmt_name = getattr(stmt, 'name', None)
                if stmt_name == part:
                    last_node = stmt
                    # Optimized: get statements attribute once
                    current_statements = getattr(stmt, 'statements', [])
                    found = True
                    break
            if not found:
                return None
        
        return last_node
    
    def find_node_by_leafref_path(self, leafref_path: str, ref_value: Any, context: Context) -> tuple[Any, List] | None:
        """Find a node in the data using a leafref path by recursively walking the tree.
        
        Args:
            leafref_path: The leafref path (e.g., "/data-model/entities/name" or "../../fields/name")
            ref_value: The value to search for
            context: Context for evaluation (required, never None)
            
        Returns:
            Tuple of (node, path) where node is the found node and path is its location in data tree,
            or None if not found
        """
        # Resolve relative paths to determine the target location using AST parser
        if leafref_path.startswith('/'):
            # Absolute path - walk from root using AST parser
            steps, _, _ = self._parse_path_steps(leafref_path)
            target_path = steps
        else:
            # Relative path - resolve relative to original context
            # Cache context paths to avoid repeated attribute access
            original_context = context.original_context_path
            context_to_use = original_context if original_context else context.context_path
            
            # Parse the relative path using AST parser
            field_parts, _, up_levels = self._parse_path_steps(leafref_path)
            
            # Build target path by going up from context, then adding field parts
            context_len = len(context_to_use)
            if up_levels > context_len:
                return None
            
            # Remove list indices when going up (optimized: list comprehension)
            context_without_indices = [p for p in context_to_use if not isinstance(p, int)]
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
        # Create new context with root_data as data for path walking
        nav_context = context.with_data(context.root_data, context.context_path)
        # For absolute paths, don't use context index (search in all entities)
        # For relative paths, use context index (search in specific entity)
        use_context_index = not leafref_path.startswith('/')
        container = self.walk_path_to_container(container_path_parts, nav_context, use_context_index=use_context_index)
        
        if container is None:
            return None
        
        # Search for the node with key_field == ref_value
        node = self.search_for_node(container, key_field, ref_value)
        if node is None:
            return None
        
        # Find the full path to the node by searching the data tree
        node_path = self._find_node_path(context.root_data, node, container_path_parts, key_field, ref_value)
        return (node, node_path) if node_path else (node, None)
    
    def _find_node_path(self, root_data: Any, target_node: Any, container_path: List[str], key_field: str, ref_value: Any) -> List | None:
        """Find the full data path to a node by recursively searching the tree.
        
        Args:
            root_data: Root data to search in
            target_node: The node to find
            container_path: Path to the container (schema path, no indices)
            key_field: The key field name
            ref_value: The key field value
            
        Returns:
            Full data path (with indices) to the node, or None if not found
        """
        def search_recursive(data: Any, path: List) -> List | None:
            """Recursively search for the target node."""
            if data is target_node:
                return path
            
            if isinstance(data, dict):
                for key, value in data.items():
                    if value is target_node:
                        return path + [key]
                    if isinstance(value, (dict, list)):
                        result = search_recursive(value, path + [key])
                        if result:
                            return result
            elif isinstance(data, list):
                for idx, item in enumerate(data):
                    if item is target_node:
                        return path + [idx]
                    if isinstance(item, (dict, list)):
                        result = search_recursive(item, path + [idx])
                        if result:
                            return result
            return None
        
        # Search from root
        return search_recursive(root_data, [])
    
    def walk_path_to_container(self, path_parts: List[str], context: Context, use_context_index: bool = True) -> Any:
        """Recursively walk down the tree following the path to find the container.
        
        This method uses context information (like entity indices) to navigate
        through lists when possible. For example, when walking to "entities/fields",
        it uses the entity index from the current context to find the specific entity.
        
        Args:
            path_parts: List of path parts (schema node names, no indices)
            context: Context for evaluation (required, never None)
            use_context_index: If False, don't use entity index from context (for absolute paths)
            
        Returns:
            The container at that path, or None if not found
        """
        # Optimized: early return
        if not path_parts:
            return context.root_data
        
        # Extract list index from context if available and requested
        # Cache context paths to avoid repeated attribute access
        original_context = context.original_context_path
        context_to_use = original_context if original_context else context.context_path
        list_idx = None
        list_name = None
        if use_context_index and context_to_use:
            context_len = len(context_to_use)
            # Find any list in the context path (generic, not hardcoded to "entities")
            # Look for pattern: [..., list_name, index, ...]
            for j in range(context_len - 1):
                if isinstance(context_to_use[j + 1], int):
                    # Found a list index - store the list name and index
                    list_name = context_to_use[j]
                    list_idx = context_to_use[j + 1]
                    break
        
        current = context.root_data
        
        for i, part in enumerate(path_parts):
            if current is None:
                return None
            
            if isinstance(current, dict):
                if part in current:
                    next_value = current[part]
                    # Special handling: if we're navigating to a list that matches the context,
                    # and we have a list index from context AND use_context_index is True, use it
                    # This is generic - works with any list, not just "entities"
                    if (part == list_name and isinstance(next_value, list) and 
                        list_idx is not None and use_context_index):
                        if 0 <= list_idx < len(next_value):
                            current = next_value[list_idx]
                        else:
                            return None
                    else:
                        current = next_value
                else:
                    return None
            elif isinstance(current, list):
                # For lists, check if context has an index for this list part
                # Use cached context_to_use instead of accessing attribute again
                list_idx = None
                if context_to_use:
                    context_len = len(context_to_use)
                    # Optimized: iterate with explicit bounds check
                    for j in range(context_len - 1):
                        if context_to_use[j] == part:
                            next_item = context_to_use[j + 1]
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
                                result = self.walk_path_from_node(item, remaining_parts)
                                if result is not None:
                                    return result
                    return None
            else:
                return None
        
        return current
    
    def walk_path_from_node(self, node: Any, path_parts: List[str]) -> Any:
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
    
    def search_for_node(self, container: Any, key_field: str, ref_value: Any) -> Any:
        """Search for a node in the container where key_field == ref_value.
        
        Args:
            container: The container to search in (dict, list, or nested structure)
            key_field: The field name to match
            ref_value: The value to search for
            
        Returns:
            The node containing the value, or None if not found
        """
        # Optimized: early return for None
        if container is None:
            return None
        
        # Optimized: type check once, use isinstance for performance
        container_type = type(container)
        if container_type is list:
            # Search in list items - optimized iteration
            for item in container:
                if isinstance(item, dict):
                    # Check direct match first (common case - optimized: single dict lookup)
                    item_value = item.get(key_field)
                    if item_value == ref_value:
                        return item
                    # Also search recursively in nested structures
                    result = self.search_for_node(item, key_field, ref_value)
                    if result is not None:
                        return result
        elif container_type is dict:
            # Check if container itself matches (fast path - optimized: single dict lookup)
            container_value = container.get(key_field)
            if container_value == ref_value:
                return container
            # Search in nested structures (optimized: iterate values directly)
            for value in container.values():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            # Check direct match first (optimized: single dict lookup)
                            item_value = item.get(key_field)
                            if item_value == ref_value:
                                return item
                            # Recursively search nested structures
                            result = self.search_for_node(item, key_field, ref_value)
                            if result is not None:
                                return result
                elif isinstance(value, dict):
                    # Recursively search in nested dicts
                    result = self.search_for_node(value, key_field, ref_value)
                    if result is not None:
                        return result
        
        return None
    
    def _find_node_location_in_data(self, node: dict, search_context: List) -> List:
        """Find the location of a node in the data structure.
        
        Args:
            node: The node dict to find
            search_context: Context to start searching from (unused, but kept for API consistency)
            
        Returns:
            The context path where the node was found, or None
        """
        # Search recursively in the data structure
        # Start from root and search for the node
        root_data = self.evaluator.root_data
        if not root_data:
            return None
        
        # Use a helper to recursively search
        def search_recursive(data, path, target_node):
            if data is target_node or (isinstance(data, dict) and isinstance(target_node, dict) and 
                                      data == target_node):
                return path
            if isinstance(data, dict):
                for key, value in data.items():
                    result = search_recursive(value, path + [key], target_node)
                    if result:
                        return result
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    result = search_recursive(item, path + [i], target_node)
                    if result:
                        return result
            return None
        
        result_path = search_recursive(root_data, [], node)
        return result_path if result_path else None
    