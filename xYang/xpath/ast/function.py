"""
Function call nodes with evaluation logic split by function type.
"""

from typing import List, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .base import XPathNode
    from .path import PathNode
    from ..evaluator import XPathEvaluator
    from ..context import Context
    from . import JsonValue

from .base import XPathNode
from .path import PathNode


class FunctionCallNode(XPathNode):
    """Base class for function call nodes. Acts as factory for creating specific function nodes."""
    
    def __new__(cls, name: str, args: List[XPathNode]):
        """Factory method to create the appropriate subclass based on function name."""
        # Lazy import to avoid circular dependency
        from .deref import DerefFunctionNode
        
        function_map = {
            'count': CountFunctionNode,
            'deref': DerefFunctionNode,
            'string-length': StringLengthFunctionNode,
            'translate': TranslateFunctionNode,
            'current': CurrentFunctionNode,
            'true': TrueFunctionNode,
            'false': FalseFunctionNode,
            'bool': BoolFunctionNode,
            'number': NumberFunctionNode,
            'string': StringFunctionNode,
            'not': NotFunctionNode,
        }
        
        node_class = function_map.get(name.lower())
        if node_class:
            instance = super().__new__(node_class)
            instance.name = name
            instance.args = args
            return instance
        
        # Fallback to base class if function not recognized
        instance = super().__new__(cls)
        instance.name = name
        instance.args = args
        return instance
    
    def __init__(self, name: str, args: List[XPathNode]):
        """Initialize function call node."""
        self.name = name
        self.args = args
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Evaluate function call. Should be overridden by subclasses."""
        raise NotImplementedError(f"Function {self.name} not implemented")
    
    def __repr__(self):
        args_str = ", ".join(repr(arg) for arg in self.args)
        return f"Function({self.name}({args_str}))"


class CountFunctionNode(FunctionCallNode):
    """count() function node."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Handle count() function - needs special handling before arg evaluation."""
        if len(self.args) == 1:
            arg_node = self.args[0]
            # If it's a path node, evaluate it directly
            if isinstance(arg_node, PathNode):
                path_value = evaluator.path_evaluator.evaluate_path_node(arg_node, context)
                if isinstance(path_value, list):
                    return len(path_value)
                # If result is a single dict (from predicate filtering), count as 1
                # This handles cases where a predicate filters to a single item
                if isinstance(path_value, dict):
                    return 1
                return 0
            # Otherwise evaluate normally
            arg_value = arg_node.evaluate(evaluator, context)
            if isinstance(arg_value, list):
                return len(arg_value)
            # If result is a single dict (from predicate filtering), count as 1
            if isinstance(arg_value, dict):
                return 1
            return 0
        return 0


class StringLengthFunctionNode(FunctionCallNode):
    """string-length() function node."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Handle string-length() function."""
        if len(self.args) == 1:
            arg_value = self.args[0].evaluate(evaluator, context)
            return len(str(arg_value or ''))
        return 0


class TranslateFunctionNode(FunctionCallNode):
    """translate() function node."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Handle translate() function."""
        if len(self.args) == 3:
            source_val = self.args[0].evaluate(evaluator, context)
            from_chars_val = self.args[1].evaluate(evaluator, context)
            to_chars_val = self.args[2].evaluate(evaluator, context)
            
            source = str(source_val or '')
            from_chars = str(from_chars_val or '').strip("'\"")
            to_chars = str(to_chars_val or '').strip("'\"")
            
            # In XPath translate(), if to_chars is shorter, extra from_chars are deleted
            if not to_chars:
                # Delete all from_chars
                result = ''.join(c for c in source if c not in from_chars) if from_chars else source
            else:
                # Map from_chars to to_chars, delete extras
                trans_dict = {}
                to_len = len(to_chars)
                for i, char in enumerate(from_chars):
                    trans_dict[ord(char)] = to_chars[i] if i < to_len else None
                result = source.translate(trans_dict)
            return result
        return ''


class CurrentFunctionNode(FunctionCallNode):
    """current() function node."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Handle current() function."""
        # Pass evaluator for per-evaluator caching (thread safety)
        return context.current(evaluator)


class TrueFunctionNode(FunctionCallNode):
    """true() function node."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Handle true() function."""
        return True


class FalseFunctionNode(FunctionCallNode):
    """false() function node."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Handle false() function."""
        return False


class BoolFunctionNode(FunctionCallNode):
    """bool() function node."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Handle bool() function following XPath 1.0 semantics.
        
        XPath 1.0 bool() function:
        - Python False -> XPath false() (returns False)
        - Python True -> XPath true() (returns True)
        - Then falls through to XPath 1.0 string/number coercion rules
        """
        if len(self.args) == 1:
            value = self.args[0].evaluate(evaluator, context)
            # Explicitly handle Python booleans first (XPath-aware boolean semantics)
            # This ensures Python False -> XPath false() and Python True -> XPath true()
            # before falling through to XPath 1.0 string/number coercion rules
            if isinstance(value, bool):
                return value
            # For other types, use yang_bool which handles YANG/JSON boolean strings
            # and then falls through to XPath 1.0 coercion rules
            from ..utils import yang_bool
            return yang_bool(value)
        return False


class NumberFunctionNode(FunctionCallNode):
    """number() function node."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Handle number() function."""
        from ..utils import xpath_number
        if len(self.args) == 1:
            arg_value = self.args[0].evaluate(evaluator, context)
            return xpath_number(arg_value)
        # number() with no args converts current context node to number
        # Pass evaluator for per-evaluator caching (thread safety)
        return xpath_number(context.current(evaluator))


class StringFunctionNode(FunctionCallNode):
    """string() function node."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Handle string() function following XPath 1.0 semantics.
        
        XPath 1.0 string() function:
        - If no argument, converts current context node to string
        - If one argument, converts that argument to string
        - Numbers: convert to string representation (no scientific notation for integers)
        - Booleans: "true" or "false"
        - Node sets: string value of first node (if list, first element)
        - None/empty: empty string ""
        """
        from ..utils import xpath_string
        
        if len(self.args) == 1:
            arg_value = self.args[0].evaluate(evaluator, context)
            return xpath_string(arg_value)
        # string() with no args converts current context node to string
        # Pass evaluator for per-evaluator caching (thread safety)
        return xpath_string(context.current(evaluator))


class NotFunctionNode(FunctionCallNode):
    """not() function node."""
    
    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        """Handle not() function."""
        if len(self.args) == 1:
            operand = self.args[0].evaluate(evaluator, context)
            # In XPath, not() returns true if value is false/empty/None, false if value exists
            # Optimized: check most common cases first
            if operand is None or operand is False or operand == '':
                return True
            if isinstance(operand, (list, dict)):
                return len(operand) == 0
            return False
        return True
