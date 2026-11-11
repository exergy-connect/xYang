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
  deviation "/ex:foo" {
    deviate add {
      leaf extra { type string; }
    }
  }
  extension ext { argument name; }
  rpc reset {
    input { leaf in-arg { type string; } }
    output { leaf out-arg { type string; } }
  }
  notification done { leaf msg { type string; } }
  leaf a { type string; }
}
"""
    with caplog.at_level(logging.WARNING, logger="xyang.parser.unsupported_skip"):
        mod = parse_yang_string(yang)
    warn_msgs = " ".join(r.getMessage() for r in caplog.records)
    # ``rpc`` and nested ``input``/``output`` are parsed.
    # ``deviate add`` is skipped with a warning that names the kind and path.
    assert "ignoring unsupported 'deviate add' for /ex:foo" in warn_msgs.lower()
    assert "rpc" not in warn_msgs.lower()
    assert "input" not in warn_msgs.lower()
    assert "output" not in warn_msgs.lower()
    reset = mod.find_statement("reset")
    assert reset is not None
    assert getattr(reset, "name", None) == "reset"
    done = mod.find_statement("done")
    assert done is not None
    assert getattr(done, "name", None) == "done"
    leaf = mod.find_statement("a")
    assert leaf is not None
    assert getattr(leaf, "name", None) == "a"


def test_action_is_parsed_under_a_container_and_rejected_at_module_level() -> None:
    from xyang.ast import YangActionStmt

    mod = parse_yang_string(
        'module ex { yang-version 1.1; namespace "urn:ex"; prefix ex;'
        " container c { action go { input { leaf x { type empty; } } } } }"
    )
    (action,) = [s for s in mod.find_statement("c").statements if isinstance(s, YangActionStmt)]
    assert action.name == "go"
    with pytest.raises(Exception, match="unknown statement in module body: 'action'"):
        parse_yang_string('module ex { yang-version 1.1; namespace "urn:ex"; prefix ex; action go { } }')


@pytest.mark.parametrize("keyword", ["input", "output"])
def test_module_rejects_top_level_input_output(keyword: str) -> None:
    yang = f"""
module ex {{
  yang-version 1.1;
  namespace "urn:ex";
  prefix ex;
  {keyword} {{ leaf x {{ type empty; }} }}
}}
"""
    with pytest.raises(Exception, match=rf"{keyword}.*rpc.*action"):
        parse_yang_string(yang)


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
