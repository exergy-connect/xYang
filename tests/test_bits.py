"""Tests for YANG ``bits`` built-in type (RFC 7950 §9.3.4)."""

from __future__ import annotations

import json

import pytest

from xyang import YangValidator, parse_yang_string
from xyang.errors import YangSyntaxError
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

UNION_BITS_MODULE = """
module bits-union {
  yang-version 1.1;
  namespace "urn:test:bits-u";
  prefix "u";

  leaf val {
    type union {
      type int32;
      type bits {
        bit a;
        bit b;
      };
    };
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
    by_name = {b.name: b.position for b in module.typedefs["t"].type.bits}
    assert by_name == {"early": 0, "late": 5}


def test_bits_validate_empty_and_sets():
    module = parse_yang_string(BITS_TYPEDEF_MODULE)
    v = YangValidator(module)
    ok, err, _ = v.validate({"top": {"mode": ""}})
    assert ok and not err
    ok, err, _ = v.validate({"top": {"mode": "execute read"}})
    assert ok and not err
    ok, err, _ = v.validate({"top": {"mode": "write"}})
    assert ok and not err


def test_bits_validate_rejects_unknown():
    module = parse_yang_string(BITS_TYPEDEF_MODULE)
    v = YangValidator(module)
    ok, err, _ = v.validate({"top": {"mode": "nope"}})
    assert not ok and err


def test_bits_validate_rejects_duplicate_token():
    module = parse_yang_string(BITS_TYPEDEF_MODULE)
    v = YangValidator(module)
    ok, err, _ = v.validate({"top": {"mode": "execute execute"}})
    assert not ok and err


def test_bits_validate_rejects_non_string():
    module = parse_yang_string(BITS_TYPEDEF_MODULE)
    v = YangValidator(module)
    ok, err, _ = v.validate({"top": {"mode": 1}})
    assert not ok and err


def test_bits_duplicate_bit_name_parse_error():
    bad = """
module x {
  yang-version 1.1;
  namespace "urn:x"; prefix "x";
  typedef t {
    type bits {
      bit a;
      bit a;
    }
  }
}
"""
    with pytest.raises(YangSyntaxError):
        parse_yang_string(bad)


def test_bits_union_member():
    module = parse_yang_string(UNION_BITS_MODULE)
    v = YangValidator(module)
    ok, err, _ = v.validate({"val": 42})
    assert ok and not err
    ok, err, _ = v.validate({"val": "a b"})
    assert ok and not err
    ok, err, _ = v.validate({"val": "not-a-bit"})
    assert not ok and err


def test_bits_json_schema_roundtrip():
    p = YangParser(expand_uses=False)
    module = p.parse_string(BITS_TYPEDEF_MODULE)
    text = schema_to_yang_json(module)
    data = json.loads(text)
    roundtrip = parse_json_schema(data)
    t1 = module.typedefs["flags"].type
    t2 = roundtrip.typedefs["flags"].type
    assert t1 is not None and t2 is not None
    assert t1.name == "bits" and t2.name == "bits"
    assert {b.name: b.position for b in t1.bits} == {b.name: b.position for b in t2.bits}
