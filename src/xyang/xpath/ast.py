"""
AST nodes for xpath XPath expressions.

All nodes support: accept(ev, ctx, node) -> value.
"""

from __future__ import annotations

from typing import Any, List, Optional

# Forward reference for evaluator (avoid circular import)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .evaluator import XPathEvaluator
    from .node import Context, Node


class ASTNode:
    """Base for all AST nodes."""

    def accept(
        self,
        ev: "XPathEvaluator",
        ctx: "Context",
        node: "Node",
    ) -> Any:
        raise NotImplementedError


class LiteralNode(ASTNode):
    def __init__(self, value: Any):
        self.value = value

    def accept(self, ev: "XPathEvaluator", ctx: "Context", node: "Node") -> Any:
        return self.value


class PathSegment:
    def __init__(self, step: str, predicate: Optional[ASTNode] = None):
        self.step = step
        self.predicate = predicate
        # Module a ``prefix:name`` or ``prefix:*`` step is bound to; set by ``bind_xpath_prefixes``
        # from the prefixes of the module that wrote the expression (RFC 7950 §6.4.1).
        self.module: Optional[str] = None

    @property
    def prefix(self) -> Optional[str]:
        """Lexical prefix of a ``prefix:name`` or ``prefix:*`` step, else ``None``."""
        if self.step in (".", "..") or ":" not in self.step:
            return None
        return self.step.partition(":")[0]

    @property
    def local(self) -> str:
        """Local name of the step (``name`` for ``prefix:name``)."""
        return self.step.partition(":")[2] if ":" in self.step else self.step

    @property
    def is_wildcard(self) -> bool:
        """``*`` or ``prefix:*`` (XPath 1.0 NameTest)."""
        return self.step == "*" or self.step.endswith(":*")


class PathNode(ASTNode):
    def __init__(
        self,
        segments: List[PathSegment],
        is_absolute: bool = False,
        is_cacheable: bool = True,
    ):
        self.segments = segments
        self.is_absolute = is_absolute
        self.is_cacheable = is_cacheable
        # True once ``bind_xpath_prefixes`` has bound this path's prefixed steps.
        self.bound = False

    def accept(self, ev: "XPathEvaluator", ctx: "Context", node: "Node") -> Any:
        return ev.eval_path(self, ctx, node)

    def to_string(self) -> str:
        """Serialize path to string (e.g. for error messages)."""
        prefix = "/" if self.is_absolute else ""
        return prefix + "/".join(seg.step for seg in self.segments)


class BinaryOpNode(ASTNode):
    def __init__(self, left: ASTNode, operator: str, right: ASTNode):
        self.left = left
        self.operator = operator
        self.right = right

    def accept(self, ev: "XPathEvaluator", ctx: "Context", node: "Node") -> Any:
        return ev.eval_binary(self, ctx, node)


class FunctionCallNode(ASTNode):
    def __init__(self, name: str, args: List[ASTNode]):
        self.name = name
        self.args = args

    def accept(self, ev: "XPathEvaluator", ctx: "Context", node: "Node") -> Any:
        return ev.eval_function(self, ctx, node)


def ast_is_const_false(node: Optional[ASTNode]) -> bool:
    """True if *node* is an XPath AST that always evaluates to false.

    Used for schema pruning (e.g. ``must`` under ``uses`` expansion).
    :class:`~xyang.xpath.parser.XPathParser` turns ``false`` / ``false()`` into
    :class:`LiteralNode` with ``value is False`` (not :class:`FunctionCallNode`).
    """
    return isinstance(node, LiteralNode) and node.value is False
