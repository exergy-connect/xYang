"""
XPath evaluator for xpath.

Stateless YANG XPath evaluator.
ctx is passed unchanged through the entire evaluation of one expression.
node is replaced on every path step.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Tuple

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

    __slots__ = ("_cache_lookups", "_cache_hits", "_cache_purged")

    def __init__(self) -> None:
        self._cache_lookups = 0
        self._cache_hits = 0
        self._cache_purged = 0

    def clear_cache_stats(self) -> None:
        """Reset cache stats. Call at start of each validation run."""
        self._cache_lookups = 0
        self._cache_hits = 0
        self._cache_purged = 0

    def get_cache_stats(self) -> dict[str, Any]:
        """Return cache hit ratio and efficiency stats for the current run."""
        return {
            "lookups": self._cache_lookups,
            "hits": self._cache_hits,
            "purged": self._cache_purged,
            "hit_ratio": (
                self._cache_hits / self._cache_lookups
                if self._cache_lookups else 0.0
            ),
        }

    def eval(self, ast: ASTNode, ctx: Context, node: Node) -> Any:
        """
        Evaluate one XPath expression with a local path cache for this expression only.

        Cache behaviour
        --------------
        If ctx.path_cache is not None, it is treated as the global (cross-expression)
        cache. For the duration of this evaluation we replace it with a local dict
        seeded from the global cache:

        1. We save the global cache reference and set ctx.path_cache = dict(global_cache)
           so that all path lookups during this expression see a mutable local dict
           that starts with any previously cached (path_string -> (value, cacheable))
           entries from the global cache.

        2. We run the expression (ast.accept). Path resolution goes through eval_path,
           which looks up and stores (nodes, cacheable) in ctx.path_cache (the local dict).
           So repeated paths in the same expression (e.g. "/a/b = 1 and /a/b = 2") hit
           the local cache; paths already in the global cache also hit on first use.

        3. In a finally block we purge the local cache of entries that are not
           cacheable (e.g. paths with context-dependent predicates). We iterate over
           a snapshot (list(local_cache.items())) and delete entries where cacheable
           is False. The local dict is left containing only cacheable results. We do
           not flush these back into the global cache here; the caller can do that or
           keep using the same context (ctx.path_cache remains the local dict after
           eval, so subsequent eval() calls with the same context will seed from that
           local dict if the caller does not replace ctx.path_cache again).

        If ctx.path_cache is None, no caching is done and we just evaluate the
        expression.
        """
        global_cache = ctx.path_cache
        if global_cache is not None:
            ctx.path_cache = dict(global_cache)
        try:
            return ast.accept(self, ctx, node)
        finally:
            if global_cache is not None:
                local_cache = ctx.path_cache  # set to dict(global_cache) in try
                assert local_cache is not None
                for key, (value, cacheable) in list(local_cache.items()):
                    if not cacheable:
                        del local_cache[key]
                        self._cache_purged += 1

    def _eval_inner(
        self, ast: ASTNode, ctx: Context, node: Node
    ) -> Tuple[Any, bool]:
        """Evaluate and return (value, cacheable). Used for predicates and composition."""
        if isinstance(ast, LiteralNode):
            return (ast.value, True)
        if isinstance(ast, PathNode):
            return self.eval_path(ast, ctx, node)
        if isinstance(ast, BinaryOpNode):
            return self._eval_binary_inner(ast, ctx, node)
        if isinstance(ast, FunctionCallNode):
            return self._eval_function_inner(ast, ctx, node)
        # Fallback: accept and assume cacheable
        return (ast.accept(self, ctx, node), True)

    # ------------------------------------------------------------------
    # Path
    # ------------------------------------------------------------------

    def eval_path(self, path: PathNode, ctx: Context, node: Node) -> Tuple[List[Node], bool]:
        """
        Resolve a path expression. Returns (node-set, cacheable).
        Uses and populates the (local) expression cache. is_cacheable only
        affects whether the result is flushed to the global cache after eval.
        """
        key = path.to_string()
        if ctx.path_cache is not None:
            self._cache_lookups += 1
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("path_cache lookup #%d key=%r", self._cache_lookups, key)
            if key in ctx.path_cache:
                self._cache_hits += 1
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("path_cache HIT #%d key=%r", self._cache_hits, key)
                return ctx.path_cache[key]

        nodes, cacheable = self._eval_path_inner(path, ctx, node)

        if ctx.path_cache is not None:
            ctx.path_cache[key] = (nodes, cacheable)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("path_cache store key=%r cacheable=%s", key, cacheable)

        return (nodes, cacheable)

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
    ) -> Tuple[List[Node], bool]:
        """Filter nodes by predicate. Returns (results, cacheable)."""
        if not nodes:
            return ([], True)
        results: List[Node] = []
        cacheable = True
        for i, n in enumerate(nodes):
            val, c = self._eval_inner(predicate, ctx, n)
            cacheable = cacheable and c
            keep = False
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                if int(val) == i + 1:
                    keep = True
            elif yang_bool(val):
                keep = True
            if keep:
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
        if logger.isEnabledFor(logging.DEBUG) and not results:
            right_repr = getattr(ast.right, "to_string", None)
            right_str = (right_repr() if callable(right_repr) else None) or type(ast.right).__name__
            logger.debug(
                "path composition produced empty result: left_nodes=%d right=%s node_chain=%s",
                len(left_nodes),
                right_str,
                node_chain(node),
            )
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
        fn = FUNCTIONS.get(ast.name.lower())
        result = fn(self, ast, ctx, node) if fn is not None else None
        return (result, False)  # for simplicity, functions are assumed not cacheable
