"""
Function call node.
"""

from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from .base import XPathNode
    from ..evaluator import XPathEvaluator
    from ..context import Context
    from . import JsonValue

from .base import XPathNode


class FunctionCallNode(XPathNode):
    """Function call node."""

    def __init__(self, name: str, args: List[XPathNode]):
        self.name = name
        self.args = args

    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        # pylint: disable=protected-access
        return evaluator._evaluate_function_node(self, context)

    def __repr__(self):
        args_str = ", ".join(repr(arg) for arg in self.args)
        return f"Function({self.name}({args_str}))"
