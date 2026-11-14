"""Scope restrictions for the global typedef table (RFC 7950 §§5.4–5.5)."""

from __future__ import annotations

import re
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .ast import YangTypedefStmt, YangTypeStmt
    from .module import YangModule

from .errors import YangExportError, YangSemanticError


def in_scope(restriction: str | None, context: str) -> bool:
    return restriction is None or context == restriction or context.startswith(restriction + "/")


def scope_path(context: str, parent: object) -> str:
    kind = type(parent).__name__
    if kind not in {"YangContainerStmt", "YangListStmt", "YangGroupingStmt", "YangRpcStmt", "YangActionStmt", "YangInputStmt", "YangOutputStmt", "YangNotificationStmt"}:
        return context
    name = getattr(parent, "name", "")
    if kind == "YangGroupingStmt":
        name = "@grouping:" + name
    if kind == "YangInputStmt":
        name = "input"
    if kind == "YangOutputStmt":
        name = "output"
    return context + "/" + name.replace("~", "~0").replace("/", "~1")


def register_typedef(typedefs: dict[str, "YangTypedefStmt"], td: "YangTypedefStmt") -> str:
    from .types.registry import REGISTRY

    for previous in typedefs.values():
        if previous.name == td.name and (in_scope(previous.scope, td.scope or "") or in_scope(td.scope, previous.scope or "")):
            raise YangSemanticError(f"Duplicate typedef {td.name!r} in lexical scope")
    if td.name in REGISTRY:
        raise YangSemanticError(f"Duplicate typedef {td.name!r}: built-in type")
    key = (td.scope + "/" if td.scope else "") + td.name
    typedefs[key] = td
    return key


def validate_scope(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("/") or value.endswith("/") or "//" in value or re.search(r"~(?:[^01]|$)", value):
        raise ValueError("typedef scope must be a non-empty absolute context path")
    return value


# Export catalog only: references are resolved on demand, never bound to declarations.
EXPORT_TYPEDEFS: ContextVar[dict[str, tuple[YangTypedefStmt, YangModule]] | None] = ContextVar("export_typedefs", default=None)


def scoped_export_catalog(module: "YangModule") -> dict[str, tuple["YangTypedefStmt", "YangModule"]]:
    entries: dict[str, tuple["YangTypedefStmt", "YangModule"]] = {}
    visited: set[int] = set()

    def collect(current: "YangModule") -> None:
        if id(current) in visited:
            return
        visited.add(id(current))
        for key, td in current.typedefs.items():
            if td.scope is not None:
                exported = key if current is module else "@" + current.name + ":" + key
                if exported in entries:
                    raise YangExportError(f"Conflicting scoped typedef key {exported!r}")
                entries[exported] = (td, current)
        for imported in current.import_prefixes.values():
            collect(imported)

    collect(module)
    return entries


def scoped_type_schema(type_stmt: "YangTypeStmt", module: "YangModule") -> dict[str, Any] | None:
    from .module import resolve_typedef
    from .json.schema_keys import json_schema_defs_uri

    catalog = EXPORT_TYPEDEFS.get()
    if catalog is None:
        return None
    td, _ = resolve_typedef(type_stmt, module)
    if td is None or td.scope is None:
        return None
    if getattr(type_stmt, "range", None) or getattr(type_stmt, "length", None) or getattr(type_stmt, "patterns", None):
        raise YangExportError(f"cannot export restrictions on scoped typedef {td.name!r} in the native JSON form")
    for key, (candidate, _) in catalog.items():
        if candidate is td:
            return {"$ref": json_schema_defs_uri(key), "x-yang": {"type-context": type_stmt.context or ""}}
    raise YangExportError(f"Scoped typedef {td.name!r} is absent from the export catalog")
