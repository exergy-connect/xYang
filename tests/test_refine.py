"""Consolidated tests for RFC 7950 ``refine`` behavior."""

from __future__ import annotations

import json

import pytest

from xyang import YangRefineTargetNotFoundError, parse_yang_string
from xyang.ast import (
    YangCaseStmt,
    YangChoiceStmt,
    YangLeafListStmt,
    YangLeafStmt,
    YangListStmt,
    YangStatement,
    YangUsesStmt,
)
from xyang.errors import YangCircularUsesError
from xyang.json.generator import generate_json_schema
from xyang.json.parser import parse_json_schema
from xyang.module import YangModule
from xyang.parser.yang_parser import YangParser
from xyang.xpath.ast import ast_is_const_false


def _leaf_under_container_c(module, *, name: str):
    c = module.statements[0]
    assert c.name == "c"
    leaf = c.statements[0]
    assert isinstance(leaf, YangLeafStmt)
    assert leaf.name == name
    return leaf


def _leaf_list_under_container_c(module, *, name: str):
    c = module.statements[0]
    assert c.name == "c"
    node = c.statements[0]
    assert isinstance(node, YangLeafListStmt)
    assert node.name == name
    return node


_REFINE_DEFAULT_FALSE = """
module refine_default_false {
  yang-version 1.1;
  namespace "urn:xyang:test:refine-default";
  prefix rd;

  grouping g {
    leaf flag {
      type boolean;
    }
  }

  container c {
    uses g {
      refine flag {
        default false;
      }
    }
  }
}
"""


def test_refine_leaf_default_false_parses_and_applies():
    mod = parse_yang_string(_REFINE_DEFAULT_FALSE)
    leaf = _leaf_under_container_c(mod, name="flag")
    assert leaf.default == "false"


def test_refine_required_default_false_nested_grouping_like_xframe():
    yang = """
module refine_required_default {
  yang-version 1.1;
  namespace "urn:xyang:test:refine-required-default";
  prefix rrd;

  grouping field_common {
    leaf required {
      type boolean;
    }
  }

  grouping generic_field {
    uses field_common {
      refine required {
        default false;
      }
    }
  }

  container c {
    uses generic_field;
  }
}
"""
    mod = parse_yang_string(yang)
    leaf = _leaf_under_container_c(mod, name="required")
    assert leaf.default == "false"


def test_refine_default_json_schema_has_default_and_round_trips():
    mod = parse_yang_string(_REFINE_DEFAULT_FALSE)
    schema = generate_json_schema(mod)
    flag_schema = schema["properties"]["c"]["properties"]["flag"]
    assert flag_schema.get("default") == "false"

    text = json.dumps(schema)
    mod2 = parse_json_schema(text)
    leaf = _leaf_under_container_c(mod2, name="flag")
    assert leaf.default == "false"


def test_refine_default_without_uses_expand_preserves_refine_ast():
    """When expand_uses is False, refined_defaults is stored on YangRefineStmt."""
    mod = YangParser(expand_uses=False).parse_string(_REFINE_DEFAULT_FALSE)
    c = mod.statements[0]
    uses = c.statements[0]
    assert isinstance(uses, YangUsesStmt)
    assert uses.name == "uses"
    assert len(uses.refines) == 1
    assert uses.refines[0].target_path.to_string() == "flag"
    assert uses.refines[0].refined_defaults == ["false"]


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("p:top/mid/payload", "p:top/mid/payload"),
        ("top/p:mid/payload", "top/p:mid/payload"),
        ("top/mid/p:payload", "top/mid/p:payload"),
        ('"p:top/p:mid/p:payload"', "p:top/p:mid/p:payload"),
    ],
)
def test_refine_prefixed_target_preserved_for_each_path_position(
    target: str, expected: str
) -> None:
    yang = f"""
module refine_prefix_locations {{
  yang-version 1.1;
  namespace "urn:xyang:test:refine-prefix-locations";
  prefix p;

  grouping g {{
    container top {{
      container mid {{
        leaf payload {{
          type string;
        }}
      }}
    }}
  }}

  container c {{
    uses g {{
      refine {target} {{
        description "location coverage";
      }}
    }}
  }}
}}
"""
    mod = YangParser(expand_uses=False).parse_string(yang)
    c = mod.statements[0]
    uses = c.statements[0]
    assert isinstance(uses, YangUsesStmt)
    assert len(uses.refines) == 1
    assert uses.refines[0].target_path.to_string() == expected


def test_refine_with_non_existing_prefix_raises_target_not_found() -> None:
    yang = """
module refine_bad_prefix {
  yang-version 1.1;
  namespace "urn:xyang:test:refine-bad-prefix";
  prefix p;

  grouping g {
    leaf flag {
      type boolean;
    }
  }

  container c {
    uses g {
      refine missing:flag {
        description "unknown prefix";
      }
    }
  }
}
"""
    with pytest.raises(YangRefineTargetNotFoundError) as exc_info:
        parse_yang_string(yang)
    assert "missing:flag" in exc_info.value.target_path


def test_refine_with_existing_prefix_but_missing_node_raises() -> None:
    yang = """
module refine_existing_prefix_missing_node {
  yang-version 1.1;
  namespace "urn:xyang:test:refine-existing-prefix-missing-node";
  prefix p;

  grouping g {
    leaf present {
      type string;
    }
  }

  container c {
    uses g {
      refine p:not-present {
        description "prefix exists but node does not";
      }
    }
  }
}
"""
    with pytest.raises(YangRefineTargetNotFoundError) as exc_info:
        parse_yang_string(yang)
    assert "p:not-present" in exc_info.value.target_path


