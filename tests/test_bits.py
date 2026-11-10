"""Tests for YANG ``bits`` built-in type (RFC 7950 §9.3.4)."""

from __future__ import annotations

import json

from xyang import parse_yang_string
from xyang.json import parse_json_schema, schema_to_yang_json
from xyang.parser import YangParser


BITS_TYPEDEF_MODULE = """
module bits-test {
  yang-version 1.1;
  namespace "urn:test:bits";
  prefix "t";

  typedef flags {
    type bits {
      bit execute { position 0; description "run"; }
      bit read { position 2; }
      bit write;
    }
  }

  container top {
    leaf mode {
      type flags;
    }
  }
}
"""

def test_bits_typedef_implicit_positions():
    module = parse_yang_string(BITS_TYPEDEF_MODULE)
    td = module.typedefs["flags"]
    assert td.type is not None
    assert td.type.name == "bits"
    by_name = {b.name: b.position for b in td.type.bits}
    assert by_name == {"execute": 0, "read": 2, "write": 3}


def test_bits_implicit_before_explicit_uses_declaration_order():
    """RFC 7950: implicit position uses max-so-far in source order, not after all explicits."""
    yang = """
module x {
  yang-version 1.1;
  namespace "urn:x"; prefix "x";
  typedef t {
    type bits {
      bit early;
      bit late { position 5; }
    }
  }
}
"""
    module = parse_yang_string(yang)
    td = module.typedefs["t"]
    assert td.type is not None
    by_name = {b.name: b.position for b in td.type.bits}
    assert by_name == {"early": 0, "late": 5}


def test_bits_json_schema_roundtrip():
    p = YangParser(expand_uses=False)
    module = p.parse_string(BITS_TYPEDEF_MODULE)
    text = schema_to_yang_json(module)
    data = json.loads(text)
    flags_def = (data.get("$defs") or {}).get("flags", {})
    assert flags_def.get("type") == "string"
    assert "pattern" in flags_def
    assert "examples" in flags_def
    assert isinstance(flags_def["examples"], list)
    assert "" in flags_def["examples"]
    bits_xyang = flags_def.get("x-yang") or {}
    assert bits_xyang.get("type") == "bits"
    assert isinstance(bits_xyang.get("bits"), dict)
    assert bits_xyang["bits"] == {"execute": 0, "read": 2, "write": 3}
    roundtrip = parse_json_schema(data)
    t1 = module.typedefs["flags"].type
    t2 = roundtrip.typedefs["flags"].type
    assert t1 is not None and t2 is not None
    assert t1.name == "bits" and t2.name == "bits"
    assert {b.name: b.position for b in t1.bits} == {b.name: b.position for b in t2.bits}
