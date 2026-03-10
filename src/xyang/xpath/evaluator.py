"""
XPath evaluator for xpath.

Stateless YANG XPath evaluator.
ctx is passed unchanged through the entire evaluation of one expression.
node is replaced on every path step.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List

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
    node_chain,
    yang_bool,
)

logger = logging.getLogger(__name__)


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
    Path results are cached per run in ctx.path_cache (absolute and relative).
    """

    __slots__ = ("_cache_lookups", "_cache_hits")

    def __init__(self) -> None:
        self._cache_lookups = 0
        self._cache_hits = 0

    def clear_cache_stats(self) -> None:
        """Reset cache stats. Call at start of each validation run."""
        self._cache_lookups = 0
        self._cache_hits = 0

    def get_cache_stats(self) -> dict[str, Any]:
        """Return cache hit ratio and efficiency stats for the current run."""
        return {
            "lookups": self._cache_lookups,
            "hits": self._cache_hits,
            "hit_ratio": (
                self._cache_hits / self._cache_lookups
                if self._cache_lookups else 0.0
            ),
        }

    def eval(self, ast: ASTNode, ctx: Context, node: Node) -> Any:
        """
        Evaluate one XPath expression.

        If ctx.path_cache is not None, it is used as a global cache. Only absolute
        cacheable paths (see eval_path) are looked up and stored there; relative
        paths are never cached, even within the same expression.
        """
        return ast.accept(self, ctx, node)

    def _eval_inner(self, ast: ASTNode, ctx: Context, node: Node) -> Any:
        """Evaluate and return value. Used for predicates and composition."""
        if isinstance(ast, LiteralNode):
            return ast.value
        if isinstance(ast, PathNode):
            return self.eval_path(ast, ctx, node)
        if isinstance(ast, BinaryOpNode):
            return self._eval_binary_inner(ast, ctx, node)
        if isinstance(ast, FunctionCallNode):
            return self._eval_function_inner(ast, ctx, node)
        return ast.accept(self, ctx, node)

    # ------------------------------------------------------------------
    # Path
    # ------------------------------------------------------------------

    def eval_path(self, path: PathNode, ctx: Context, node: Node) -> List[Node]:
        """
        Resolve a path expression. Returns node-set.
        Only absolute, cacheable paths use ctx.path_cache (global cache).
        Cacheability is determined statically during parsing (path.is_cacheable).
        """
        key = path.to_string()
        path_cache = ctx.path_cache
        if path_cache is not None and path.is_cacheable:
            self._cache_lookups += 1
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "path_cache lookup #%d path=%r key=%r node=%r",
                    self._cache_lookups,
                    path.to_string(),
                    key,
                    node.data,
                )
            if key in path_cache:
                self._cache_hits += 1
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("path_cache HIT #%d key=%r", self._cache_hits, key)
                return path_cache[key]

        nodes = self._eval_path_inner(path, ctx, node)

        if path_cache is not None and path.is_cacheable:
            path_cache[key] = nodes
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("path_cache store key=%r nodes=%r", key, [n.data for n in nodes])

        return nodes

    def _eval_path_inner(
        self, path: PathNode, ctx: Context, node: Node
    ) -> List[Node]:
        """Evaluate path without cache. Returns nodes."""
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
                result = [node.step(item, schema_child) for item in val]
            else:
                result = [node.step(val, schema_child)]
        else:
            result = [node.step(val, schema_child)]
        return result

    def _apply_predicate(
        self,
        nodes: List[Node],
        predicate: ASTNode,
        ctx: Context,
    ) -> List[Node]:
        """Filter nodes by predicate. Returns results."""
        if not nodes:
            return []
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "_apply_predicate: %d node(s), predicate=%s",
                len(nodes),
                getattr(predicate, "to_string", lambda: repr(predicate))(),
            )
        results: List[Node] = []
        for i, n in enumerate(nodes):
            val = self._eval_inner(predicate, ctx, n)
            keep = False
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                if int(val) == i + 1:
                    keep = True
            elif yang_bool(val):
                keep = True
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("  predicate[%d] val=%r keep=%s", i, val, keep)
            if keep:
                results.append(n)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("_apply_predicate: %d -> %d result(s)", len(nodes), len(results))
        return results

    # ------------------------------------------------------------------
    # Binary operators
    # ------------------------------------------------------------------

    def eval_binary(self, ast: BinaryOpNode, ctx: Context, node: Node) -> Any:
        return self._eval_binary_inner(ast, ctx, node)

    def _eval_binary_inner(
        self, ast: BinaryOpNode, ctx: Context, node: Node
    ) -> Any:
        op = ast.operator

        if op == "or":
            left = self._eval_inner(ast.left, ctx, node)
            if yang_bool(left):
                return True
            return yang_bool(self._eval_inner(ast.right, ctx, node))

        if op == "and":
            left = self._eval_inner(ast.left, ctx, node)
            if not yang_bool(left):
                return False
            return yang_bool(self._eval_inner(ast.right, ctx, node))

        if op == "/":
            return self._eval_composition_inner(ast, ctx, node)

        left = self._eval_inner(ast.left, ctx, node)
        right = self._eval_inner(ast.right, ctx, node)
        handler = _BINARY_OP_HANDLERS.get(op)
        return handler(left, right) if handler is not None else None

    def _eval_composition_inner(
        self, ast: BinaryOpNode, ctx: Context, node: Node
    ) -> List[Node]:
        """Path composition: left/right. Returns nodes."""
        left = self._eval_inner(ast.left, ctx, node)
        left_nodes: List[Node] = (
            list(left)
            if is_nodeset(left)
            else [left]
            if isinstance(left, Node)
            else []
        )

        results: List[Node] = []
        for n in left_nodes:
            r = self._eval_inner(ast.right, ctx, n)
            if is_nodeset(r):
                results.extend(r)
            elif isinstance(r, Node):
                results.append(r)
        if logger.isEnabledFor(logging.DEBUG) and not results:
            right_repr = getattr(ast.right, "to_string", None)
            right_str = (right_repr() if callable(right_repr) else None) or type(ast.right).__name__
            logger.debug(
                "path composition produced empty result: left_nodes=%d right=%s node_chain=%s",
                len(left_nodes),
                right_str,
                node_chain(node),
            )
        return results

    # ------------------------------------------------------------------
    # Functions
    # ------------------------------------------------------------------

    def eval_function(
        self, ast: FunctionCallNode, ctx: Context, node: Node
    ) -> Any:
        return self._eval_function_inner(ast, ctx, node)

    def _eval_function_inner(
        self, ast: FunctionCallNode, ctx: Context, node: Node
    ) -> Any:
        fn = FUNCTIONS.get(ast.name.lower())
        return fn(self, ast, ctx, node) if fn is not None else None
