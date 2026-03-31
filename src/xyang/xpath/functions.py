"""
Built-in XPath functions for xpath.

Signature: (ev, ast, ctx, node) -> Any.
ctx and node follow the same contract as evaluator methods.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

from .ast import FunctionCallNode
from .node import Context, Node

if TYPE_CHECKING:
    from ..module import YangModule
    from .evaluator import XPathEvaluator
from .utils import first_value, is_nodeset, yang_bool


def f_current(ev: "XPathEvaluator", ast: FunctionCallNode, ctx: Context, node: Node) -> Any:
    """current() returns the validation anchor (as a Node) so current()/child works."""
    return ctx.current if ctx.current is not None else None


def f_not(ev: "XPathEvaluator", ast: FunctionCallNode, ctx: Context, node: Node) -> Any:
    if len(ast.args) != 1:
        return None
    return not yang_bool(ev.eval(ast.args[0], ctx, node))


def f_true(ev: "XPathEvaluator", ast: FunctionCallNode, ctx: Context, node: Node) -> Any:
    return True


def f_false(ev: "XPathEvaluator", ast: FunctionCallNode, ctx: Context, node: Node) -> Any:
    return False


def f_count(ev: "XPathEvaluator", ast: FunctionCallNode, ctx: Context, node: Node) -> Any:
    if len(ast.args) != 1:
        return 0
    val = ev.eval(ast.args[0], ctx, node)
    return len(val) if is_nodeset(val) else 1


def f_string(ev: "XPathEvaluator", ast: FunctionCallNode, ctx: Context, node: Node) -> Any:
    if len(ast.args) != 1:
        return ""
    v = first_value(ev.eval(ast.args[0], ctx, node))
    return "" if v is None else str(v)


def f_number(ev: "XPathEvaluator", ast: FunctionCallNode, ctx: Context, node: Node) -> Any:
    if len(ast.args) != 1:
        return float("nan")
    v = first_value(ev.eval(ast.args[0], ctx, node))
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def f_bool(ev: "XPathEvaluator", ast: FunctionCallNode, ctx: Context, node: Node) -> Any:
    if len(ast.args) != 1:
        return False
    return yang_bool(ev.eval(ast.args[0], ctx, node))


def f_string_length(ev: Any, ast: Any, ctx: Any, node: Any) -> Any:
    if len(ast.args) != 1:
        return 0
    v = first_value(ev.eval(ast.args[0], ctx, node))
    return 0 if v is None else len(str(v))


def f_concat(ev: "XPathEvaluator", ast: FunctionCallNode, ctx: Context, node: Node) -> Any:
    parts = []
    for arg in ast.args:
        v = first_value(ev.eval(arg, ctx, node))
        parts.append("" if v is None else str(v))
    return "".join(parts)


def f_translate(ev: Any, ast: Any, ctx: Any, node: Any) -> Any:
    if len(ast.args) != 3:
        return ""
    source = str(first_value(ev.eval(ast.args[0], ctx, node)) or "")
    from_chars = str(ev.eval(ast.args[1], ctx, node) or "").strip("'\"")
    to_chars = str(ev.eval(ast.args[2], ctx, node) or "").strip("'\"")
    if not from_chars:
        return source
    trans = {
        ord(c): (to_chars[i] if i < len(to_chars) else None)
        for i, c in enumerate(from_chars)
    }
    return source.translate(trans)


def f_deref(ev: "XPathEvaluator", ast: FunctionCallNode, ctx: Context, node: Node) -> Any:
    """
    deref(path): resolve a leafref to its target nodes.
    1. Evaluate path argument to get source nodes.
    2. Read leafref PathNode from schema of each source node.
    3. Resolve that path — absolute from ctx.root, relative from src itself.
    4. Filter targets whose data matches the source value.
    5. Return matching nodes; use deref(...)/.. to get the parent container.
    """
    if len(ast.args) != 1:
        return []

    # Evaluate argument from context node so e.g. deref(../child_fk) in a predicate
    # uses the node the must is attached to, not the predicate's cursor.
    start = ctx.current if ctx.current is not None else node
    raw = ev.eval(ast.args[0], ctx, start)
    source_nodes = (
        raw if is_nodeset(raw) else [raw] if isinstance(raw, Node) else []
    )
    if not source_nodes:
        return []

    from .schema_nav import SchemaNav

    results: List[Node] = []
    for src in source_nodes:
        leafref_path = SchemaNav.leafref_path(src.schema)
        if leafref_path is None:
            continue
        targets = ev.eval_path(leafref_path, ctx, src)
        for t in targets:
            if t.data == src.data:
                results.append(t)
    return results


def f_derived_from(
    ev: "XPathEvaluator", ast: FunctionCallNode, ctx: Context, node: Node
) -> Any:
    """derived-from(identityref, identity) — value is strict descendant of target (RFC 7950)."""
    if len(ast.args) != 2:
        return False
    from ..identity_graph import is_derived_from_strict, resolve_identity_qname
    from ..module import YangModule

    root_schema = ctx.root.schema if ctx.root is not None else None
    if not isinstance(root_schema, YangModule):
        return False
    mod = root_schema
    start = ctx.current if ctx.current is not None else node
    v1 = ev.eval(ast.args[0], ctx, start)
    if is_nodeset(v1):
        if not v1:
            return False
        v1 = v1[0].data
    elif isinstance(v1, Node):
        v1 = v1.data
    else:
        v1 = first_value(v1)
    if not isinstance(v1, str):
        return False
    v2 = first_value(ev.eval(ast.args[1], ctx, start))
    if not isinstance(v2, str):
        return False
    local_val = resolve_identity_qname(mod, v1)
    local_tgt = resolve_identity_qname(mod, v2)
    if local_val is None or local_tgt is None:
        return False
    return is_derived_from_strict(mod, local_val, local_tgt)


def f_derived_from_or_self(
    ev: "XPathEvaluator", ast: FunctionCallNode, ctx: Context, node: Node
) -> Any:
    """derived-from-or-self(identityref, identity) — equal or strict descendant."""
    if len(ast.args) != 2:
        return False
    from ..identity_graph import is_derived_from_or_self, resolve_identity_qname
    from ..module import YangModule

    root_schema = ctx.root.schema if ctx.root is not None else None
    if not isinstance(root_schema, YangModule):
        return False
    mod = root_schema
    start = ctx.current if ctx.current is not None else node
    v1 = ev.eval(ast.args[0], ctx, start)
    if is_nodeset(v1):
        if not v1:
            return False
        v1 = v1[0].data
    elif isinstance(v1, Node):
        v1 = v1.data
    else:
        v1 = first_value(v1)
    if not isinstance(v1, str):
        return False
    v2 = first_value(ev.eval(ast.args[1], ctx, start))
    if not isinstance(v2, str):
        return False
    local_val = resolve_identity_qname(mod, v1)
    local_tgt = resolve_identity_qname(mod, v2)
    if local_val is None or local_tgt is None:
        return False
    return is_derived_from_or_self(mod, local_val, local_tgt)


FUNCTIONS = {
    "current": f_current,
    "not": f_not,
    "true": f_true,
    "false": f_false,
    "count": f_count,
    "string": f_string,
    "number": f_number,
    "bool": f_bool,
    "string-length": f_string_length,
    "concat": f_concat,
    "translate": f_translate,
    "deref": f_deref,
    "derived-from": f_derived_from,
    "derived-from-or-self": f_derived_from_or_self,
}
