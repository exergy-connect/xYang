"""
RFC 7951 JSON encoding: mapping instance member names to schema.

A namespace-qualified object member is ``module-name:node`` where ``module-name``
is the YANG module name and ``node`` is a top-level data node in that module.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

from ..ast import YangStatement
from ..module import YangModule

_STRUCTURE_INDEX_KEY = "ietf-yang-structure-ext:structure-index"


def resolve_structure_instance(
    data: Dict[str, Any], module: YangModule
) -> Optional[Tuple[YangStatement, Dict[str, Any]]]:
    """
    If *data* is a single RFC 7951 ``module-name:structure`` object for a registered
    RFC 8791 structure in *module*, return ``(structure_schema, inner_object)``.
    """
    if not isinstance(data, dict) or len(data) != 1:
        return None
    json_key, inner = next(iter(data.items()))
    if not isinstance(json_key, str) or ":" not in json_key:
        return None
    mod_name, _, struct_name = json_key.partition(":")
    if mod_name != module.name or not struct_name:
        return None
    idx = module.extension_runtime.get(_STRUCTURE_INDEX_KEY) or {}
    schema = idx.get(struct_name)
    if schema is None:
        return None
    if not isinstance(inner, dict):
        return None
    return schema, inner


def defining_module_name(stmt: YangStatement, parent_module_name: str) -> str:
    """YANG module that defines *stmt* for RFC 7951 encoding under *parent_module_name*."""
    explicit = getattr(stmt, "defining_module", None)
    if explicit:
        return explicit
    return parent_module_name


def instance_member_keys(stmt: YangStatement, parent_module_name: str) -> set[str]:
    """
    JSON object keys for *stmt* under a parent data node in *parent_module_name*.

    Same-module children use the local identifier; nodes from another module use
    ``module-name:identifier`` (RFC 7951).
    """
    local = stmt.name
    if not local:
        return set()
    def_mod = defining_module_name(stmt, parent_module_name)
    if def_mod == parent_module_name:
        return {local}
    return {f"{def_mod}:{local}"}


def instance_member_present(data: Mapping[str, Any], stmt: YangStatement, parent_module_name: str) -> bool:
    return bool(instance_member_keys(stmt, parent_module_name) & data.keys())


def instance_member_lookup(
    data: Mapping[str, Any], stmt: YangStatement, parent_module_name: str
) -> tuple[Any, Optional[str]]:
    """
    Return ``(value, json_key)`` for *stmt* in *data*.

  ``json_key`` is the key found in *data*, or ``None`` when the value comes from a
    schema default and is not present in *data*.
    """
    for key in instance_member_keys(stmt, parent_module_name):
        if key in data:
            return data[key], key
    return None, None


def resolve_qualified_top_level(
    member_key: str, modules: Mapping[str, YangModule]
) -> Tuple[Optional[YangStatement], Optional[YangModule]]:
    """
    Resolve an RFC 7951 ``module-name:identifier`` member at the root of a JSON object
    (e.g. under ``anydata``) to a top-level schema statement and its defining module.

    Returns ``(None, None)`` if the key is not qualified, the module is unknown, or
    the identifier is not a top-level data node in that module.
    """
    if ":" not in member_key:
        return None, None
    mod_name, _, ident = member_key.partition(":")
    mod = modules.get(mod_name)
    if mod is None:
        return None, None
    stmt = mod.find_statement(ident)
    return stmt, mod


__all__ = [
    "defining_module_name",
    "instance_member_keys",
    "instance_member_lookup",
    "instance_member_present",
    "resolve_qualified_top_level",
    "resolve_structure_instance",
]
