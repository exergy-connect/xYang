"""
YANG identifier-ref: an identifier with an optional module prefix
(RFC 7950 prefix:identifier). Built once at parse time — transformers
must not re-split qname strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class YangIdentifierRef:
    """Local identifier with optional import / module prefix."""

    name: str
    prefix: Optional[str] = None


def format_identifier_ref(ref: YangIdentifierRef) -> str:
    return f"{ref.prefix}:{ref.name}" if ref.prefix else ref.name


def identifier_ref(name: str, prefix: Optional[str] = None) -> YangIdentifierRef:
    return YangIdentifierRef(name=name, prefix=prefix) if prefix else YangIdentifierRef(name=name)


def parse_identifier_ref_atom(atom: str) -> YangIdentifierRef:
    """Convert one opaque atom (if-feature token, JSON Schema base string, RFC 7951 value)."""
    idx = atom.find(":")
    if idx <= 0 or idx >= len(atom) - 1:
        return YangIdentifierRef(name=atom)
    return YangIdentifierRef(prefix=atom[:idx], name=atom[idx + 1 :])


def parse_absolute_schema_path(path: str) -> list[YangIdentifierRef]:
    """Parse absolute schema-node path (``/prefix:a/prefix:b``) into segment refs."""
    raw = path.strip().strip('"').strip("'")
    if not raw.startswith("/"):
        raise ValueError(f"Schema path must be absolute, got {path!r}")
    parts = [p.strip() for p in raw[1:].split("/") if p.strip()]
    if not parts:
        raise ValueError(f"Empty schema path: {path!r}")
    out: list[YangIdentifierRef] = []
    for seg in parts:
        ref = parse_identifier_ref_atom(seg)
        if not ref.prefix:
            raise ValueError(
                f"Invalid schema path segment {seg!r}: expected 'prefix:identifier'"
            )
        out.append(ref)
    return out


def coerce_identifier_ref(value: Any) -> Optional[YangIdentifierRef]:
    """Normalize JSON/legacy string-or-object bases into identifier-refs."""
    if isinstance(value, str) and value:
        return parse_identifier_ref_atom(value)
    if isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str) and name:
            prefix = value.get("prefix")
            if isinstance(prefix, str) and prefix:
                return YangIdentifierRef(prefix=prefix, name=name)
            return YangIdentifierRef(name=name)
    if isinstance(value, YangIdentifierRef):
        return value
    return None
