"""
Entry point for xpath: Validator that holds root Node for a validation run.

Call site walks the data tree and maintains the corresponding schema node.
When a must/when expression is encountered, the caller passes the current
data value, its YangStatement AST node, and the parent Node.

Usage:
    validator = Validator(root_data, root_schema_node)
    ctx, node = validator.make_context(data, schema_node, parent_node)
    result = yang_bool(evaluator.eval(ast, ctx, node))
"""

from __future__ import annotations

from typing import Any, Optional

from .node import Context, Node


class Validator:
    """
    Stateless validator for a single YANG module validation run.
    Holds the fixed root Node so callers do not pass it on every expression evaluation.
    """

    __slots__ = ("_root",)

    def __init__(self, root_data: Any, root_schema: Any):
        self._root = Node(root_data, root_schema, None)

    def make_context(
        self,
        data: Any,
        schema: Any,
        parent: Optional[Node] = None,
    ) -> tuple[Context, Node]:
        """
        Build the (Context, Node) pair for evaluating one must/when expression.

        data / schema  -- the node being validated and its AST node
        parent         -- parent Node maintained by the data tree walker; None at root

        Returns (ctx, node) where:
            ctx  is fixed for the expression lifetime (current + root)
            node is the starting cursor for path evaluation
        """
        current_node = Node(data, schema, parent)
        ctx = Context(current=current_node, root=self._root)
        return ctx, current_node
