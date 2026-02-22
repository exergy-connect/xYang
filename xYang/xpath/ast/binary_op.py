"""
Binary operator nodes with evaluation logic split by operator type.
"""

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .base import XPathNode
    from .path import PathNode
    from ..evaluator import XPathEvaluator
    from ..context import Context
    from . import JsonValue

from .base import XPathNode
from .path import PathNode


class BinaryOpNode(XPathNode):
    """Base class for binary operator nodes. Acts as factory for creating specific operator nodes."""
    
    def __new__(cls, operator: str, left: XPathNode, right: XPathNode):
        """Factory method to create the appropriate subclass based on operator."""
        operator_map = {
            'or': LogicalOrNode,
            'and': LogicalAndNode,
            '=': ComparisonEqualNode,
            '!=': ComparisonNotEqualNode,
            '<=': ComparisonLessEqualNode,
            '>=': ComparisonGreaterEqualNode,
            '<': ComparisonLessNode,
            '>': ComparisonGreaterNode,
            '+': ArithmeticAddNode,
            '-': ArithmeticSubtractNode,
            '*': ArithmeticMultiplyNode,
            '/': PathNavigationNode,  # / can be path navigation or division
        }
        
        node_class = operator_map.get(operator)
        if node_class:
            instance = super().__new__(node_class)
            instance.operator = operator
            instance.left = left
            instance.right = right
            return instance
        
        # Fallback to base class if operator not recognized
        instance = super().__new__(cls)
        instance.operator = operator
        instance.left = left
        instance.right = right
        return instance
    
    def __init__(self, operator: str, left: XPathNode, right: XPathNode):
        """Initialize binary operator node."""
        self.operator = operator
        self.left = left
        self.right = right
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Evaluate binary operator. Should be overridden by subclasses."""
        raise NotImplementedError
    
    @staticmethod
    def _coerce_value(value: Any, type_context: Any, evaluator: Any) -> Any:
        """Coerce a value based on type context.
        
        Args:
            value: Value to coerce
            type_context: Schema type context (YangTypeStmt)
            evaluator: XPathEvaluator instance
            
        Returns:
            Coerced value, or original value if no coercion needed/applicable
        """
        if type_context is None:
            return value
        
        # Handle union types: try coercion in declared order, use first success
        if hasattr(type_context, 'types') and type_context.types:
            for union_type in type_context.types:
                coerced = BinaryOpNode._coerce_value_for_type(value, union_type)
                if coerced is not None:
                    return coerced
            return value
        
        # Handle simple types
        coerced = BinaryOpNode._coerce_value_for_type(value, type_context)
        return coerced if coerced is not None else value
    
    @staticmethod
    def _coerce_value_for_type(value: Any, type_stmt: Any) -> Any:
        """Coerce a value for a specific type statement."""
        if not hasattr(type_stmt, 'name'):
            return None
        
        type_name = type_stmt.name
        
        if type_name == 'boolean':
            return BinaryOpNode._coerce_boolean(value)
        elif type_name == 'int32':
            return BinaryOpNode._coerce_int32(value)
        
        return None
    
    @staticmethod
    def _coerce_boolean(value: Any) -> Any:
        """Coerce a value to boolean."""
        if isinstance(value, bool):
            return None  # Already boolean, no coercion needed
        
        if isinstance(value, str):
            value_lower = value.lower().strip()
            if value_lower == 'true':
                return True
            elif value_lower == 'false':
                return False
        
        return None  # Not coercible to boolean
    
    @staticmethod
    def _coerce_int32(value: Any) -> Any:
        """Coerce a value to int32."""
        if isinstance(value, int):
            return None  # Already integer, no coercion needed
        
        if isinstance(value, str):
            try:
                value_stripped = value.strip()
                if value_stripped and (value_stripped[0] in '+-' and value_stripped[1:].isdigit() or value_stripped.isdigit()):
                    return int(value_stripped)
            except (ValueError, AttributeError):
                pass
        
        return None  # Not coercible to int32

    def __repr__(self):
        return f"BinaryOp({self.operator}, {self.left}, {self.right})"


class LogicalOrNode(BinaryOpNode):
    """Logical OR operator (or)."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Evaluate logical OR with short-circuit evaluation."""
        from ..utils import yang_bool
        
        left = self.left.evaluate(evaluator, context)
        # If left is truthy, short-circuit and return True without evaluating right
        if yang_bool(left):
            return True
        # Only evaluate right if left is falsy
        right = self.right.evaluate(evaluator, context)
        return bool(right)


