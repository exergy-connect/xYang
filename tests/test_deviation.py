"""``deviate not-supported`` removes the target, including across an import.

Same-module not-supported validation and missing-target schema errors live in
``tests/cases/modules/``.
"""

from __future__ import annotations

from pathlib import Path

from xyang import YangValidator
from xyang.parser import YangParser


def _write(dir_path: Path, name: str, text: str) -> Path:
    path = dir_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_cross_module_not_supported_removes_imported_leaf(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "base.yang",
        """
module base {
  yang-version 1.1;
  namespace "urn:b";
  prefix b;
  container top {
    leaf a { type string; }
    leaf b { type uint8; }
  }
}
""",
    )
    _write(
        tmp_path,
        "dev.yang",
        """
module dev {
  yang-version 1.1;
  namespace "urn:dev";
  prefix d;
  import base { prefix b; }
  deviation "/b:top/b:a" {
    description "a is not used";
    reference "RFC 7950";
    deviate not-supported;
  }
}
""",
    )
    parser = YangParser()
    dev = parser.parse_file(tmp_path / "dev.yang")
    base = dev.import_prefixes["b"]
    ok, errors, _warnings = YangValidator(base).validate({"top": {"a": "x"}})
    assert not ok
    assert any("Unknown field 'a'" in err for err in errors)
    ok_sibling, sibling_errors, _warnings = YangValidator(base).validate({"top": {"b": 1}})
    assert ok_sibling, sibling_errors


def test_target_parsed_alone_keeps_deviated_node(tmp_path: Path) -> None:
    """A deviation must not edit the shared parser cache. B alone still has the node."""
    _write(
        tmp_path,
        "base.yang",
        """
module base {
  yang-version 1.1;
  namespace "urn:b";
  prefix b;
  container top {
    leaf a { type string; }
    leaf b { type uint8; }
  }
}
""",
    )
    _write(
        tmp_path,
        "dev.yang",
        """
module dev {
  yang-version 1.1;
  namespace "urn:dev";
  prefix d;
  import base { prefix b; }
  deviation "/b:top/b:a" { deviate not-supported; }
}
""",
    )
    parser = YangParser()
    dev = parser.parse_file(tmp_path / "dev.yang")
    deviated = dev.import_prefixes["b"]
    removed, removed_errors, _warnings = YangValidator(deviated).validate({"top": {"a": "x"}})
    assert not removed
    assert any("Unknown field 'a'" in err for err in removed_errors)
    alone = parser.parse_file(tmp_path / "base.yang")
    ok, errors, _warnings = YangValidator(alone).validate({"top": {"a": "x"}})
    assert ok, errors
    assert alone is not deviated
