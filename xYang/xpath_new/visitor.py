"""
Visitor base for XPath AST.

Implementations (e.g. ResolverVisitor) resolve the expression against
data and schema.
"""

from abc import ABC, abstractmethod
from typing import Any

from .ast import (
    ExprNode,
    PathNode,
    LiteralNode,
    BinaryOpNode,
    UnaryOpNode,
    FunctionCallNode,
)


class Visitor(ABC):
    """Visitor for XPath AST nodes."""

    @abstractmethod
    def visit_path_node(self, node: PathNode) -> Any:
        """Visit a path expression."""
        raise NotImplementedError

    @abstractmethod
    def visit_literal(self, node: LiteralNode) -> Any:
        """Visit a literal."""
        raise NotImplementedError

    @abstractmethod
    def visit_binary_op(self, node: BinaryOpNode) -> Any:
        """Visit a binary operator."""
        raise NotImplementedError

    @abstractmethod
    def visit_unary_op(self, node: UnaryOpNode) -> Any:
        """Visit a unary operator."""
        raise NotImplementedError

    @abstractmethod
    def visit_function_call(self, node: FunctionCallNode) -> Any:
        """Visit a function call."""
        raise NotImplementedError
