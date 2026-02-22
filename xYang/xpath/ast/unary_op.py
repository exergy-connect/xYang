"""
Unary operator node.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import XPathNode
    from ..evaluator import XPathEvaluator
    from ..context import Context
    from . import JsonValue

from .base import XPathNode


class UnaryOpNode(XPathNode):
    """Unary operator node (e.g., not())."""

    def __init__(self, operator: str, operand: XPathNode):
        self.operator = operator
        self.operand = operand

    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        # pylint: disable=protected-access
        return evaluator._evaluate_unary_op(self, context)

    def __repr__(self):
        return f"UnaryOp({self.operator}, {self.operand})"