def test_refine_quoted_target_without_uses_expand_parses_path():
    yang = """
module refine_quoted_target {
  yang-version 1.1;
  namespace "urn:xyang:test:refine-quoted-target";
  prefix rq;

  grouping g {
    leaf flag {
      type boolean;
    }
  }

  container c {
    uses g {
      refine "flag" {
        default false;
      }
    }
  }
}
"""
    mod = YangParser(expand_uses=False).parse_string(yang)
    c = mod.statements[0]
    uses = c.statements[0]
    assert isinstance(uses, YangUsesStmt)
    assert len(uses.refines) == 1
    assert uses.refines[0].target_path.to_string() == "flag"
    assert uses.refines[0].refined_defaults == ["false"]


_REFINE_LEAF_LIST_TWO_DEFAULTS = """
module refine_ll_defaults {
  yang-version 1.1;
  namespace "urn:xyang:test:refine-ll";
  prefix rll;

  grouping g {
    leaf-list tags {
      type string;
    }
  }

  container c {
    uses g {
      refine tags {
        default "alpha";
        default "beta";
      }
    }
  }
}
"""


def test_refine_leaf_list_multiple_defaults_applied():
    mod = parse_yang_string(_REFINE_LEAF_LIST_TWO_DEFAULTS)
    ll = _leaf_list_under_container_c(mod, name="tags")
    assert ll.defaults == ["alpha", "beta"]


def test_refine_leaf_list_single_default():
    yang = """
module refine_ll_one {
  yang-version 1.1;
  namespace "urn:xyang:test:refine-ll-one";
  prefix o;

  grouping g {
    leaf-list ids {
      type int32;
    }
  }
  container c {
    uses g {
      refine ids {
        default 7;
      }
    }
  }
}
"""
    mod = parse_yang_string(yang)
    ll = _leaf_list_under_container_c(mod, name="ids")
    assert len(ll.defaults) == 1
    assert ll.defaults[0] in (7, "7")


def test_refine_leaf_list_json_schema_default_array_round_trips():
    mod = parse_yang_string(_REFINE_LEAF_LIST_TWO_DEFAULTS)
    schema = generate_json_schema(mod)
    tags = schema["properties"]["c"]["properties"]["tags"]
    assert tags.get("default") == ["alpha", "beta"]

    text = json.dumps(schema)
    mod2 = parse_json_schema(text)
    ll = _leaf_list_under_container_c(mod2, name="tags")
    assert ll.defaults == ["alpha", "beta"]


def test_refine_bad_path_raises():
    yang = """
module t {
  yang-version 1.1;
  namespace "urn:test:t";
  prefix "t";
  grouping g {
    leaf a { type string; }
  }
  container c {
    uses g {
      refine does_not_exist {
        description "x";
      }
    }
  }
}
"""
    with pytest.raises(YangRefineTargetNotFoundError) as exc_info:
        parse_yang_string(yang)
    assert "does_not_exist" in str(exc_info.value)


def test_refine_min_elements_bad_path_raises():
    yang = """
module t2 {
  yang-version 1.1;
  namespace "urn:test:t2";
  prefix "t";
  grouping g {
    leaf a { type string; }
  }
  container c {
    uses g {
      refine missing/list {
        max-elements 0;
      }
    }
  }
}
"""
    with pytest.raises(YangRefineTargetNotFoundError) as exc_info:
        parse_yang_string(yang)
    assert "missing/list" in exc_info.value.target_path


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
    module = parse_yang_string(YANG_REFINE_LIST_CARDINALITY)
    assert module.name == "refine_list_cardinality"
    lst = _find_list_named(module, "items")
    assert lst is not None
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
    module = parse_yang_string(YANG_USES_IN_LIST_WITH_REFINE)
    assert module.name == "uses_in_list_with_refine"
    lst = _find_list_named(module, "L")
    assert lst is not None
    leaf = _find_leaf_named(module, "payload_leaf")
    assert leaf is not None
    assert leaf.must_statements and any(
        ast_is_const_false(m.ast) for m in leaf.must_statements
    )


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
    with pytest.raises(YangCircularUsesError) as exc:
        parse_yang_string(YANG_GENERIC_FIELD_NO_ARRAY_CASE)
    assert "generic-field" in str(exc.value)


def test_grouping_generic_field_without_case_array_parses_with_expand_disabled():
    parser = YangParser(expand_uses=False)
    module = parser.parse_string(YANG_GENERIC_FIELD_NO_ARRAY_CASE)
    assert module.name == "generic_field_no_array"


def test_refine_mandatory_false_on_grouping_leaf():
    yang = """
module t {
  namespace "urn:test:r";
  prefix "r";
  grouping g {
    leaf entity {
      type string;
      mandatory true;
    }
  }
  container c {
    uses g {
      refine entity {
        mandatory false;
      }
    }
  }
}
"""
    mod = YangParser(expand_uses=True).parse_string(yang)
    container = mod.statements[0]
    leaf = container.statements[0]
    assert isinstance(leaf, YangLeafStmt)
    assert leaf.name == "entity"
    assert leaf.mandatory is False
