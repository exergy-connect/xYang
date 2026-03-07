"""
Literal value node and XPath 2.0-style sequence of literals.
"""

from typing import List, Union, TYPE_CHECKING

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


class SequenceNode(XPathNode):
    """XPath 2.0-style sequence of literals: ('a', 'b', 1).

    Parsed when the parser sees ( followed by a string or number literal;
    evaluates to a list of those values. In equality (e.g. path = ('integer', 'number')),
    compare_equal() treats the RHS list as "any of these", so the result is true
    when the left-hand side equals any element of the sequence.
    """

    def __init__(self, values: List[Union[str, int, float, bool]]):
        self.values = values

    def evaluate(self, evaluator: 'XPathEvaluator', context: 'Context') -> 'JsonValue':
        return list(self.values)

    def __repr__(self):
        return f"Sequence({self.values!r})"
