"""``config`` substatement is stored on the AST when present."""

from __future__ import annotations

import logging

from xyang import parse_yang_string
from xyang.ast import YangContainerStmt, YangLeafStmt
from xyang.json.generator import generate_json_schema
from xyang.json.schema_keys import XYangKey
def test_config_false_on_container_stored() -> None:
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
    c = mod.find_statement("state-tree")
    assert isinstance(c, YangContainerStmt)
    assert c.config is False


def test_config_false_on_leaf_stored() -> None:
    mod = parse_yang_string(
        """module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  leaf ro {
    type string;
    config false;
  }
}"""
    )
    leaf = mod.find_statement("ro")
    assert isinstance(leaf, YangLeafStmt)
    assert leaf.config is False


def test_config_no_warning(caplog) -> None:
    caplog.set_level(logging.WARNING)
    parse_yang_string(
        """module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  leaf x { type string; config false; }
}"""
    )
    assert not any("config" in r.message for r in caplog.records)


def test_refine_config_applied() -> None:
    mod = parse_yang_string(
        """module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  grouping g {
    leaf x { type string; }
  }
  container c {
    uses g {
      refine x { config false; }
    }
  }
}"""
    )
    c = mod.find_statement("c")
    assert c is not None
    leaf = next(s for s in c.statements if isinstance(s, YangLeafStmt) and s.name == "x")
    assert leaf.config is False


def test_config_emitted_in_json_schema() -> None:
    mod = parse_yang_string(
        """module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  leaf ro { type string; config false; }
}"""
    )
    schema = generate_json_schema(mod)
    assert schema["properties"]["ro"]["x-yang"][XYangKey.CONFIG] is False
