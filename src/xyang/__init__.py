"""
xYang - YANG parsing and validation using xpath.

Based on xYang; uses xpath for parsing must/when expressions and for
document validation (when, structure, must, type checks).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .errors import (
    YangCircularUsesError,
    YangRefineTargetNotFoundError,
    YangSemanticError,
)
from .parser import parse_yang_file, parse_yang_string
from .validator.yang_validator import YangValidator
from .module import YangModule
from .validator.infer_required_features import infer_required_features

__all__ = [
    "parse_yang_file",
    "parse_yang_string",
    "YangModule",
    "YangValidator",
    "infer_required_features",
    "validate",
    "YangSemanticError",
    "YangCircularUsesError",
    "YangRefineTargetNotFoundError",
]


def _feature_map(
    features: Mapping[str, Iterable[str]] | None,
) -> dict[str, frozenset[str]] | None:
    """Case-file feature map ``{"module": ["f1", ...]}`` to validator sets.

    ``None`` enables every declared feature. A module missing from the mapping
    keeps all of its features. Anything else is an error.
    """
    if features is None:
        return None
    if isinstance(features, (str, bytes)) or not isinstance(features, Mapping):
        raise TypeError("features must be a mapping of module name to feature names, or None")
    normalized: dict[str, frozenset[str]] = {}
    for name, feats in features.items():
        if not isinstance(name, str) or isinstance(feats, (str, bytes)) or not isinstance(feats, Iterable):
            raise TypeError(f"features[{name!r}] must be an iterable of feature name strings")
        names = tuple(feats)
        if any(not isinstance(item, str) for item in names):
            raise TypeError(f"features[{name!r}] must be an iterable of feature name strings")
        normalized[name] = frozenset(names)
    return normalized


def validate(
    schema: str | Path | YangModule,
    data: Any,
    *,
    features: Mapping[str, Iterable[str]] | None = None,
    include_path: Iterable[str | Path] = (),
) -> dict[str, Any]:
    """Validate ``data`` against ``schema`` and return ``validate_detailed``'s dict.

    ``schema`` is a YANG file path or a parsed module. ``features`` is the
    case-file shape ``{"module": ["feature", ...]}``; ``None`` enables every
    declared feature. ``include_path`` lists extra directories for ``import``
    and ``include``, and applies only when ``schema`` is a path.
    """
    enabled = _feature_map(features)
    includes = tuple(include_path)
    if isinstance(schema, YangModule):
        if includes:
            raise ValueError("include_path applies only when schema is a path")
        module = schema
    elif isinstance(schema, (str, Path)):
        module = parse_yang_file(schema, include_path=tuple(str(path) for path in includes))
    else:
        raise TypeError(f"schema must be a path or YangModule, got {type(schema).__name__}")
    return YangValidator(module, enabled_features_by_module=enabled).validate_detailed(data)
