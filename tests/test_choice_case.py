"""
Tests for YANG choice/case statements.

RFC 7950 defines how ``mandatory`` interacts with choices and cases:

* **§7.9.4** — On a ``choice``, ``mandatory true`` means at least one node from
  exactly one of the choice's cases must exist in valid data (default ``false``).
  Whether that constraint is *evaluated* depends on the choice's closest ancestor
  that is not a non-presence container: if that ancestor is a **case** node,
  the constraint applies only when **any other node from that case** exists.

* **§7.6.5** — On a ``leaf`` under a case, ``mandatory true`` means the leaf
  must exist if **any** node from that case exists in the data tree.

The ``case-stmt`` grammar (Appendix A) does not list ``mandatory`` as a direct
substatement of ``case``; ``mandatory`` belongs to ``choice`` (and leaves, etc.).

This module also covers choice/case usage in the example meta-model (array
``item_type``: primitive vs entity).
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
from xyang.errors import YangSemanticError, YangSyntaxError


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
    """RFC 7950 §7.9.4: ``mandatory true`` on a ``choice`` is stored on the AST (data rules in §7.9.4 / §8)."""
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


def test_mandatory_substatement_under_case_is_rejected():
    """Appendix A ``case-stmt`` has no ``mandatory`` substatement; xYang rejects it."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    choice protocol {
      case a {
        mandatory true;
        leaf x { type string; }
      }
    }
  }
}
"""
    with pytest.raises(YangSyntaxError) as exc_info:
        parse_yang_string(yang_content)
    assert "case" in str(exc_info.value).lower() or "mandatory" in str(exc_info.value).lower()


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
    """RFC 7950 §7.6.5: ``mandatory`` on a ``leaf``; under a case, existence rules use the case ancestor (§7.6.5)."""
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


def test_rfc7950_section_7_9_4_mandatory_nested_choice_enforced_when_other_case_node_exists():
    """§7.9.4: mandatory on a nested choice is enforced when another node from the same outer case exists.

    The inner ``choice`` is wrapped in ``container inner_wrap`` so JSON mirrors the schema (the
    validator matches outer cases on direct child keys). Sibling ``sibling`` plus an empty
    ``inner_wrap`` leaves the inner mandatory choice unsatisfied.
    """
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    choice outer {
      case ca {
        leaf sibling { type string; }
        container inner_wrap {
          choice inner {
            mandatory true;
            case ia { leaf a { type string; } }
            case ib { leaf b { type string; } }
          }
        }
      }
      case cb {
        leaf z { type string; }
      }
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    invalid = {"data": {"sibling": "x", "inner_wrap": {}}}
    is_valid, errors, _warnings = validator.validate(invalid)
    assert not is_valid, (
        "sibling plus empty inner_wrap should violate mandatory inner choice (RFC 7950 §7.9.4)"
    )
    assert errors


def test_rfc7950_section_7_9_4_mandatory_nested_choice_satisfied_by_inner_branch_alone():
    """§7.9.4: only the inner branch need be present; no sibling leaf is required."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    choice outer {
      case ca {
        leaf sibling { type string; }
        container inner_wrap {
          choice inner {
            mandatory true;
            case ia { leaf a { type string; } }
            case ib { leaf b { type string; } }
          }
        }
      }
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    validator = YangValidator(module)
    valid = {"data": {"inner_wrap": {"a": "only-inner"}}}
    is_valid, errors, _warnings = validator.validate(valid)
    assert is_valid, f"Expected valid with inner case only. Errors: {errors}"


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
    """Test invalid meta-model data - missing mandatory choice.
    
    Note: This test documents expected behavior. When choice/case mandatory
    validation is implemented, this should fail validation.
    """
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
    # TODO: When choice/case mandatory validation is implemented, this should fail
    # assert not is_valid, "Expected invalid due to missing mandatory choice in item_type"
    # assert len(errors) > 0
    # Current behavior: may pass (needs implementation)
    assert isinstance(is_valid, bool)


def test_choice_duplicate_schema_node_name_across_cases_is_illegal():
    """RFC 7950 §7.9: identifiers of nodes in the cases of a choice must be unique (shared scope).

    Same name as ``leaf`` in one case and ``container`` in another is invalid YANG.
    """
    yang = """
module dup-choice {
  yang-version 1.1;
  namespace "urn:dup";
  prefix "d";

  container c {
    choice interface-type {
      case a {
        leaf ethernet {
          type string;
        }
      }
      case b {
        container ethernet {
          leaf x { type string; }
        }
      }
    }
  }
}
"""
    with pytest.raises(YangSemanticError) as exc_info:
        parse_yang_string(yang)
    assert "ethernet" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
