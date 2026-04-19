"""
RFC 7951 JSON encoding: mapping instance member names to schema.

A namespace-qualified object member is ``module-name:node`` where ``module-name``
is the YANG module name and ``node`` is a top-level data node in that module.
"""

from __future__ import annotations

from typing import Mapping, Optional, Tuple

from ..ast import YangStatement
from ..module import YangModule


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


__all__ = ["resolve_qualified_top_level"]
