"""YANG instance encoding helpers (e.g. JSON per RFC 7951)."""

from .rfc7951 import resolve_qualified_top_level

__all__ = ["resolve_qualified_top_level"]
