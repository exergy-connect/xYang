"""
XPath evaluator for xpath.

Stateless YANG XPath evaluator.
ctx is passed unchanged through the entire evaluation of one expression.
node is replaced on every path step.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

from .ast import (
    ASTNode,
    BinaryOpNode,
    FunctionCallNode,
    LiteralNode,
    PathNode,
)
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

NON_CACHEABLE_FUNCTIONS = frozenset({"current", "deref"})


class XPathEvaluator:
    """
    Stateless YANG XPath evaluator.
    The same evaluator instance can be reused across expressions.
    Path results are cached per run in ctx.path_cache (absolute and relative).
    """

    __slots__ = (
        "_cache_abs_lookups",
        "_cache_abs_hits",
        "_cache_rel_lookups",
        "_cache_rel_hits",
    )

    def __init__(self) -> None:
        self._cache_abs_lookups = 0
        self._cache_abs_hits = 0
        self._cache_rel_lookups = 0
        self._cache_rel_hits = 0

    def clear_cache(self) -> None:
        """Reset cache stats. Call at start of each validation run."""
        self._cache_abs_lookups = 0
        self._cache_abs_hits = 0
        self._cache_rel_lookups = 0
        self._cache_rel_hits = 0

    def get_cache_stats(self) -> dict[str, Any]:
        """Return cache hit ratio and efficiency stats for the current run."""
        total_lookups = self._cache_abs_lookups + self._cache_rel_lookups
        total_hits = self._cache_abs_hits + self._cache_rel_hits
        return {
            "abs_lookups": self._cache_abs_lookups,
            "abs_hits": self._cache_abs_hits,
            "abs_hit_ratio": (
                self._cache_abs_hits / self._cache_abs_lookups
                if self._cache_abs_lookups else 0.0
            ),
            "rel_lookups": self._cache_rel_lookups,
            "rel_hits": self._cache_rel_hits,
            "rel_hit_ratio": (
                self._cache_rel_hits / self._cache_rel_lookups
                if self._cache_rel_lookups else 0.0
            ),
            "total_lookups": total_lookups,
            "total_hits": total_hits,
            "hit_ratio": total_hits / total_lookups if total_lookups else 0.0,
        }

    def eval(self, ast: ASTNode, ctx: Context, node: Node) -> Any:
        return ast.accept(self, ctx, node)

    def _eval_inner(
        self, ast: ASTNode, ctx: Context, node: Node
    ) -> Tuple[Any, bool]:
        """Evaluate and return (value, cacheable). Used for predicates and composition."""
        if isinstance(ast, LiteralNode):
            return (ast.value, True)
        if isinstance(ast, PathNode):
            nodes, cacheable = self._eval_path_inner(ast, ctx, node)
            return (nodes, cacheable)
        if isinstance(ast, BinaryOpNode):
            return self._eval_binary_inner(ast, ctx, node)
        if isinstance(ast, FunctionCallNode):
            return self._eval_function_inner(ast, ctx, node)
        # Fallback: accept and assume cacheable
        return (ast.accept(self, ctx, node), True)

    # ------------------------------------------------------------------
    # Path
    # ------------------------------------------------------------------

    def eval_path(self, path: PathNode, ctx: Context, node: Node) -> List[Node]:
        """
        Resolve a path expression. Returns a node-set (list of Node).
        Uses and populates caches when the path is cacheable.

        Absolute paths with any predicate are not cached: predicates can contain
        relative navigation (e.g. ../entity, current()) so the result is
        context-dependent and must not be reused across evaluations.
        """
        absolute_with_predicate = path.is_absolute and any(
            seg.predicate is not None for seg in path.segments
        )
        if absolute_with_predicate:
            nodes, _ = self._eval_path_inner(path, ctx, node)
            return nodes

        path_expr = path.to_string()
        if path.is_absolute:
            key = (path_expr,)
        else:
            key = (
                path_expr,
                id(node.data),
                id(ctx.current.data) if ctx.current is not None else None,
            )

        if ctx.path_cache is not None:
            if path.is_absolute:
                self._cache_abs_lookups += 1
            else:
                self._cache_rel_lookups += 1
            if key in ctx.path_cache:
                if path.is_absolute:
                    self._cache_abs_hits += 1
                else:
                    self._cache_rel_hits += 1
                cached = ctx.path_cache[key]
                logger.debug(
                    "path_cache hit: key=%r nodes=%d path=%s",
                    key,
                    len(cached),
                    path_expr,
                )
                return cached

        nodes, cacheable = self._eval_path_inner(path, ctx, node)

        if cacheable and ctx.path_cache is not None:
            ctx.path_cache[key] = nodes
            logger.debug(
                "path_cache store: key=%r nodes=%d path=%s",
                key,
                len(nodes),
                path_expr,
            )

        return nodes

    def _eval_path_inner(
        self, path: PathNode, ctx: Context, node: Node
    ) -> Tuple[List[Node], bool]:
        """Evaluate path without cache. Returns (nodes, cacheable)."""
        cacheable = True
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
                nodes, pred_cacheable = self._apply_predicate(
                    nodes, seg.predicate, ctx
                )
                cacheable = cacheable and pred_cacheable

        return (nodes, cacheable)

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
    ) -> Tuple[List[Node], bool]:
        """Filter nodes by predicate. Returns (results, cacheable)."""
        if not nodes:
            return ([], True)
        results: List[Node] = []
        cacheable = True
        for i, n in enumerate(nodes):
            val, c = self._eval_inner(predicate, ctx, n)
            cacheable = cacheable and c
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                if int(val) == i + 1:
                    results.append(n)
            elif yang_bool(val):
                results.append(n)
        return (results, cacheable)

    # ------------------------------------------------------------------
    # Binary operators
    # ------------------------------------------------------------------

    def eval_binary(self, ast: BinaryOpNode, ctx: Context, node: Node) -> Any:
        val, _ = self._eval_binary_inner(ast, ctx, node)
        return val

    def _eval_binary_inner(
        self, ast: BinaryOpNode, ctx: Context, node: Node
    ) -> Tuple[Any, bool]:
        op = ast.operator

        if op == "or":
            left, c1 = self._eval_inner(ast.left, ctx, node)
            if yang_bool(left):
                return (True, c1)
            right, c2 = self._eval_inner(ast.right, ctx, node)
            return (yang_bool(right), c1 and c2)

        if op == "and":
            left, c1 = self._eval_inner(ast.left, ctx, node)
            if not yang_bool(left):
                return (False, c1)
            right, c2 = self._eval_inner(ast.right, ctx, node)
            return (yang_bool(right), c1 and c2)

        if op == "/":
            return self._eval_composition_inner(ast, ctx, node)

        left, c1 = self._eval_inner(ast.left, ctx, node)
        right, c2 = self._eval_inner(ast.right, ctx, node)
        handler = _BINARY_OP_HANDLERS.get(op)
        result = handler(left, right) if handler is not None else None
        return (result, c1 and c2)

    def _eval_composition_inner(
        self, ast: BinaryOpNode, ctx: Context, node: Node
    ) -> Tuple[List[Node], bool]:
        """Path composition: left/right. Returns (nodes, cacheable)."""
        left, c_left = self._eval_inner(ast.left, ctx, node)
        left_nodes: List[Node] = (
            list(left)
            if is_nodeset(left)
            else [left]
            if isinstance(left, Node)
            else []
        )

        results: List[Node] = []
        cacheable = c_left
        for n in left_nodes:
            r, c_right = self._eval_inner(ast.right, ctx, n)
            cacheable = cacheable and c_right
            if is_nodeset(r):
                results.extend(r)
            elif isinstance(r, Node):
                results.append(r)
        return (results, cacheable)

    # ------------------------------------------------------------------
    # Functions
    # ------------------------------------------------------------------

    def eval_function(
        self, ast: FunctionCallNode, ctx: Context, node: Node
    ) -> Any:
        result, _ = self._eval_function_inner(ast, ctx, node)
        return result

    def _eval_function_inner(
        self, ast: FunctionCallNode, ctx: Context, node: Node
    ) -> Tuple[Any, bool]:
        cacheable = ast.name.lower() not in NON_CACHEABLE_FUNCTIONS
        fn = FUNCTIONS.get(ast.name.lower())
        result = fn(self, ast, ctx, node) if fn is not None else None
        return (result, cacheable)
