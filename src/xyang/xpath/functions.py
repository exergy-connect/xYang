"""
Built-in XPath functions for xpath.

Signature: (ev, ast, ctx, node) -> Any.
ctx and node follow the same contract as evaluator methods.
"""

from typing import Any, List, Optional

from .node import Node
from .utils import first_value, is_nodeset, yang_bool


def f_current(ev: Any, ast: Any, ctx: Any, node: Any) -> Any:
    """current() returns the validation anchor (as a Node) so current()/child works."""
    return ctx.current if ctx.current is not None else None


def f_not(ev: Any, ast: Any, ctx: Any, node: Any) -> Any:
    if len(ast.args) != 1:
        return None
    return not yang_bool(ev.eval(ast.args[0], ctx, node))


def f_true(ev: Any, ast: Any, ctx: Any, node: Any) -> Any:
    return True


def f_false(ev: Any, ast: Any, ctx: Any, node: Any) -> Any:
    return False


def f_count(ev: Any, ast: Any, ctx: Any, node: Any) -> Any:
    if len(ast.args) != 1:
        return 0
    val = ev.eval(ast.args[0], ctx, node)
    return len(val) if is_nodeset(val) else 1


def f_string(ev: Any, ast: Any, ctx: Any, node: Any) -> Any:
    if len(ast.args) != 1:
        return ""
    v = first_value(ev.eval(ast.args[0], ctx, node))
    return "" if v is None else str(v)


def f_number(ev: Any, ast: Any, ctx: Any, node: Any) -> Any:
    if len(ast.args) != 1:
        return float("nan")
    v = first_value(ev.eval(ast.args[0], ctx, node))
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def f_bool(ev: Any, ast: Any, ctx: Any, node: Any) -> Any:
    if len(ast.args) != 1:
        return False
    return yang_bool(ev.eval(ast.args[0], ctx, node))


def f_string_length(ev: Any, ast: Any, ctx: Any, node: Any) -> Any:
    if len(ast.args) != 1:
        return 0
    v = first_value(ev.eval(ast.args[0], ctx, node))
    return 0 if v is None else len(str(v))


def f_concat(ev: Any, ast: Any, ctx: Any, node: Any) -> Any:
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


def f_deref(ev: Any, ast: Any, ctx: Any, node: Any) -> Any:
    """
    deref(path): resolve a leafref to its target nodes.
    1. Evaluate path argument to get source nodes.
    2. Read leafref path from schema of each source node.
    3. Resolve that path from root.
    4. Filter targets whose data matches the source value.
    5. Return each match (the referenced node); use deref(...)/.. to get the container.
    """
    if len(ast.args) != 1:
        return []

    source_nodes = ev.eval(ast.args[0], ctx, node)
    if not is_nodeset(source_nodes):
        return []

    from .schema_nav import SchemaNav

    results: List[Node] = []
    for src in source_nodes:
        leafref_path = SchemaNav.leafref_path(src.schema)
        if not leafref_path:
            continue

        # YANG: path is relative to the node that contains the leafref (parent of the leaf)
        start = (
            ctx.root
            if leafref_path.is_absolute
            else (src.parent if src.parent is not None else node)
        )
        targets = ev.eval_path(leafref_path, ctx, start)

        for t in targets:
            if t.data == src.data:
                results.append(t)

    return results


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
}
