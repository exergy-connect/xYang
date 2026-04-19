"""
Optional validation of ``anydata`` subtree contents (JSON / RFC 7951 names).

Reference: draft-ietf-netmod-yang-anydata-validation (anydata-complete / anydata-candidate
aligned with RFC 7950 §8.3.3). Callers supply a ``dict[module_name, YangModule]``; xYang
does not parse ``ietf-yang-library`` instance data.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Tuple

from ...ast import YangLeafStmt, YangStatement
from ...module import YangModule
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


def _resolve_qualified_top_level(
    json_key: str, modules: Dict[str, YangModule]
) -> Tuple[YangStatement | None, YangModule | None]:
    """RFC 7951 namespace-qualified member at the anydata root: ``module-name:node``."""
    if ":" not in json_key:
        return None, None
    mod_name, _, ident = json_key.partition(":")
    mod = modules.get(mod_name)
    if mod is None:
        return None, None
    stmt = mod.find_statement(ident)
    return stmt, mod


def _rewrite_error_path(
    err: ValidationError,
    anydata_path: str,
    json_key: str,
    schema_local_name: str,
) -> ValidationError:
    """Use RFC 7951 ``json_key`` in paths; inner :class:`DocumentValidator` uses schema names."""
    p = err.path
    inner_prefix = anydata_path.rstrip("/") + "/" + schema_local_name
    public_prefix = anydata_path.rstrip("/") + "/" + json_key
    if p == inner_prefix:
        new_path = public_prefix
    elif p.startswith(inner_prefix + "/"):
        new_path = public_prefix + p[len(inner_prefix) :]
    else:
        new_path = p
    return ValidationError(
        path=new_path,
        message=err.message,
        expression=err.expression,
        severity=err.severity,
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
        stmt, mod = _resolve_qualified_top_level(json_key, modules)
        if stmt is None or mod is None:
            outer._errors.append(
                ValidationError(
                    path=f"{anydata_path.rstrip('/')}/{json_key}",
                    message=(
                        f"Unknown anydata member {json_key!r}: "
                        "no matching module:identifier in the provided module map"
                    ),
                )
            )
            continue

        if isinstance(stmt, YangLeafStmt):
            outer._errors.append(
                ValidationError(
                    path=f"{anydata_path.rstrip('/')}/{json_key}",
                    message=(
                        f"anydata member {json_key!r} maps to a leaf; "
                        "nested subtree validation expects a container or list"
                    ),
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
            outer._errors.append(
                _rewrite_error_path(err, anydata_path, json_key, stmt.name)
            )


__all__ = [
    "AnydataValidationMode",
    "parse_anydata_extension_kwargs",
    "run_anydata_subtree_validation",
]
