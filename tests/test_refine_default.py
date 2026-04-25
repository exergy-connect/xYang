"""https://github.com/exergy-connect/xYang/issues/7 — ``default`` under ``refine``."""

import json

from xyang import parse_yang_string
from xyang.ast import YangLeafListStmt, YangLeafStmt, YangUsesStmt
from xyang.json.generator import generate_json_schema
from xyang.json.parser import parse_json_schema
from xyang.parser.yang_parser import YangParser

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


def test_refine_prefixed_target_without_uses_expand_preserves_prefix():
    yang = """
module refine_prefixed_target {
  yang-version 1.1;
  namespace "urn:xyang:test:refine-prefixed-target";
  prefix rd;

  grouping g {
    leaf flag {
      type boolean;
    }
  }

  container c {
    uses g {
      refine rd:flag {
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
    assert uses.refines[0].target_path.to_string() == "rd:flag"
    assert uses.refines[0].refined_defaults == ["false"]


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
