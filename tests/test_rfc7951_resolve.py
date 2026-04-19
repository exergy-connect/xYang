"""RFC 7951 JSON member → top-level schema resolution (core)."""

from __future__ import annotations

from xyang import parse_yang_string
from xyang.encoding import resolve_qualified_top_level


def test_resolve_qualified_top_level_finds_statement():
    a = parse_yang_string(
        """
module mod-a {
  yang-version 1.1;
  namespace "urn:a";
  prefix a;
  container root { leaf x { type string; } }
}
"""
    )
    b = parse_yang_string(
        """
module mod-b {
  yang-version 1.1;
  namespace "urn:b";
  prefix b;
  leaf y { type int8; }
}
"""
    )
    modules = {a.name: a, b.name: b}
    stmt, mod = resolve_qualified_top_level("mod-a:root", modules)
    assert mod is a
    assert stmt is not None and stmt.name == "root"

    stmt2, mod2 = resolve_qualified_top_level("mod-b:y", modules)
    assert mod2 is b
    assert stmt2 is not None and stmt2.name == "y"


def test_resolve_qualified_top_level_unknown_module():
    m = parse_yang_string(
        'module lone { yang-version 1.1; namespace "urn:l"; prefix l; leaf z { type string; } }'
    )
    stmt, mod = resolve_qualified_top_level("unknown:z", {m.name: m})
    assert stmt is None and mod is None


def test_resolve_unqualified_returns_none():
    m = parse_yang_string(
        'module lone { yang-version 1.1; namespace "urn:l"; prefix l; leaf z { type string; } }'
    )
    stmt, mod = resolve_qualified_top_level("z", {m.name: m})
    assert stmt is None and mod is None
