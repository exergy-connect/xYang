"""
XPath evaluator for xpath.

Stateless YANG XPath evaluator.
ctx is passed unchanged through the entire evaluation of one expression.
node is replaced on every path step.
"""

from __future__ import annotations

from typing import Any, Callable, List

from .ast import ASTNode, BinaryOpNode, FunctionCallNode, PathNode
from .functions import FUNCTIONS
from .node import Context, Node
from .schema_nav import SchemaNav
from .utils import (
    compare_eq,
    compare_gt,
    compare_lt,
    first_value,
    is_nodeset,
    yang_bool,
)


def _bin_plus(left: Any, right: Any) -> Any:
    lv, rv = first_value(left), first_value(right)
    try:
        return float(lv) + float(rv)
    except (TypeError, ValueError):
        return float("nan")


def _bin_minus(left: Any, right: Any) -> Any:
    lv, rv = first_value(left), first_value(right)
    try:
        return float(lv) - float(rv)
    except (TypeError, ValueError):
        return float("nan")


_BINARY_OP_HANDLERS: dict[str, Callable[[Any, Any], Any]] = {
    "=": compare_eq,
    "!=": lambda l, r: not compare_eq(l, r),
    "<": compare_lt,
    ">": compare_gt,
    "<=": lambda l, r: compare_eq(l, r) or compare_lt(l, r),
    ">=": lambda l, r: compare_eq(l, r) or compare_gt(l, r),
    "+": _bin_plus,
    "-": _bin_minus,
}


class XPathEvaluator:
    """
    Stateless YANG XPath evaluator.
    The same evaluator instance can be reused across expressions.
    """

    def eval(self, ast: ASTNode, ctx: Context, node: Node) -> Any:
        return ast.accept(self, ctx, node)

    # ------------------------------------------------------------------
    # Path
    # ------------------------------------------------------------------

    def eval_path(self, path: PathNode, ctx: Context, node: Node) -> List[Node]:
        """
        Resolve a path expression. Returns a node-set (list of Node).
        Absolute paths start from ctx.root. Relative paths start from node.
        """
        nodes: List[Node] = [ctx.root if path.is_absolute else node]

        for seg in path.segments:
            if seg.step == ".":
                pass
            elif seg.step == "..":
                nodes = [n.parent for n in nodes if n.parent is not None]
            else:
                next_nodes: List[Node] = []
                for n in nodes:
                    next_nodes.extend(self._step(n, seg.step))
                nodes = next_nodes

            if seg.predicate is not None:
                nodes = self._apply_predicate(nodes, seg.predicate, ctx)

        return nodes

    def _step(self, node: Node, key: str) -> List[Node]:
        """
        Step from node into child named key.
        List expansion is determined by schema type (YangListStmt / YangLeafListStmt).
        When current node is a list (data is list), expand to entries then step key from each.
        """
        data = node.data
        if isinstance(data, list) and (
            SchemaNav.is_list(node.schema) or SchemaNav.is_leaf_list(node.schema)
        ):
            # At a list node; expand to list entries and step key from each
            return [
                n
                for item in data
                for n in self._step(node.step(item, node.schema), key)
            ]

        schema_child = SchemaNav.child(node.schema, key)

        if isinstance(data, dict):
            if key in data:
                val = data[key]
                if val is None:
                    val = True  # presence container / empty leaf
            else:
                val = SchemaNav.default(schema_child)
        else:
            val = None

        if val is None:
            return []

        if SchemaNav.is_list(schema_child) or SchemaNav.is_leaf_list(schema_child):
            if isinstance(val, list):
                return [node.step(item, schema_child) for item in val]
            return [node.step(val, schema_child)]

        return [node.step(val, schema_child)]

    def _apply_predicate(
        self,
        nodes: List[Node],
        predicate: ASTNode,
        ctx: Context,
    ) -> List[Node]:
        """Filter nodes by predicate. Numeric predicate [N] keeps the Nth node (1-based)."""
        if not nodes:
            return []
        results: List[Node] = []
        for i, n in enumerate(nodes):
            val = self.eval(predicate, ctx, n)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                if int(val) == i + 1:
                    results.append(n)
            elif yang_bool(val):
                results.append(n)
        return results

    # ------------------------------------------------------------------
    # Binary operators
    # ------------------------------------------------------------------

    def eval_binary(self, ast: BinaryOpNode, ctx: Context, node: Node) -> Any:
        op = ast.operator

        if op == "or":
            if yang_bool(self.eval(ast.left, ctx, node)):
                return True
            return yang_bool(self.eval(ast.right, ctx, node))

        if op == "and":
            if not yang_bool(self.eval(ast.left, ctx, node)):
                return False
            return yang_bool(self.eval(ast.right, ctx, node))

        if op == "/":
            return self._eval_composition(ast, ctx, node)

        left = self.eval(ast.left, ctx, node)
        right = self.eval(ast.right, ctx, node)

        handler = _BINARY_OP_HANDLERS.get(op)
        return handler(left, right) if handler is not None else None

    def _eval_composition(
        self, ast: BinaryOpNode, ctx: Context, node: Node
    ) -> List[Node]:
        """Path composition: left/right. Evaluates right within each Node produced by left."""
        left = self.eval(ast.left, ctx, node)

        left_nodes = (
            left
            if is_nodeset(left)
            else [left]
            if isinstance(left, Node)
            else []
        )

        results: List[Node] = []
        for n in left_nodes:
            r = self.eval(ast.right, ctx, n)
            if is_nodeset(r):
                results.extend(r)
            elif isinstance(r, Node):
                results.append(r)
        return results

    # ------------------------------------------------------------------
    # Functions
    # ------------------------------------------------------------------

    def eval_function(
        self, ast: FunctionCallNode, ctx: Context, node: Node
    ) -> Any:
        fn = FUNCTIONS.get(ast.name.lower())
        return fn(self, ast, ctx, node) if fn is not None else None
