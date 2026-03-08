"""
New XPath handling: parser → AST → Visitor for resolution.

Use for when (and later must) expressions. AST nodes use accept(visitor);
ResolverVisitor resolves against data and schema.
"""

from .ast import (
    ExprNode,
    PathNode,
    PathSegment,
    LiteralNode,
    BinaryOpNode,
    UnaryOpNode,
    FunctionCallNode,
)
from .parser import XPathParser as XPathParserNew
from .visitor import Visitor
from .resolver import ResolverVisitor

__all__ = [
    'ExprNode',
    'PathNode',
    'PathSegment',
    'LiteralNode',
    'BinaryOpNode',
    'UnaryOpNode',
    'FunctionCallNode',
    'XPathParserNew',
    'Visitor',
    'ResolverVisitor',
]
