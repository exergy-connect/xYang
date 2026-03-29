"""Builders for instance data that validates against examples/meta-model.yang."""

from __future__ import annotations

from typing import Any

DEFAULT_VERSION = "26.03.29.1"


def dm(**kwargs: Any) -> dict[str, Any]:
    """Wrap a data-model dict with required metadata."""
    name = kwargs.pop("name", "M")
    version = kwargs.pop("version", DEFAULT_VERSION)
    author = kwargs.pop("author", "A")
    description = kwargs.pop("description", "Test data model.")
    body: dict[str, Any] = {
        "name": name,
        "version": version,
        "author": author,
        "description": description,
    }
    body.update(kwargs)
    return {"data-model": body}


def ent(
    name: str,
    primary_key: str,
    fields: list[dict[str, Any]],
    *,
    description: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": name,
        "description": description or f"Entity {name}.",
        "primary_key": primary_key,
        "fields": fields,
    }
    out.update(extra)
    return out


def fp(
    name: str,
    primitive: str,
    *,
    description: str | None = None,
    minDate: str | None = None,
    maxDate: str | None = None,
    foreignKeys: list[dict[str, Any]] | None = None,
    **field_top: Any,
) -> dict[str, Any]:
    """Entity field with type.case primitive (+ optional constraints under type)."""
    t: dict[str, Any] = {"primitive": primitive}
    if minDate is not None:
        t["minDate"] = minDate
    if maxDate is not None:
        t["maxDate"] = maxDate
    if foreignKeys is not None:
        t["foreignKeys"] = foreignKeys
    out: dict[str, Any] = {
        "name": name,
        "description": description or f"Field {name}.",
        "type": t,
    }
    out.update(field_top)
    return out


def f_array_entity(
    name: str,
    entity: str,
    *,
    description: str | None = None,
    **field_top: Any,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": name,
        "description": description or f"Field {name}.",
        "type": {"array": {"entity": entity}},
    }
    out.update(field_top)
    return out


def subf(name: str, primitive: str, *, description: str | None = None) -> dict[str, Any]:
    """Composite subcomponent (generic-field under type/composite)."""
    return {
        "name": name,
        "description": description or f"Subfield {name}.",
        "type": {"primitive": primitive},
    }


def f_composite(
    name: str,
    components: list[dict[str, Any]],
    *,
    description: str | None = None,
    **field_top: Any,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": name,
        "description": description or f"Field {name}.",
        "type": {"composite": components},
    }
    out.update(field_top)
    return out


def f_computed(
    name: str,
    primitive: str,
    operation: str,
    fields: list[dict[str, Any]],
    *,
    description: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description or f"Field {name}.",
        "type": {"primitive": primitive},
        "computed": {"operation": operation, "fields": fields},
    }
