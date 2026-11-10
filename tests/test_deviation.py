"""``deviate not-supported`` removes the target, including across an import."""

from __future__ import annotations

from pathlib import Path

import pytest

from xyang import YangValidator
from xyang.errors import YangSemanticError
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


def test_missing_not_supported_target_is_schema_error(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "m.yang",
        """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  container top { leaf b { type uint8; } }
  deviation "/m:top/m:a" { deviate not-supported; }
}
""",
    )
    with pytest.raises(YangSemanticError):
        YangParser().parse_file(tmp_path / "m.yang")
