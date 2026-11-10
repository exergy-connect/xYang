"""
Optional validation of ``anydata`` subtree contents (JSON / RFC 7951 names).

Reference: draft-ietf-netmod-yang-anydata-validation (anydata-complete / anydata-candidate
aligned with RFC 7950 §8.3.3). Callers supply a ``dict[module_name, YangModule]``; xYang
does not parse ``ietf-yang-library`` instance data.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Tuple

from ...ast import YangLeafStmt
from ...module import YangModule
from ...encoding import resolve_qualified_top_level
from ...validator.document_validator import DocumentValidator
from ...validator.path_builder import PathBuilder
from ...validator.validation_error import ValidationError


class AnydataValidationMode(str, Enum):
    """How strictly to validate children of an ``anydata`` node."""

    COMPLETE = "complete"
    CANDIDATE = "candidate"


def parse_anydata_extension_kwargs(
    kwargs: Dict[str, Any],
) -> Tuple[Dict[str, YangModule], AnydataValidationMode]:
    """Validate ``enable_extension(ANYDATA_VALIDATION, ...)`` keyword arguments."""
    rest = dict(kwargs)
    try:
        modules = rest.pop("modules")
    except KeyError as e:
        raise TypeError("ANYDATA_VALIDATION requires keyword argument 'modules'") from e
    mode = rest.pop("mode", AnydataValidationMode.COMPLETE)
    if rest:
        raise TypeError(f"unexpected keyword arguments: {sorted(rest)!r}")
    if not isinstance(modules, dict):
        raise TypeError("'modules' must be a dict[str, YangModule]")
    if not isinstance(mode, AnydataValidationMode):
        raise TypeError("'mode' must be an AnydataValidationMode")
    for k, v in modules.items():
        if not isinstance(k, str):
            raise TypeError("module map keys must be str (YANG module names)")
        if not isinstance(v, YangModule):
            raise TypeError(f"modules[{k!r}] must be a YangModule")
        if v.name != k:
            raise TypeError(f"modules dict key {k!r} must match YangModule.name {v.name!r}")
    return modules, mode


def _rewrite_located(value: str, anydata_path: str, json_key: str, schema_local_name: str) -> str:
    """Use RFC 7951 ``json_key`` in a display path or JSON Pointer."""
    inner_prefix = anydata_path.rstrip("/") + "/" + schema_local_name
    public_prefix = anydata_path.rstrip("/") + "/" + json_key
    if value == inner_prefix:
        return public_prefix
    if value.startswith(inner_prefix + "/"):
        return public_prefix + value[len(inner_prefix) :]
    return value


def _rewrite_error_path(
    err: ValidationError,
    anydata_path: str,
    json_key: str,
    schema_local_name: str,
) -> ValidationError:
    """Use RFC 7951 ``json_key`` in paths; inner :class:`DocumentValidator` uses schema names."""
    return ValidationError(
        path=_rewrite_located(err.path, anydata_path, json_key, schema_local_name),
        message=err.message,
        expression=err.expression,
        severity=err.severity,
        code=err.code,
        pointer=_rewrite_located(err.pointer, anydata_path, json_key, schema_local_name),
    )


def run_anydata_subtree_validation(
    outer: DocumentValidator,
    value: Dict[str, Any],
    anydata_path: str,
) -> None:
    """Validate ``value`` (JSON object under ``anydata``) and append to ``outer._errors``."""
    cfg = outer._anydata_validation
    if cfg is None:
        return
    modules: Dict[str, YangModule] = cfg["modules"]
    mode = cfg["mode"]
    constraint = mode == AnydataValidationMode.COMPLETE
    segments = [s for s in anydata_path.strip("/").split("/") if s]

    for json_key, child_val in value.items():
        stmt, mod = resolve_qualified_top_level(json_key, modules)
        if stmt is None or mod is None:
            member_path = f"{anydata_path.rstrip('/')}/{json_key}"
            outer._errors.append(
                ValidationError(
                    path=member_path,
                    message=(
                        f"Unknown anydata member {json_key!r}: "
                        "no matching module:identifier in the provided module map"
                    ),
                    code="unknown-field",
                    pointer=member_path,
                )
            )
            continue

        if isinstance(stmt, YangLeafStmt):
            member_path = f"{anydata_path.rstrip('/')}/{json_key}"
            outer._errors.append(
                ValidationError(
                    path=member_path,
                    message=(
                        f"anydata member {json_key!r} maps to a leaf; "
                        "nested subtree validation expects a container or list"
                    ),
                    code="type",
                    pointer=member_path,
                )
            )
            continue

        fragment = {stmt.name: child_val}
        inner = DocumentValidator(
            mod,
            enabled_features_by_module=outer._enabled_features_by_module,
            constraint_checks=constraint,
        )
        inner_pb = PathBuilder(initial_segments=segments)
        sub_errors = inner.validate(
            fragment,
            leafref_severity=outer._leafref_severity,
            leafref_root_data=outer._root_data,
            path=inner_pb,
        )
        for err in sub_errors:
            outer._errors.append(_rewrite_error_path(err, anydata_path, json_key, stmt.name))


__all__ = [
    "AnydataValidationMode",
    "parse_anydata_extension_kwargs",
    "run_anydata_subtree_validation",
]
