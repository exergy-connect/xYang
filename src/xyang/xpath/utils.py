"""
Utilities for xpath: YANG boolean coercion, node-set helpers, comparisons.
"""

from typing import Any, List

from .node import Node


def yang_bool(val: Any) -> bool:
    """YANG boolean coercion."""
    if isinstance(val, list):
        return len(val) > 0
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        return val != ""
    return val is not None


def node_set_values(val: Any) -> List[Any]:
    """Extract scalar data values from a node-set (list of Node) or scalar."""
    if isinstance(val, list):
        return [n.data if isinstance(n, Node) else n for n in val]
    return [] if val is None else [val]


def first_value(val: Any) -> Any:
    """First value from node-set or scalar."""
    vs = node_set_values(val)
    return vs[0] if vs else None


def is_nodeset(val: Any) -> bool:
    """True if val is a node-set (list of Node)."""
    return isinstance(val, list) and (not val or isinstance(val[0], Node))


def coerce_pair(l: Any, r: Any):
    """Coerce left/right for comparison (bool, numeric, or string)."""
    if isinstance(l, bool) or isinstance(r, bool):
        return yang_bool(l), yang_bool(r)
    if isinstance(l, (int, float)) and isinstance(r, (int, float)):
        return float(l), float(r)
    try:
        return float(l), float(r)
    except (TypeError, ValueError):
        return str(l).strip(), str(r).strip()


def compare_eq(left: Any, right: Any) -> bool:
    """XPath equality: node-set vs scalar; type coercion."""
    lv, rv = node_set_values(left), node_set_values(right)
    if not lv or not rv:
        return not lv and not rv
    for l in lv:
        for r in rv:
            if l is None and r is None:
                return True
            if l is None or r is None:
                continue
            cl, cr = coerce_pair(l, r)
            if cl == cr:
                return True
    return False


def compare_lt(left: Any, right: Any) -> bool:
    """XPath less-than: any pair satisfies <."""
    for l in node_set_values(left):
        for r in node_set_values(right):
            try:
                cl, cr = coerce_pair(l, r)
                if cl < cr:
                    return True
            except TypeError:
                pass
    return False


def compare_gt(left: Any, right: Any) -> bool:
    """XPath greater-than: any pair satisfies >."""
    for l in node_set_values(left):
        for r in node_set_values(right):
            try:
                cl, cr = coerce_pair(l, r)
                if cl > cr:
                    return True
            except TypeError:
                pass
    return False
