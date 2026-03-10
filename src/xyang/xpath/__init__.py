"""
xpath: YANG XPath evaluator with schema-aware Node(data, schema, parent).

Mental model:
    Context(current, root) - fixed for one expression evaluation.
    Node(data, schema, parent) - variable cursor; constructed on every path step.

Visitor methods receive (ev, ctx, node). current() returns the validation anchor.
"""

from .ast import (
    ASTNode,
    BinaryOpNode,
    FunctionCallNode,
    LiteralNode,
    PathNode,
    PathSegment,
)
from .evaluator import XPathEvaluator
from .functions import FUNCTIONS
from .node import Context, Node
from .schema_nav import SchemaNav
from .utils import (
    compare_eq,
    compare_gt,
    compare_lt,
    first_value,
    is_nodeset,
    node_set_values,
    yang_bool,
)
from .parser import XPathParser
from .tokens import Token, TokenType
from .tokenizer import XPathTokenizer

__all__ = [
    "ASTNode",
    "BinaryOpNode",
    "Context",
    "FunctionCallNode",
    "FUNCTIONS",
    "LiteralNode",
    "Node",
    "PathNode",
    "PathSegment",
    "SchemaNav",
    "XPathEvaluator",
    "XPathParser",
    "Token",
    "TokenType",
    "XPathTokenizer",
    "compare_eq",
    "compare_gt",
    "compare_lt",
    "first_value",
    "is_nodeset",
    "node_set_values",
    "yang_bool",
]