class LogicalAndNode(BinaryOpNode):
    """Logical AND operator (and)."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Evaluate logical AND with short-circuit evaluation."""
        from ..utils import yang_bool
        
        left = self.left.evaluate(evaluator, context)
        # If left is falsy, short-circuit and return False without evaluating right
        if not yang_bool(left):
            return False
        # Only evaluate right if left is truthy
        right = self.right.evaluate(evaluator, context)
        return bool(right)


class ComparisonEqualNode(BinaryOpNode):
    """Equality comparison operator (=)."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Evaluate equality comparison with type coercion."""
        from ..utils import compare_equal
        
        left = self.left.evaluate(evaluator, context)
        right = self.right.evaluate(evaluator, context)
        
        type_context = evaluator._get_type_context(context)
        left_coerced = BinaryOpNode._coerce_value(left, type_context, evaluator)
        right_coerced = BinaryOpNode._coerce_value(right, type_context, evaluator)
        
        return compare_equal(left_coerced, right_coerced)


class ComparisonNotEqualNode(BinaryOpNode):
    """Inequality comparison operator (!=)."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Evaluate inequality comparison with type coercion."""
        from ..utils import compare_equal
        
        left = self.left.evaluate(evaluator, context)
        right = self.right.evaluate(evaluator, context)
        
        type_context = evaluator._get_type_context(context)
        left_coerced = BinaryOpNode._coerce_value(left, type_context, evaluator)
        right_coerced = BinaryOpNode._coerce_value(right, type_context, evaluator)
        
        return not compare_equal(left_coerced, right_coerced)


class ComparisonLessEqualNode(BinaryOpNode):
    """Less than or equal comparison operator (<=)."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Evaluate less than or equal comparison with type coercion."""
        from ..utils import compare_less_equal
        
        left = self.left.evaluate(evaluator, context)
        right = self.right.evaluate(evaluator, context)
        
        type_context = evaluator._get_type_context(context)
        left_coerced = BinaryOpNode._coerce_value(left, type_context, evaluator)
        right_coerced = BinaryOpNode._coerce_value(right, type_context, evaluator)
        
        return compare_less_equal(left_coerced, right_coerced)


class ComparisonGreaterEqualNode(BinaryOpNode):
    """Greater than or equal comparison operator (>=)."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Evaluate greater than or equal comparison with type coercion."""
        from ..utils import compare_greater_equal
        
        left = self.left.evaluate(evaluator, context)
        right = self.right.evaluate(evaluator, context)
        
        type_context = evaluator._get_type_context(context)
        left_coerced = BinaryOpNode._coerce_value(left, type_context, evaluator)
        right_coerced = BinaryOpNode._coerce_value(right, type_context, evaluator)
        
        return compare_greater_equal(left_coerced, right_coerced)


class ComparisonLessNode(BinaryOpNode):
    """Less than comparison operator (<)."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Evaluate less than comparison with type coercion."""
        from ..utils import compare_less
        
        left = self.left.evaluate(evaluator, context)
        right = self.right.evaluate(evaluator, context)
        
        type_context = evaluator._get_type_context(context)
        left_coerced = BinaryOpNode._coerce_value(left, type_context, evaluator)
        right_coerced = BinaryOpNode._coerce_value(right, type_context, evaluator)
        
        return compare_less(left_coerced, right_coerced)


class ComparisonGreaterNode(BinaryOpNode):
    """Greater than comparison operator (>)."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Evaluate greater than comparison with type coercion."""
        from ..utils import compare_greater
        
        left = self.left.evaluate(evaluator, context)
        right = self.right.evaluate(evaluator, context)
        
        type_context = evaluator._get_type_context(context)
        left_coerced = BinaryOpNode._coerce_value(left, type_context, evaluator)
        right_coerced = BinaryOpNode._coerce_value(right, type_context, evaluator)
        
        return compare_greater(left_coerced, right_coerced)


class ArithmeticAddNode(BinaryOpNode):
    """Arithmetic addition operator (+)."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Evaluate addition (string concatenation or arithmetic)."""
        left = self.left.evaluate(evaluator, context)
        right = self.right.evaluate(evaluator, context)
        
        try:
            return float(left) + float(right)
        except (ValueError, TypeError):
            return str(left) + str(right)


class ArithmeticSubtractNode(BinaryOpNode):
    """Arithmetic subtraction operator (-)."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Evaluate subtraction."""
        left = self.left.evaluate(evaluator, context)
        right = self.right.evaluate(evaluator, context)
        
        try:
            return float(left) - float(right)
        except (ValueError, TypeError):
            return None


class ArithmeticMultiplyNode(BinaryOpNode):
    """Arithmetic multiplication operator (*)."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Evaluate multiplication."""
        left = self.left.evaluate(evaluator, context)
        right = self.right.evaluate(evaluator, context)
        
        try:
            return float(left) * float(right)
        except (ValueError, TypeError):
            return None


