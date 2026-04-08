"""Tests for ``if-feature``: parsing (RFC 7950 §7.18.2), evaluation (§7.20.2), and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from xyang.ast import (
    YangCaseStmt,
    YangChoiceStmt,
    YangContainerStmt,
    YangLeafListStmt,
    YangLeafStmt,
    YangListStmt,
)
from xyang.module import YangModule
from xyang.parser import YangParser
from xyang.validator.document_validator import DocumentValidator
from xyang.validator.if_feature_eval import (
    build_enabled_features_map,
    evaluate_if_feature_expression,
    reachable_modules,
    stmt_if_features_satisfied,
)


@pytest.fixture
def yang_source(tmp_path: Path) -> Path:
    return tmp_path / "test.yang"


def _parse(yang: str, source_path: Path) -> YangModule:
    mod = YangParser().parse_string(
        yang, filename=str(source_path), source_path=source_path
    )
    assert isinstance(mod, YangModule)
    return mod


# -- parsing --


def test_if_feature_on_leaf_stores_expression(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:test:if-feature";
  prefix x;

  feature f;

  leaf a {
    if-feature "f";
    type string;
  }
}
"""
    mod = _parse(yang, yang_source)
    leaf = mod.find_statement("a")
    assert isinstance(leaf, YangLeafStmt)
    assert leaf.if_features == ["f"]


def test_if_feature_braced_with_description(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:test:if-feature";
  prefix x;

  feature bar;

  container c {
    if-feature "bar" {
      description "needs bar";
    }
    leaf x {
      type string;
    }
  }
}
"""
    mod = _parse(yang, yang_source)
    c = mod.find_statement("c")
    assert isinstance(c, YangContainerStmt)
    assert c.if_features == ["bar"]


def test_if_feature_braced_with_reference(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:test:if-feature";
  prefix x;

  feature baz;

  leaf L {
    if-feature "baz" {
      description "d";
      reference "RFC 7950";
    }
    type string;
  }
}
"""
    mod = _parse(yang, yang_source)
    leaf = mod.find_statement("L")
    assert isinstance(leaf, YangLeafStmt)
    assert leaf.if_features == ["baz"]


def test_multiple_if_feature_and_on_same_node(yang_source: Path) -> None:
    """Several ``if-feature`` lines apply as a conjunction (stored in order)."""
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:test:if-feature";
  prefix x;

  feature p;
  feature q;

  leaf z {
    if-feature "p";
    if-feature "q";
    type uint8;
  }
}
"""
    mod = _parse(yang, yang_source)
    leaf = mod.find_statement("z")
    assert isinstance(leaf, YangLeafStmt)
    assert leaf.if_features == ["p", "q"]


def test_if_feature_on_leaf_list(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:test:if-feature";
  prefix x;

  feature fl;

  leaf-list tags {
    if-feature "fl";
    type string;
  }
}
"""
    mod = _parse(yang, yang_source)
    ll = mod.find_statement("tags")
    assert isinstance(ll, YangLeafListStmt)
    assert ll.if_features == ["fl"]


def test_if_feature_on_list(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:test:if-feature";
  prefix x;

  feature lst;

  list items {
    if-feature "lst";
    key "id";
    leaf id { type string; }
    leaf val { type uint8; }
  }
}
"""
    mod = _parse(yang, yang_source)
    lst = mod.find_statement("items")
    assert isinstance(lst, YangListStmt)
    assert lst.if_features == ["lst"]


def test_if_feature_prefixed_feature_reference(tmp_path: Path) -> None:
    """``if-feature`` may name a feature in an imported module via ``prefix:feature``."""
    (tmp_path / "lib.yang").write_text(
        """
module lib {
  yang-version 1.1;
  namespace "urn:test:if-feature-lib";
  prefix l;
  feature remote;
}
""",
        encoding="utf-8",
    )
    (tmp_path / "main.yang").write_text(
        """
module main {
  yang-version 1.1;
  namespace "urn:test:if-feature-main";
  prefix m;
  import lib { prefix imp; }
  leaf x {
    if-feature "imp:remote";
    type string;
  }
}
""",
        encoding="utf-8",
    )
    mod = YangParser(expand_uses=False).parse_file(tmp_path / "main.yang")
    assert mod.import_prefixes["imp"].name == "lib"
    assert "remote" in mod.import_prefixes["imp"].features
    leaf = mod.find_statement("x")
    assert isinstance(leaf, YangLeafStmt)
    assert leaf.if_features == ["imp:remote"]


# -- expression evaluation --


def test_eval_boolean_ops_and_precedence(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature a;
  feature b;
  feature c;
}
"""
    mod = _parse(yang, yang_source)
    en_all = build_enabled_features_map(mod, None)
    en_none = build_enabled_features_map(mod, {"m": frozenset()})
    en_a = build_enabled_features_map(mod, {"m": frozenset({"a"})})
    en_ab = build_enabled_features_map(mod, {"m": frozenset({"a", "b"})})

    assert evaluate_if_feature_expression("a", mod, en_all) is True
    assert evaluate_if_feature_expression("a", mod, en_none) is False
    assert evaluate_if_feature_expression("not a", mod, en_all) is False
    assert evaluate_if_feature_expression("not a", mod, en_none) is True
    assert evaluate_if_feature_expression("a or b", mod, en_a) is True
    assert evaluate_if_feature_expression("a and b", mod, en_a) is False
    assert evaluate_if_feature_expression("a and b", mod, en_ab) is True
    # f or g and h  =>  f or (g and h)
    assert evaluate_if_feature_expression("a or b and c", mod, en_a) is True
    assert evaluate_if_feature_expression("(a or b) and c", mod, en_a) is False


