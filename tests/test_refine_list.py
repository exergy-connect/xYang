"""Tests that ``refine`` can target a ``list`` and apply cardinality (and related) substatements.

Also covers ``uses`` inside a ``list`` body with ``refine`` on the used grouping,
and a ``grouping generic-field`` shape **without** the ``case-array`` branch (recursive
``uses``; full expansion hits a grouping cycle unless expansion is disabled).
"""

from __future__ import annotations

import pytest

from xyang import parse_yang_string
from xyang.errors import YangCircularUsesError
from xyang.module import YangModule
from xyang.parser.yang_parser import YangParser
from xyang.xpath.ast import ast_is_const_false
from xyang.ast import (
    YangCaseStmt,
    YangChoiceStmt,
    YangLeafStmt,
    YangListStmt,
    YangStatement,
)


def _walk(stmt: YangStatement):
    yield stmt
    if isinstance(stmt, YangChoiceStmt):
        for case in stmt.cases:
            yield from _walk(case)
    elif isinstance(stmt, YangCaseStmt):
        for child in stmt.statements:
            yield from _walk(child)
    else:
        for child in getattr(stmt, "statements", []):
            yield from _walk(child)


def _find_list_named(module: YangModule, name: str) -> YangListStmt | None:
    for stmt in module.statements:
        for node in _walk(stmt):
            if isinstance(node, YangListStmt) and node.name == name:
                return node
    return None


def _find_leaf_named(module: YangModule, name: str) -> YangLeafStmt | None:
    for stmt in module.statements:
        for node in _walk(stmt):
            if isinstance(node, YangLeafStmt) and node.name == name:
                return node
    return None


def _lists_named(module: YangModule, name: str) -> list[YangListStmt]:
    return [
        node
        for stmt in module.statements
        for node in _walk(stmt)
        if isinstance(node, YangListStmt) and node.name == name
    ]


YANG_REFINE_LIST_CARDINALITY = """
module refine_list_cardinality {
  yang-version 1.1;
  namespace "urn:test:refine-list-cardinality";
  prefix "rlc";

  grouping g {
    list items {
      key k;
      leaf k {
        type string;
      }
    }
  }

  container c {
    uses g {
      refine items {
        max-elements 3;
        min-elements 1;
      }
    }
  }
}
"""


def test_refine_applies_max_min_elements_to_list():
    """``refine <list-name> { max-elements; min-elements; }`` mutates the list node after expansion."""
    module = parse_yang_string(YANG_REFINE_LIST_CARDINALITY)
    assert module.name == "refine_list_cardinality"
    lst = _find_list_named(module, "items")
    assert lst is not None, "expanded schema should contain list 'items'"
    assert lst.max_elements == 3
    assert lst.min_elements == 1


YANG_REFINE_LIST_UNDER_CHOICE_CASE = """
module refine_list_under_choice {
  yang-version 1.1;
  namespace "urn:test:refine-list-under-choice";
  prefix "rluc";

  grouping g {
    choice ch {
      case only {
        list rows {
          key id;
          leaf id {
            type string;
          }
        }
      }
    }
  }

  container root {
    uses g {
      refine ch/only/rows {
        max-elements 0;
        min-elements 0;
      }
    }
  }
}
"""


def test_refine_applies_to_list_under_choice_case():
    """Refine path through ``choice`` / ``case`` reaches the ``list`` and applies."""
    module = parse_yang_string(YANG_REFINE_LIST_UNDER_CHOICE_CASE)
    lst = _find_list_named(module, "rows")
    assert lst is not None
    assert lst.max_elements == 0
    assert lst.min_elements == 0


YANG_USES_IN_LIST_WITH_REFINE = """
module uses_in_list_with_refine {
  yang-version 1.1;
  namespace "urn:test:uses-in-list-with-refine";
  prefix "uil";

  grouping payload {
    leaf payload_leaf {
      type string;
    }
  }

  container c {
    list L {
      key k;
      leaf k {
        type string;
      }
      uses payload {
        refine payload_leaf {
          must "false()";
          description "Refine on a leaf inside grouping used from list body.";
        }
      }
    }
  }
}
"""


def test_uses_inside_list_with_refine_applies_to_grouping_leaf():
    """``list`` body may contain ``uses``; ``refine`` targets nodes from the used grouping."""
    module = parse_yang_string(YANG_USES_IN_LIST_WITH_REFINE)
    assert module.name == "uses_in_list_with_refine"
    lst = _find_list_named(module, "L")
    assert lst is not None, "list L should exist after expansion"
    leaf = _find_leaf_named(module, "payload_leaf")
    assert leaf is not None, "grouping leaf should be inlined under list L"
    assert leaf.must_statements and any(
        ast_is_const_false(m.ast) for m in leaf.must_statements
    ), "refine must false() should apply to payload_leaf"


YANG_GENERIC_FIELD_NO_ARRAY_CASE = """
module generic_field_no_array {
  yang-version 1.1;
  namespace "urn:test:generic-field-no-array";
  prefix "gfna";

  typedef primitive-type-name {
    type enumeration {
      enum string;
      enum integer;
    }
    description "Primitive type tag.";
  }

  grouping generic-field {
    description "Like examples/generic-field.yang but without the case-array branch.";
    leaf name {
      type string {
        length "1..128";
      }
      mandatory true;
      description "Field name.";
    }
    container type {
      description "Field type: primitive or composite only.";
      choice choice-type {
        mandatory true;
        description "Primitive or composite object.";
        case primitive {
          leaf primitive {
            type primitive-type-name;
            mandatory true;
            description "Primitive type.";
          }
        }
        case case-composite {
          description "Composite field: named subfields, each a full generic-field.";
          list fields {
            key name;
            min-elements 1;
            description "Subfields (recursive generic field).";
            uses generic-field {
              refine type/choice-type/case-composite/fields {
                max-elements 0;
                description "Exclude nested composite subfields; breaks recursive uses expansion.";
              }
            }
          }
        }
      }
    }
  }

  container field {
    description "Example instance root for one generic field.";
    uses generic-field;
  }
}
"""


def test_grouping_generic_field_without_case_array_raises_circular_uses_when_expanding():
    """Recursive ``uses generic-field`` under ``list fields`` is a non-terminating expand cycle."""
    with pytest.raises(YangCircularUsesError) as exc:
        parse_yang_string(YANG_GENERIC_FIELD_NO_ARRAY_CASE)
    assert "generic-field" in str(exc.value)


def test_grouping_generic_field_without_case_array_parses_with_expand_disabled():
    """Same module loads when ``uses`` expansion is skipped (refines stay on AST)."""
    parser = YangParser(expand_uses=False)
    module = parser.parse_string(YANG_GENERIC_FIELD_NO_ARRAY_CASE)
    assert module.name == "generic_field_no_array"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
