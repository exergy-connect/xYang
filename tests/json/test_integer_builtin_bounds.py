"""Integer built-in round-trip via JSON Schema minimum/maximum (not x-yang.builtin-type)."""

from __future__ import annotations

from xyang import parse_yang_string
from xyang.json import generate_json_schema, parse_json_schema
from xyang.json.integer_bounds import YANG_INTEGER_BOUNDS


def test_uint16_full_range_round_trips_without_builtin_type_key():
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  leaf x { type uint16; }
}
"""
    mod = parse_yang_string(yang)
    schema = generate_json_schema(mod)
    leaf = schema["properties"]["x"]["x-yang"]
    prop = schema["properties"]["x"]
    assert "builtin-type" not in leaf
    lo, hi = YANG_INTEGER_BOUNDS["uint16"]
    assert prop["minimum"] == lo
    assert prop["maximum"] == hi

    mod2 = parse_json_schema(schema)
    leaf2 = mod2.find_statement("x")
    assert leaf2 is not None
    assert leaf2.type is not None
    assert leaf2.type.name == "uint16"
    assert leaf2.type.range is None


def test_uint8_and_subrange_round_trip():
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  leaf a { type uint8; }
  leaf b { type uint16 { range "0..100"; } }
}
"""
    mod = parse_yang_string(yang)
    schema = generate_json_schema(mod)
    a = schema["properties"]["a"]
    assert a["minimum"] == 0
    assert a["maximum"] == 255
    b = schema["properties"]["b"]
    assert b["minimum"] == 0
    assert b["maximum"] == 100

    mod2 = parse_json_schema(schema)
    assert mod2.find_statement("a").type.name == "uint8"
    b_type = mod2.find_statement("b").type
    assert b_type.name == "uint8"
    assert b_type.range == "0..100"


def test_int32_zero_to_max_round_trips():
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  typedef t {
    type int32 { range "0..max"; }
  }
  leaf x { type t; }
}
"""
    mod = parse_yang_string(yang)
    schema = generate_json_schema(mod)
    tdef = schema["$defs"]["t"]
    _, hi = YANG_INTEGER_BOUNDS["int32"]
    assert tdef["minimum"] == 0
    assert tdef["maximum"] == hi

    mod2 = parse_json_schema(schema)
    td = mod2.typedefs["t"]
    assert td.type.name == "int32"
    assert td.type.range == "0..max"
