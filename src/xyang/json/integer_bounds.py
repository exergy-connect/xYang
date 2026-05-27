"""
Canonical JSON Schema ``minimum`` / ``maximum`` for YANG integer built-ins (RFC 7950 §4.2.4).
"""

from __future__ import annotations

from typing import Optional

# (minimum, maximum) inclusive for each built-in when no ``range`` is set on the type.
YANG_INTEGER_BOUNDS: dict[str, tuple[int, int]] = {
    "int8": (-128, 127),
    "int16": (-32768, 32767),
    "int32": (-2147483648, 2147483647),
    "int64": (-9223372036854775808, 9223372036854775807),
    "uint8": (0, 255),
    "uint16": (0, 65535),
    "uint32": (0, 4294967295),
    "uint64": (0, 18446744073709551615),
}

YANG_INTEGER_BUILTIN_NAMES = frozenset(YANG_INTEGER_BOUNDS.keys())


def _parse_range(range_str: str) -> tuple[Optional[int], Optional[int]]:
    parts = range_str.split("..", 1)
    lo: Optional[int] = None
    hi: Optional[int] = None
    if parts[0].strip() and parts[0].strip().lower() != "min":
        try:
            lo = int(parts[0].strip())
        except ValueError:
            pass
    if len(parts) > 1 and parts[1].strip() and parts[1].strip().lower() != "max":
        try:
            hi = int(parts[1].strip())
        except ValueError:
            pass
    return lo, hi


def json_integer_bounds_for_builtin(
    yang_type: str,
    range_str: Optional[str] = None,
) -> tuple[Optional[int], Optional[int]]:
    """Return JSON Schema ``minimum`` / ``maximum`` for a YANG integer built-in."""
    if yang_type not in YANG_INTEGER_BOUNDS:
        return None, None
    if range_str:
        return _parse_range(range_str)
    lo, hi = YANG_INTEGER_BOUNDS[yang_type]
    return lo, hi


def yang_integer_from_json_bounds(
    min_val: object | None,
    max_val: object | None,
) -> tuple[str, Optional[str]]:
    """
    Infer YANG integer built-in name and optional ``range`` from JSON Schema bounds.

    Returns ``(type_name, range_or_none)``.
    """
    lo = _coerce_int(min_val)
    hi = _coerce_int(max_val)

    if lo is not None and hi is not None:
        for name, (blo, bhi) in YANG_INTEGER_BOUNDS.items():
            if lo == blo and hi == bhi:
                return name, None

    range_str: Optional[str] = None
    if lo is not None or hi is not None:
        min_part = str(lo) if lo is not None else "min"
        max_part = str(hi) if hi is not None else "max"
        range_str = f"{min_part}..{max_part}"

    base = _narrowest_integer_builtin(lo, hi)
    return base, range_str


def _coerce_int(value: object | None) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _narrowest_integer_builtin(lo: Optional[int], hi: Optional[int]) -> str:
    """Pick the narrowest built-in that can hold the bounds (unsigned preferred when lo >= 0)."""
    if lo is not None and lo < 0:
        order = ("int8", "int16", "int32", "int64")
    else:
        order = ("uint8", "uint16", "uint32", "uint64", "int8", "int16", "int32", "int64")
    effective_lo = lo if lo is not None else YANG_INTEGER_BOUNDS[order[0]][0]
    effective_hi = hi if hi is not None else YANG_INTEGER_BOUNDS[order[-1]][1]
    for name in order:
        blo, bhi = YANG_INTEGER_BOUNDS[name]
        if effective_lo >= blo and effective_hi <= bhi:
            return name
    return "int64"
