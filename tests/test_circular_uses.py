"""Semantic error when ``uses`` forms a cyclic grouping chain (compile-time expansion)."""

from __future__ import annotations

import pytest

from xyang.errors import YangCircularUsesError
from xyang.parser.yang_parser import YangParser


def test_self_referential_grouping_raises():
    """``uses`` of the same grouping inside that grouping is a cycle."""
    yang = """
module c {
  yang-version 1.1;
  namespace "urn:test:c";
  prefix "c";
  grouping a {
    uses a;
    leaf x { type string; }
  }
  container r { uses a; }
}
"""
    with pytest.raises(YangCircularUsesError) as exc_info:
        YangParser().parse_string(yang)
    err = exc_info.value
    assert err.repeated == "a"
    assert "a" in str(err)


def test_two_grouping_cycle_raises():
    """A -> B -> A is detected when expanding."""
    yang = """
module c {
  yang-version 1.1;
  namespace "urn:test:c";
  prefix "c";
  grouping a { uses b; leaf la { type string; } }
  grouping b { uses a; leaf lb { type string; } }
  container r { uses a; }
}
"""
    with pytest.raises(YangCircularUsesError) as exc_info:
        YangParser().parse_string(yang)
    assert exc_info.value.repeated in ("a", "b")
    chain = exc_info.value.prefix_chain
    assert len(chain) >= 1


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