def test_eval_parens_and_whitespace(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature p;
  feature q;
}
"""
    mod = _parse(yang, yang_source)
    en_p = build_enabled_features_map(mod, {"m": frozenset({"p"})})
    assert evaluate_if_feature_expression("  ( p or q ) ", mod, en_p) is True


def test_eval_own_module_prefix(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix mx;
  feature f;
}
"""
    mod = _parse(yang, yang_source)
    en = build_enabled_features_map(mod, None)
    assert evaluate_if_feature_expression("f", mod, en) is True
    assert evaluate_if_feature_expression("mx:f", mod, en) is True


def test_eval_unknown_prefix_and_feature(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature f;
}
"""
    mod = _parse(yang, yang_source)
    en = build_enabled_features_map(mod, None)
    assert evaluate_if_feature_expression("nope:f", mod, en) is False
    assert evaluate_if_feature_expression("x:missing", mod, en) is False


def test_eval_malformed_expression_is_false(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature f;
}
"""
    mod = _parse(yang, yang_source)
    en = build_enabled_features_map(mod, None)
    assert evaluate_if_feature_expression("", mod, en) is False
    assert evaluate_if_feature_expression("f f", mod, en) is False
    assert evaluate_if_feature_expression("not", mod, en) is False


def test_stmt_if_features_satisfied_and_multiple_substatements(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature p;
  feature q;
}
"""
    mod = _parse(yang, yang_source)
    en_both = build_enabled_features_map(mod, {"m": frozenset({"p", "q"})})
    en_p = build_enabled_features_map(mod, {"m": frozenset({"p"})})
    assert stmt_if_features_satisfied([], mod, en_both) is True
    assert stmt_if_features_satisfied(["p", "q"], mod, en_both) is True
    assert stmt_if_features_satisfied(["p", "q"], mod, en_p) is False


def test_eval_prefixed_or_expression_two_modules(tmp_path: Path) -> None:
    (tmp_path / "lib.yang").write_text(
        """
module lib {
  yang-version 1.1;
  namespace "urn:lib";
  prefix l;
  feature fea1;
  feature fea2;
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
  import lib { prefix ex; }
  leaf x {
    if-feature "ex:fea1 or ex:fea2";
    type string;
  }
}
""",
        encoding="utf-8",
    )
    mod = YangParser(expand_uses=False).parse_file(tmp_path / "main.yang")
    leaf = mod.find_statement("x")
    assert isinstance(leaf, YangLeafStmt)
    assert leaf.if_features == ["ex:fea1 or ex:fea2"]
    en1 = build_enabled_features_map(mod, {"lib": frozenset({"fea1"}), "main": frozenset()})
    assert evaluate_if_feature_expression(leaf.if_features[0], mod, en1) is True
    en2 = build_enabled_features_map(mod, {"lib": frozenset({"fea2"}), "main": frozenset()})
    assert evaluate_if_feature_expression(leaf.if_features[0], mod, en2) is True
    en_none = build_enabled_features_map(mod, {"lib": frozenset(), "main": frozenset()})
    assert evaluate_if_feature_expression(leaf.if_features[0], mod, en_none) is False


def test_reachable_modules_includes_transitive_imports(tmp_path: Path) -> None:
    (tmp_path / "a.yang").write_text(
        """
module a {
  yang-version 1.1;
  namespace "urn:a";
  prefix a;
}
""",
        encoding="utf-8",
    )
    (tmp_path / "b.yang").write_text(
        """
module b {
  yang-version 1.1;
  namespace "urn:b";
  prefix b;
  import a { prefix pa; }
}
""",
        encoding="utf-8",
    )
    (tmp_path / "c.yang").write_text(
        """
module c {
  yang-version 1.1;
  namespace "urn:c";
  prefix c;
  import b { prefix pb; }
}
""",
        encoding="utf-8",
    )
    root = YangParser(expand_uses=False).parse_file(tmp_path / "c.yang")
    names = {m.name for m in reachable_modules(root)}
    assert names == {"c", "b", "a"}


def test_build_enabled_features_map_unlisted_module_gets_all_declared(tmp_path: Path) -> None:
    (tmp_path / "lib.yang").write_text(
        """
