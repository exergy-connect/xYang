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
    YangUsesStmt,
)
from xyang.json.generator import generate_json_schema
from xyang.json.parser import parse_json_schema
from xyang.parser.yang_parser import YangParser


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
    assert flag_schema.get("default") is False

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


_REFINE_KEYWORD_NODE_NAME = """
module refine_keyword_node_name {
  yang-version 1.1;
  namespace "urn:xyang:test:refine-keyword-node-name";
  prefix rknn;

  grouping g {
    leaf type {
      type boolean;
    }
  }

  container c {
    uses g {
      refine type {
        default false;
      }
    }
  }
}
"""


def test_refine_keyword_node_name_parses_and_applies() -> None:
    mod = parse_yang_string(_REFINE_KEYWORD_NODE_NAME)
    leaf = _leaf_under_container_c(mod, name="type")
    assert leaf.default == "false"

    mod_no_expand = YangParser(expand_uses=False).parse_string(_REFINE_KEYWORD_NODE_NAME)
    c = mod_no_expand.statements[0]
    uses = c.statements[0]
    assert isinstance(uses, YangUsesStmt)
    assert len(uses.refines) == 1
    assert uses.refines[0].target_path.to_string() == "type"
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


def test_grouping_generic_field_without_case_array_parses_with_expand_disabled():
    parser = YangParser(expand_uses=False)
    module = parser.parse_string(YANG_GENERIC_FIELD_NO_ARRAY_CASE)
    assert module.name == "generic_field_no_array"


def test_refine_description_on_choice_case():
    yang = """
module refine_case_desc {
  yang-version 1.1;
  namespace "urn:test:refine-case-desc";
  prefix rc;

  grouping g {
    choice target {
      case stream {
        choice stream-filter {
          case within-subscription {
            leaf x { type string; }
          }
        }
      }
    }
  }

  container root {
    uses g {
      refine "target/stream/stream-filter/within-subscription" {
        description "Refined case description.";
      }
    }
  }
}
"""
    mod = parse_yang_string(yang)
    target = mod.find_statement("root")
    assert target is not None
    ch_target = target.find_statement("target")
    assert isinstance(ch_target, YangChoiceStmt)
    case_stream = next(c for c in ch_target.cases if c.name == "stream")
    ch_filter = next(
        s for s in case_stream.statements if isinstance(s, YangChoiceStmt)
    )
    case_within = next(c for c in ch_filter.cases if c.name == "within-subscription")
    assert case_within.description == "Refined case description."

