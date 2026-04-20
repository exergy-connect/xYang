"""Unsupported YANG statements (rpc, deviation, …) are skipped with a warning."""

from __future__ import annotations

import logging

import pytest

from xyang import parse_yang_string


def test_module_skips_rpc_nested_input_output_warns(caplog: pytest.LogCaptureFixture) -> None:
    yang = """
module ex {
  yang-version 1.1;
  namespace "urn:ex";
  prefix ex;
  deviation /ex:foo { deviate not-supported; }
  extension ext { argument name; }
  rpc reset {
    input { leaf in-arg { type string; } }
    output { leaf out-arg { type string; } }
  }
  action "entity" {
    input { leaf x { type empty; } }
  }
  notification done { leaf msg { type string; } }
  input { leaf in-top { type empty; } }
  output { leaf out-top { type empty; } }
  leaf a { type string; }
}
"""
    with caplog.at_level(logging.WARNING, logger="xyang.parser.unsupported_skip"):
        mod = parse_yang_string(yang)
    warn_msgs = " ".join(r.getMessage() for r in caplog.records)
    # Nested input/output under rpc/action are skipped inside the outer block (no extra warnings).
    for kw in (
        "deviation",
        "rpc",
        "action",
        "notification",
        "input",
        "output",
    ):
        assert kw in warn_msgs.lower()
    leaf = mod.find_statement("a")
    assert leaf is not None
    assert getattr(leaf, "name", None) == "a"


def test_container_skips_rpc_warns(caplog: pytest.LogCaptureFixture) -> None:
    yang = """
module ex {
  yang-version 1.1;
  namespace "urn:ex";
  prefix ex;
  container c {
    rpc inner { }
    leaf x { type int8; }
  }
}
"""
    with caplog.at_level(logging.WARNING, logger="xyang.parser.unsupported_skip"):
        mod = parse_yang_string(yang)
    assert any("rpc" in r.getMessage().lower() for r in caplog.records)
    c = mod.find_statement("c")
    assert c is not None
    names = {s.name for s in c.statements}
    assert "x" in names
