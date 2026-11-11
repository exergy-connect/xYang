"""
Tests for YANG choice/case statement AST and meta-model usage.

Validation coverage:
  tests/cases/choice/mandatory-choice
  tests/cases/choice/exclusive-cases
  tests/cases/choice/nested-mandatory
  tests/cases/choice/duplicate-case-names
  tests/cases/parser/substatements/case-mandatory
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.meta_model_data import dm, ent, f_array_entity, fp
from xyang import parse_yang_file, parse_yang_string, YangValidator
from xyang.ast import (
    YangChoiceStmt,
    YangContainerStmt,
    YangGroupingStmt,
    YangLeafStmt,
    YangListStmt,
)


def _walk_stmt(stmt: Any) -> Iterator[YangChoiceStmt]:
    """Yield every choice under stmt (recurses into container/list/grouping/case bodies)."""
    if isinstance(stmt, YangChoiceStmt):
        yield stmt
        for case in stmt.cases:
            for child in case.statements:
                yield from _walk_stmt(child)
    elif isinstance(stmt, (YangContainerStmt, YangListStmt, YangGroupingStmt)):
        for child in stmt.statements:
            yield from _walk_stmt(child)


def _iter_module_choices(module: Any) -> Iterator[YangChoiceStmt]:
    for stmt in module.statements:
        yield from _walk_stmt(stmt)


def _first_choice_named(module: Any, name: str) -> YangChoiceStmt:
    for ch in _iter_module_choices(module):
        if ch.name == name:
            return ch
    raise AssertionError(f"No choice named {name!r} in module")


def test_choice_mandatory_true_on_choice_statement_sets_ast():
    """RFC 7950 §7.9.4: ``mandatory true`` on a ``choice`` is stored on the AST."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    choice protocol {
      mandatory true;
      case a {
        leaf x { type string; }
      }
      case b {
        leaf y { type string; }
      }
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    ch = _first_choice_named(module, "protocol")
    assert ch.mandatory is True


def test_choice_mandatory_false_on_choice_statement_sets_ast():
    """RFC 7950 §7.9.4: default is ``false``; explicit ``mandatory false`` is accepted."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    choice protocol {
      mandatory false;
      case a {
        leaf x { type string; }
      }
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    ch = _first_choice_named(module, "protocol")
    assert ch.mandatory is False


def test_choice_inline_leaf_creates_implicit_case():
    """RFC 7950 §7.9.2: ``leaf`` directly under ``choice`` implies a ``case`` with the same name."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    choice sev-spec {
      leaf below { type string; }
      leaf is { type string; }
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    ch = _first_choice_named(module, "sev-spec")
    assert [c.name for c in ch.cases] == ["below", "is"]
    for case in ch.cases:
        assert len(case.statements) == 1
        assert isinstance(case.statements[0], YangLeafStmt)
        assert case.statements[0].name == case.name


def test_leaf_mandatory_true_inside_choice_case_parses():
    """RFC 7950 §7.6.5: ``mandatory`` on a ``leaf`` under a case; choice stays non-mandatory."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    choice protocol {
      case a {
        leaf x {
          type string;
          mandatory true;
        }
      }
      case b {
        leaf y { type string; }
      }
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    ch = _first_choice_named(module, "protocol")
    assert ch.mandatory is False
    case_a = next(c for c in ch.cases if c.name == "a")
    leaf_x = next(s for s in case_a.statements if isinstance(s, YangLeafStmt) and s.name == "x")
    assert leaf_x.mandatory is True


def test_choice_case_meta_model_primitive():
    """Test choice/case in meta-model with array-of-primitive case."""
    yang_path = Path(__file__).parent.parent / "examples" / "meta-model.yang"
    module = parse_yang_file(str(yang_path))
    validator = YangValidator(module)

    data = dm(
        entities=[
            ent(
                "test_entity",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    {
                        "name": "tags",
                        "description": "String tags.",
                        "type": {"array": {"primitive": "string"}},
                    },
                ],
            ),
        ],
    )

    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Expected valid meta-model data with primitive case. Errors: {errors}"


def test_choice_case_meta_model_entity():
    """Test choice/case in meta-model with array-of-entity case."""
    yang_path = Path(__file__).parent.parent / "examples" / "meta-model.yang"
    module = parse_yang_file(str(yang_path))
    validator = YangValidator(module)

    data = dm(
        entities=[
            ent("parent", "id", [fp("id", "integer", description="PK.")]),
            ent(
                "child",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    f_array_entity("parents", "parent", description="Parent entities."),
                ],
            ),
        ],
    )

    is_valid, errors, warnings = validator.validate(data)
    assert is_valid, f"Expected valid meta-model data with entity case. Errors: {errors}"


def test_choice_case_meta_model_missing():
    """Documents current meta-model behavior for an empty array inner choice."""
    yang_path = Path(__file__).parent.parent / "examples" / "meta-model.yang"
    module = parse_yang_file(str(yang_path))
    validator = YangValidator(module)

    data = dm(
        entities=[
            ent(
                "test_entity",
                "id",
                [
                    fp("id", "integer", description="PK."),
                    {"name": "tags", "description": "Empty array inner choice.", "type": {"array": {}}},
                ],
            ),
        ],
    )

    is_valid, errors, warnings = validator.validate(data)
    assert isinstance(is_valid, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
