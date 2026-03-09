"""
Utilities for xpath: YANG boolean coercion, node-set helpers, comparisons.
"""

from typing import Any, List, Optional

from .node import Node

# Built-in YANG type names that need default value coercion for XPath comparison
_YANG_BOOL_TYPE = "boolean"
_YANG_INT_TYPES = frozenset(
    {"int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64"}
)
_YANG_FLOAT_TYPES = frozenset({"decimal64", "number"})


def coerce_default_value(value: Any, type_name: Optional[str]) -> Any:
    """
    Coerce a schema default value to the Python type that matches the YANG type,
    so path comparisons (e.g. /path/leaf = false()) evaluate correctly when the leaf is defaulted.

    Returns the value unchanged if type_name is None or not a built-in type (e.g. typedef).
    """
    if value is None or type_name is None:
        return value
    if type_name == _YANG_BOOL_TYPE:
        if value in (True, "true"):
            return True
        if value in (False, "false"):
            return False
    if type_name in _YANG_INT_TYPES:
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    if type_name in _YANG_FLOAT_TYPES:
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    return value


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
    """Extract scalar data values from a node-set (list of Node), single Node, or scalar."""
    if isinstance(val, list):
        return [n.data if isinstance(n, Node) else n for n in val]
    if isinstance(val, Node):
        return [val.data]
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


def _comparison_values(right: Any) -> List[Any]:
    """Right-hand side values: node-set, XPath 2.0 value list (tuple), or single scalar."""
    if isinstance(right, (list, tuple)) and (not right or not isinstance(right[0], Node)):
        return list(right)
    return node_set_values(right)


def compare_eq(left: Any, right: Any) -> bool:
    """XPath equality: node-set vs scalar or value list (tuple); type coercion."""
    lv = node_set_values(left)
    rv = _comparison_values(right)
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
