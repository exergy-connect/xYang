"""``config`` substatement is consumed with a warning, not stored on AST."""

from __future__ import annotations

import logging

from xyang import parse_yang_string


def test_config_false_parses_with_warning(caplog) -> None:
    caplog.set_level(logging.WARNING)
    mod = parse_yang_string(
        """module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  container state-tree {
    config false;
    leaf x { type string; }
  }
}"""
    )
    assert mod.find_statement("state-tree") is not None
    assert any("config" in r.message for r in caplog.records)
