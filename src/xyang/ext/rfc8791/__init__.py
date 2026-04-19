"""RFC 8791 plugin callbacks."""

from __future__ import annotations

from ...ast import YangExtensionInvocationStmt
from ..capabilities import ExtensionIdentity, register_extension_apply_callback
from .structure_expand import apply_augment_structure_invocation

_STRUCTURE_INDEX_KEY = "ietf-yang-structure-ext:structure-index"


def register_capabilities() -> None:
    """Register RFC 8791 extension-apply callbacks."""
    register_extension_apply_callback(
        ExtensionIdentity(
            module_name="ietf-yang-structure-ext",
            extension_name="structure",
        ),
        _apply_structure,
    )
    register_extension_apply_callback(
        ExtensionIdentity(
            module_name="ietf-yang-structure-ext",
            extension_name="augment-structure",
        ),
        _apply_augment_structure,
    )


def _apply_structure(
    invocation: YangExtensionInvocationStmt,
    context_module,
):
    # ``structure`` is represented by the invocation node itself; register it
    # for fast augment-structure top-level target lookup.
    name = (invocation.argument or "").strip()
    if name:
        idx = context_module.extension_runtime.setdefault(_STRUCTURE_INDEX_KEY, {})
        idx[name] = invocation
    return invocation


def _apply_augment_structure(
    invocation: YangExtensionInvocationStmt,
    context_module,
):
    return apply_augment_structure_invocation(invocation, context_module=context_module)


__all__ = ["register_capabilities"]