class PathNavigationNode(BinaryOpNode):
    """Path navigation operator (/) or division operator."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Evaluate path navigation or division."""
        left = self.left.evaluate(evaluator, context)
        
        # Path navigation: if left is a dict or list and op is '/', treat as path navigation
        if isinstance(left, list) and len(left) > 0:
            # Left is a list - navigate from first element
            item_data = left[0] if isinstance(left[0], dict) else {'value': left[0]}
            new_context = context.with_data(item_data, [])
            if isinstance(self.right, PathNode):
                result = self.right.evaluate(evaluator, new_context)
            else:
                right_val = self.right.evaluate(evaluator, new_context)
                if isinstance(right_val, str):
                    result = evaluator.path_evaluator.evaluate_path(right_val, new_context)
                else:
                    result = right_val
            return result
        
        # Special case: if left is None and op is '/', return empty list (empty node-set)
        if left is None:
            return []
        
        # Special case: if left is a dict and op is '/', treat as path navigation
        if isinstance(left, dict):
            # Check if this node was returned by deref() - if so, use its stored path
            node_id = id(left)
            stored_path = evaluator._deref_node_paths.get(node_id)
            
            if stored_path:
                nav_context = context.with_data(context.root_data, stored_path)
            else:
                nav_context = context.with_data(left, [])
            
            # Extract path from nested binary ops or evaluate as path node
            if isinstance(self.right, BinaryOpNode) and self.right.operator == '/':
                path_parts = evaluator.path_evaluator.extract_path_from_binary_op(self.right)
                if path_parts:
                    path_str_parts = []
                    for part in path_parts:
                        if isinstance(part, str):
                            path_str_parts.append(part)
                        elif isinstance(part, PathNode):
                            path_str_parts.extend(seg.step for seg in part.segments)
                        else:
                            if hasattr(part, 'evaluate'):
                                try:
                                    val = part.evaluate(evaluator, nav_context)
                                    if val:
                                        path_str_parts.append(str(val))
                                except:
                                    pass
                    if path_str_parts:
                        path_str = '/'.join(path_str_parts)
                        result = evaluator.path_evaluator.evaluate_path(path_str, nav_context)
                    else:
                        result = None
                else:
                    result = None
            elif isinstance(self.right, PathNode):
                # It's a PathNode - evaluate it directly
                # Handle .. at the start (for both with and without predicates)
                segments = list(self.right.segments)
                if segments and segments[0].step == '..':
                    # When navigating from a deref() node (or any node), YANG semantics:
                    # ../field from node means ./field (field as child of node)
                    if len(segments) > 1:
                        # Remove .. and try field directly from the node's location
                        direct_segments = segments[1:]
                        direct_node = PathNode(direct_segments, self.right.is_absolute)
                        # Try evaluating from the node itself as data first
                        item_context = nav_context.with_data(left, [])
                        result = direct_node.evaluate(evaluator, item_context)
                        # If that didn't work, try from the node's location in the tree
                        if result is None or (isinstance(result, list) and len(result) == 0):
                            result = direct_node.evaluate(evaluator, nav_context)
                        if not result:
                            # Try evaluating from the node itself as data first
                            item_context = nav_context.with_data(left, [])
                            direct_path = '/'.join(seg.step for seg in direct_segments)
                            result = evaluator.path_evaluator.evaluate_path(direct_path, item_context)
                        # If that fails, try with .. (go up then down) as fallback
                        if result is None or (isinstance(result, list) and len(result) == 0):
                            path_str = '/'.join(seg.step for seg in segments)
                            result = evaluator.path_evaluator.evaluate_path(path_str, nav_context)
                    else:
                        # Just .. means go up from stored_path (if set) or return the node itself
                        if stored_path:
                            path_str = '/'.join(seg.step for seg in segments)
                            result = evaluator.path_evaluator.evaluate_path(path_str, nav_context)
                        else:
                            # No stored_path - just return the node itself
                            result = left
                else:
                    # No .. at start - evaluate normally (handles predicates automatically)
                    result = self.right.evaluate(evaluator, nav_context)
            else:
                right_val = self.right.evaluate(evaluator, nav_context)
                if isinstance(right_val, str):
                    result = evaluator.path_evaluator.evaluate_path(right_val, nav_context)
                else:
                    result = right_val
            return result
        
        # Normal division (left is not a dict/list, so treat as arithmetic)
        right = self.right.evaluate(evaluator, context)
        try:
            return float(left) / float(right)
        except (ValueError, TypeError, ZeroDivisionError):
            return None
