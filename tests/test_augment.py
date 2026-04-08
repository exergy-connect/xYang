"""Tests for RFC 7950 ``augment`` (schema merge into target node)."""

from __future__ import annotations

from pathlib import Path

import pytest

from xyang import YangValidator
from xyang.ast import YangAugmentStmt, YangLeafStmt
from xyang.errors import YangSyntaxError
from xyang.parser import YangParser
from xyang.validator.document_validator import DocumentValidator


def test_augment_same_module_merges_into_container(tmp_path: Path) -> None:
    path = tmp_path / "m.yang"
    path.write_text(
        """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  container a {
    leaf x { type string; }
  }
  augment "/m:a" {
    leaf y { type int32; }
  }
}
""",
        encoding="utf-8",
    )
    mod = YangParser(expand_uses=True).parse_file(path)
    assert not any(isinstance(s, YangAugmentStmt) for s in mod.statements)
    a = mod.find_statement("a")
    assert a is not None
    assert a.find_statement("x") is not None
    y = a.find_statement("y")
    assert isinstance(y, YangLeafStmt)
    v = YangValidator(mod)
    ok, errors, _ = v.validate({"a": {"x": "hi", "y": 42}})
    assert ok, errors


def test_augment_cross_file_import_merges_into_imported_container(tmp_path: Path) -> None:
    (tmp_path / "lib.yang").write_text(
        """
module lib {
  yang-version 1.1;
  namespace "urn:lib";
  prefix l;
  container root {
    leaf existing { type string; }
  }
}
""",
        encoding="utf-8",
    )
    (tmp_path / "main.yang").write_text(
        """
module main {
  yang-version 1.1;
  namespace "urn:main";
  prefix mn;
  import lib { prefix imp; }
  augment "/imp:root" {
    leaf extra { type string; }
  }
}
""",
        encoding="utf-8",
    )
    mod = YangParser(expand_uses=True).parse_file(tmp_path / "main.yang")
    assert not any(isinstance(s, YangAugmentStmt) for s in mod.statements)
    lib = mod.import_prefixes["imp"]
    root = lib.find_statement("root")
    assert root is not None
    assert root.find_statement("existing") is not None
    assert isinstance(root.find_statement("extra"), YangLeafStmt)

    v = YangValidator(lib)
    ok, errors, _ = v.validate({"root": {"existing": "a", "extra": "b"}})
    assert ok, errors


def test_augment_if_feature_prepended_on_merged_leaves(tmp_path: Path) -> None:
    path = tmp_path / "m.yang"
    path.write_text(
        """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  feature f;
  container a { leaf x { type string; } }
  augment "/m:a" {
    if-feature "f";
    leaf z { type string; }
  }
}
""",
        encoding="utf-8",
    )
    mod = YangParser(expand_uses=True).parse_file(path)
    a = mod.find_statement("a")
    assert a is not None
    z = a.find_statement("z")
    assert isinstance(z, YangLeafStmt)
    assert z.if_features == ["f"]
    v = DocumentValidator(mod, enabled_features_by_module={"m": frozenset()})
    errors = v.validate({"a": {"x": "ok", "z": "bad"}})
    assert errors and any("if-feature" in e.message for e in errors)


def test_augment_invalid_path_not_absolute_errors(tmp_path: Path) -> None:
    path = tmp_path / "m.yang"
    path.write_text(
        """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  container a { }
  augment "m:a" { leaf y { type string; } }
}
""",
        encoding="utf-8",
    )
    with pytest.raises(YangSyntaxError, match="absolute"):
        YangParser(expand_uses=True).parse_file(path)


def test_augment_unknown_prefix_errors(tmp_path: Path) -> None:
    path = tmp_path / "m.yang"
    path.write_text(
        """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  augment "/xx:noop" { leaf y { type string; } }
}
""",
        encoding="utf-8",
    )
    with pytest.raises(YangSyntaxError, match="unknown prefix"):
        YangParser(expand_uses=True).parse_file(path)
