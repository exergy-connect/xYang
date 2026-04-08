"""Round-trip ``if-features`` in JSON Schema ``x-yang`` (generate → parse)."""

from __future__ import annotations

from xyang import parse_yang_string
from xyang.ast import YangChoiceStmt, YangLeafStmt
from xyang.json import generate_json_schema, parse_json_schema


def test_if_features_emitted_on_leaf_and_round_trip():
    mod = parse_yang_string(
        """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  feature f;
  container data-model {
    leaf x {
      if-feature "f";
      type string;
    }
  }
}
"""
    )
    schema = generate_json_schema(mod)
    leaf_schema = schema["properties"]["data-model"]["properties"]["x"]
    assert leaf_schema["x-yang"].get("if-features") == ["f"]

    mod2 = parse_json_schema(schema)
    dm = mod2.find_statement("data-model")
    assert dm is not None
    leaf = next(s for s in dm.statements if s.name == "x")
    assert isinstance(leaf, YangLeafStmt)
    assert leaf.if_features == ["f"]


def test_if_features_choice_case_hoisted_round_trip():
    mod = parse_yang_string(
        """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  feature cf;
  feature bf;
  container data-model {
    choice ch {
      if-feature "cf";
      case a {
        if-feature "bf";
        leaf la { type string; }
      }
      case b {
        leaf lb { type string; }
      }
    }
  }
}
"""
    )
    schema = generate_json_schema(mod)
    dm = schema["properties"]["data-model"]
    assert dm["x-yang"]["choice"]["if-features"] == ["cf"]
    one_of = dm["oneOf"]
    branches_with_bf = [b for b in one_of if "la" in (b.get("properties") or {})]
    assert branches_with_bf
    assert branches_with_bf[0]["x-yang"].get("if-features") == ["bf"]

    mod2 = parse_json_schema(schema)
    dm2 = mod2.find_statement("data-model")
    assert dm2 is not None
    ch = next(s for s in dm2.statements if isinstance(s, YangChoiceStmt))
    assert ch.if_features == ["cf"]
    case_a = next(c for c in ch.cases if c.name == "a")
    assert case_a.if_features == ["bf"]


def test_if_features_multiple_and_on_leaf_round_trip():
    mod = parse_yang_string(
        """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  container data-model {
    leaf z {
      if-feature "p";
      if-feature "q";
      type string;
    }
  }
}
"""
    )
    schema = generate_json_schema(mod)
    assert schema["properties"]["data-model"]["properties"]["z"]["x-yang"]["if-features"] == [
        "p",
        "q",
    ]
    mod2 = parse_json_schema(schema)
    dm = mod2.find_statement("data-model")
    assert dm is not None
    leaf = next(s for s in dm.statements if s.name == "z")
    assert isinstance(leaf, YangLeafStmt)
    assert leaf.if_features == ["p", "q"]
