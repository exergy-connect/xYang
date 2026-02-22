"""
AST nodes for XPath expressions.
"""

from typing import Any, Union

# Type alias for JSON-like values that XPath can evaluate to
# Note: This is a recursive type, so we use Any for nested structures
JsonValue = Union[dict[str, Any], list[Any], str, int, float, bool, None]

from .base import XPathNode
from .tokens import TokenType, Token
from .literal import LiteralNode
from .path import PathSegment, PathNode
from .current import CurrentNode
from .function import FunctionCallNode
from .binary_op import BinaryOpNode
from .unary_op import UnaryOpNode

__all__ = [
    'JsonValue',
    'XPathNode',
    'TokenType',
    'Token',
    'LiteralNode',
    'PathSegment',
    'PathNode',
    'CurrentNode',
    'FunctionCallNode',
    'BinaryOpNode',
    'UnaryOpNode',
]
