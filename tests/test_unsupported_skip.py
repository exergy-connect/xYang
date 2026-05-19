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
    # ``rpc`` and nested ``input``/``output`` are parsed; ``action`` and top-level ``input``/``output`` warn.
    for kw in (
        "deviation",
        "action",
        "input",
        "output",
    ):
        assert kw in warn_msgs.lower()
    assert "rpc" not in warn_msgs.lower()
    reset = mod.find_statement("reset")
    assert reset is not None
    assert getattr(reset, "name", None) == "reset"
    done = mod.find_statement("done")
    assert done is not None
    assert getattr(done, "name", None) == "done"
    leaf = mod.find_statement("a")
    assert leaf is not None
    assert getattr(leaf, "name", None) == "a"


def test_container_rejects_rpc() -> None:
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
    with pytest.raises(Exception, match="rpc"):
        parse_yang_string(yang)
