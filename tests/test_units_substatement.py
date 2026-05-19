"""RFC 7950 ``units`` substatement: parse, AST, and JSON Schema round-trip."""

from __future__ import annotations

from xyang import parse_yang_string
from xyang.ast import YangLeafStmt, YangLeafListStmt, YangTypedefStmt, YangTypeStmt
from xyang.json import generate_json_schema, parse_json_schema


def test_units_on_leaf_typedef_and_inline_type():
    yang = """
module example-units {
  yang-version 1.1;
  namespace "urn:example:units";
  prefix eu;

  typedef bandwidth {
    type uint32 {
      units "kbit/s";
    }
    units "kbit/s";
  }

  container stats {
    leaf rate {
      type bandwidth;
    }
    leaf speed {
      type uint32 {
        units "m/s";
      }
      units "km/h";
    }
    leaf-list samples {
      type uint8;
      units "packets";
    }
  }
}
"""
    mod = parse_yang_string(yang)
    td = mod.typedefs["bandwidth"]
    assert td.units == "kbit/s"
    assert td.type is not None
    assert td.type.units == "kbit/s"

    stats = mod.find_statement("stats")
    assert stats is not None
    rate = stats.find_statement("rate")
    assert isinstance(rate, YangLeafStmt)
    speed = stats.find_statement("speed")
    assert isinstance(speed, YangLeafStmt)
    assert speed.units == "km/h"
    assert speed.type is not None
    assert speed.type.units == "m/s"

    samples = stats.find_statement("samples")
    assert isinstance(samples, YangLeafListStmt)
    assert samples.units == "packets"


def test_units_json_schema_round_trip():
    yang = """
module example-units-rt {
  yang-version 1.1;
  namespace "urn:example:units-rt";
  prefix eurt;

  container c {
    leaf x {
      type int32 {
        units "seconds";
      }
    }
  }
}
"""
    mod = parse_yang_string(yang)
    schema = generate_json_schema(mod)
    mod2 = parse_json_schema(schema)
    c = mod2.find_statement("c")
    assert c is not None
    x = c.find_statement("x")
    assert isinstance(x, YangLeafStmt)
    assert x.type is not None
    assert x.type.units == "seconds"
