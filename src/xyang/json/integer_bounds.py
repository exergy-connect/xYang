"""Deprecated. Integer bounds live in :mod:`xyang.types.registry`."""

from __future__ import annotations

import warnings

from ..types.registry import (
    YANG_INTEGER_BOUNDS,
    YANG_INTEGER_BUILTIN_NAMES,
    json_integer_bounds_for_builtin,
    yang_integer_from_json_bounds,
)

warnings.warn(
    "xyang.json.integer_bounds is deprecated; import from xyang.types.registry",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "YANG_INTEGER_BOUNDS",
    "YANG_INTEGER_BUILTIN_NAMES",
    "json_integer_bounds_for_builtin",
    "yang_integer_from_json_bounds",
]
