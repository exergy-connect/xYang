"""
AST nodes for XPath expressions (new pipeline).

All nodes support the Visitor pattern: accept(visitor) calls the
appropriate visit_* method and returns the result.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List, Optional, Union

if TYPE_CHECKING:
    from .visitor import Visitor

# JSON-like value for evaluation results
JsonValue = Union[dict, list, str, int, float, bool, None]


class ExprNode(ABC):
    """Base for all XPath expression AST nodes."""

    def accept(self, visitor: Visitor) -> Any:
        """Dispatch to visitor. Override in subclasses."""
        raise NotImplementedError


@dataclass
class PathSegment:
    """One step in a path (e.g. 'name', '..') with optional predicate."""
    step: str
    predicate: Optional['ExprNode'] = None


class PathNode(ExprNode):
    """Path expression: segments (and optional predicates), absolute flag."""

    def __init__(
        self,
        segments: List[PathSegment],
        is_absolute: bool = False,
    ):
        self.segments = segments
        self.is_absolute = is_absolute

    def accept(self, visitor: Visitor) -> Any:
        return visitor.visit_path_node(self)


@dataclass
class LiteralNode(ExprNode):
    """String or number literal."""
    value: Union[str, int, float, bool]

    def accept(self, visitor: Visitor) -> Any:
        return visitor.visit_literal(self)


@dataclass
class BinaryOpNode(ExprNode):
    """Binary operator: =, !=, <, >, <=, >=, and, or, +, -, etc."""
    operator: str
    left: ExprNode
    right: ExprNode

    def accept(self, visitor: Visitor) -> Any:
        return visitor.visit_binary_op(self)


@dataclass
class UnaryOpNode(ExprNode):
    """Unary operator: not."""
    operator: str
    operand: ExprNode

    def accept(self, visitor: Visitor) -> Any:
        return visitor.visit_unary_op(self)


@dataclass
class FunctionCallNode(ExprNode):
    """Function call: current(), count(), not(), true(), false(), etc."""
    name: str
    args: List[ExprNode]

    def accept(self, visitor: Visitor) -> Any:
        return visitor.visit_function_call(self)
