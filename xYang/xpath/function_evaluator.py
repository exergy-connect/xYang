"""
Function evaluation logic for XPath expressions.
"""

from typing import Any, Callable, Dict

from .ast import FunctionCallNode, PathNode
from .utils import yang_bool, xpath_number


class FunctionEvaluator:
    """Handles function evaluation in XPath expressions."""
    
    def __init__(self, evaluator: Any):
        """Initialize function evaluator with reference to main evaluator.
        
        Args:
            evaluator: The main XPathEvaluator instance
        """
        self.evaluator = evaluator
        # Initialize function dispatch dictionary
        self._function_handlers: Dict[str, Callable[[list], Any]] = {
            'string-length': self._handle_string_length,
            'translate': self._handle_translate,
            'current': self._handle_current,
            'true': self._handle_true,
            'false': self._handle_false,
            'bool': self._handle_bool,
            'number': self._handle_number,
            'not': self._handle_not,
        }
    
    def evaluate_function(self, node: FunctionCallNode) -> Any:
        """Evaluate a function call node."""
        func_name = node.name

        # Special cases that need to be handled before argument evaluation
        if func_name == 'count':
            return self._handle_count(node)
        
        if func_name == 'deref':
            return self.evaluator.deref_evaluator.evaluate_deref_function(node)

        # For other functions, evaluate arguments normally
        args = [arg.evaluate(self.evaluator) for arg in node.args]

        # Look up handler in dictionary
        handler = self._function_handlers.get(func_name)
        if handler:
            return handler(args)
        
        return None
    
    def _handle_count(self, node: FunctionCallNode) -> int:
        """Handle count() function - needs special handling before arg evaluation."""
        if len(node.args) == 1:
            arg_node = node.args[0]
            # If it's a path node, evaluate it directly
            if isinstance(arg_node, PathNode):
                path_value = self.evaluator.path_evaluator.evaluate_path_node(arg_node)
                if isinstance(path_value, list):
                    return len(path_value)
                return 0
            # Otherwise evaluate normally
            arg_value = arg_node.evaluate(self.evaluator)
            if isinstance(arg_value, list):
                return len(arg_value)
            return 0
        return 0
    
    def _handle_string_length(self, args: list) -> int:
        """Handle string-length() function."""
        if len(args) == 1:
            return len(str(args[0] or ''))
        return 0
    
    def _handle_translate(self, args: list) -> str:
        """Handle translate() function."""
        if len(args) == 3:
            source = str(args[0] or '')
            from_chars = str(args[1] or '').strip("'\"")
            to_chars = str(args[2] or '').strip("'\"")
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
    
    def _handle_current(self, args: list) -> Any:
        """Handle current() function."""
        return self.evaluator._get_current_value()
    
    def _handle_true(self, args: list) -> bool:
        """Handle true() function."""
        return True
    
    def _handle_false(self, args: list) -> bool:
        """Handle false() function."""
        return False
    
    def _handle_bool(self, args: list) -> bool:
        """Handle bool() function following XPath 1.0 semantics.
        
        XPath 1.0 bool() function:
        - Python False -> XPath false() (returns False)
        - Python True -> XPath true() (returns True)
        - Then falls through to XPath 1.0 string/number coercion rules
        """
        if len(args) == 1:
            value = args[0]
            # Explicitly handle Python booleans first (XPath-aware boolean semantics)
            # This ensures Python False -> XPath false() and Python True -> XPath true()
            # before falling through to XPath 1.0 string/number coercion rules
            if isinstance(value, bool):
                return value
            # For other types, use yang_bool which handles YANG/JSON boolean strings
            # and then falls through to XPath 1.0 coercion rules
            return yang_bool(value)
        return False
    
    def _handle_number(self, args: list) -> float:
        """Handle number() function."""
        if len(args) == 1:
            return xpath_number(args[0])
        # number() with no args converts current context node to number
        return xpath_number(self.evaluator._get_current_value())
    
    def _handle_not(self, args: list) -> bool:
        """Handle not() function."""
        if len(args) == 1:
            operand = args[0]
            # In XPath, not() returns true if value is false/empty/None, false if value exists
            # Optimized: check most common cases first
            if operand is None or operand is False or operand == '':
                return True
            if isinstance(operand, (list, dict)):
                return len(operand) == 0
            return False
        return True
