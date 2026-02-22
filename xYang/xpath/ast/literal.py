"""
Literal value node.
"""

from typing import Union, TYPE_CHECKING

if TYPE_CHECKING:
    from ..evaluator import XPathEvaluator
    from ..context import Context
    from . import JsonValue

from .base import XPathNode


class LiteralNode(XPathNode):
    """Literal value node (string, number, boolean)."""

    def __init__(self, value: Union[str, int, float, bool]):
        self.value = value

    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        return self.value

    def __repr__(self):
        return f"Literal({self.value!r})"
