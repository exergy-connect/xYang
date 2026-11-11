"""Semantic error when ``uses`` forms a cyclic grouping chain (compile-time expansion).

Self-referential and mutual cycles are shared schema_error cases under
``tests/cases/reuse/``. This file keeps the expand_uses=False API contract.
"""

from __future__ import annotations

from xyang.parser.yang_parser import YangParser


def test_expand_uses_false_skips_expansion_no_error():
    """With expansion disabled, cyclic text parses without semantic expansion pass."""
    yang = """
module c {
  yang-version 1.1;
  namespace "urn:test:c";
  prefix "c";
  grouping a { uses a; leaf x { type string; } }
  container r { uses a; }
}
"""
    mod = YangParser(expand_uses=False).parse_string(yang)
    assert mod.name == "c"