module lib {
  yang-version 1.1;
  namespace "urn:lib";
  prefix l;
  feature x;
}
""",
        encoding="utf-8",
    )
    (tmp_path / "main.yang").write_text(
        """
module main {
  yang-version 1.1;
  namespace "urn:main";
  prefix m;
  import lib { prefix imp; }
}
""",
        encoding="utf-8",
    )
    mod = YangParser(expand_uses=False).parse_file(tmp_path / "main.yang")
    # Only constrain main; lib should still expose all its declared features as enabled
    m = build_enabled_features_map(mod, {"main": frozenset()})
    assert m["lib"] == frozenset({"x"})
    assert m["main"] == frozenset()


# -- document validation --


def test_validate_inactive_leaf_present_is_error(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature f;
  container root {
    leaf a {
      if-feature "f";
      type string;
    }
  }
}
"""
    mod = _parse(yang, yang_source)
    v = DocumentValidator(
        mod, enabled_features_by_module={"m": frozenset()}
    )
    errors = v.validate({"root": {"a": "hi"}})
    assert len(errors) == 1
    assert "if-feature" in errors[0].message


def test_validate_inactive_leaf_absent_ok(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature f;
  container root {
    leaf a {
      if-feature "f";
      type string;
    }
  }
}
"""
    mod = _parse(yang, yang_source)
    v = DocumentValidator(
        mod, enabled_features_by_module={"m": frozenset()}
    )
    assert v.validate({"root": {}}) == []


def test_validate_feature_enabled_allows_data(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature f;
  container root {
    leaf a {
      if-feature "f";
      type string;
    }
  }
}
"""
    mod = _parse(yang, yang_source)
    v = DocumentValidator(
        mod, enabled_features_by_module={"m": frozenset({"f"})}
    )
    assert v.validate({"root": {"a": "ok"}}) == []


def test_validate_inactive_list_present_is_error(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature lst;
  container root {
    list items {
      if-feature "lst";
      key "id";
      leaf id { type string; }
    }
  }
}
"""
    mod = _parse(yang, yang_source)
    v = DocumentValidator(
        mod, enabled_features_by_module={"m": frozenset()}
    )
    errors = v.validate({"root": {"items": [{"id": "1"}]}})
    assert len(errors) >= 1
    assert any("if-feature" in e.message for e in errors)


# -- RFC 7950 §7.20.2: additional parent statements (choice, case, uses, refine, feature) --


def test_if_feature_on_choice_and_case(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature cf;
  feature bf;
  container root {
    choice ch {
      if-feature "cf";
      case ca {
        if-feature "bf";
        leaf L { type string; }
      }
    }
  }
}
"""
    mod = _parse(yang, yang_source)
    root = mod.find_statement("root")
    assert root is not None
    ch = next(s for s in root.statements if s.name == "ch")
    assert isinstance(ch, YangChoiceStmt)
    assert ch.if_features == ["cf"]
    ca = ch.cases[0]
    assert isinstance(ca, YangCaseStmt)
    assert ca.if_features == ["bf"]


def test_if_feature_on_uses_merged_into_grouping_leaves(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature u;
  grouping g {
    leaf L { type string; }
  }
  container root {
    uses g {
      if-feature "u";
    }
  }
}
"""
    mod = YangParser(expand_uses=True).parse_string(
        yang, filename=str(yang_source), source_path=yang_source
    )
    root = mod.find_statement("root")
    assert root is not None
    leaf_l = root.find_statement("L")
    assert isinstance(leaf_l, YangLeafStmt)
    assert leaf_l.if_features == ["u"]


def test_if_feature_on_refine_merged_into_target_leaf(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature rf;
  grouping g {
    leaf x { type string; }
  }
  container c {
    uses g {
      refine "x" {
        if-feature "rf";
      }
    }
  }
}
"""
    mod = YangParser(expand_uses=True).parse_string(
        yang, filename=str(yang_source), source_path=yang_source
    )
    c = mod.find_statement("c")
    assert c is not None
    leaf_x = c.find_statement("x")
    assert isinstance(leaf_x, YangLeafStmt)
    assert leaf_x.if_features == ["rf"]


def test_feature_substatement_if_feature_stored_on_module(yang_source: Path) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature core;
  feature layered {
    if-feature "core";
    description "needs core";
  }
}
"""
    mod = _parse(yang, yang_source)
    assert mod.feature_if_features == {"layered": ["core"]}


def test_build_enabled_features_map_prunes_feature_per_feature_if_feature(
    yang_source: Path,
) -> None:
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:t";
  prefix x;
  feature a;
  feature b { if-feature "not a"; }
}
"""
    mod = _parse(yang, yang_source)
    m = build_enabled_features_map(mod, None)
    assert m["m"] == frozenset({"a"})
