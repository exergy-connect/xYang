"""
Optional extensions to xYang (reference implementations, I-D experiments).
"""

from .capabilities import (
    ExtensionIdentity,
    apply_extension_invocations,
    get_extension_apply_callback,
    register_extension_apply_callback,
)

_BUILTINS_LOADED = False


def ensure_builtin_extensions_loaded() -> None:
    """Load built-in extension plugins exactly once."""
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    from .rfc8791 import register_capabilities as _register_rfc8791_capabilities

    _register_rfc8791_capabilities()
    _BUILTINS_LOADED = True


__all__ = [
    "ExtensionIdentity",
    "apply_extension_invocations",
    "ensure_builtin_extensions_loaded",
    "get_extension_apply_callback",
    "register_extension_apply_callback",
]
