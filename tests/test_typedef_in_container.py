"""``typedef`` nested in container, list, and grouping (RFC 7950 §7.13)."""

from __future__ import annotations

from pathlib import Path

from xyang import parse_yang_string, YangValidator
from xyang.parser import YangParser

CONTAINER_TYPEDEF = """
module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  container outer {
    typedef status-bits {
      type bits {
        bit on;
        bit off;
      }
    }
    leaf flags {
      type status-bits;
    }
  }
}
"""

GROUPING_TYPEDEF = """
module m2 {
  yang-version 1.1;
  namespace "urn:example:m2";
  prefix m2;
  grouping g {
    typedef code {
      type enumeration {
        enum a;
        enum b;
      }
    }
    leaf value { type code; }
  }
  container c { uses g; }
}
"""


def test_parse_typedef_inside_container() -> None:
    """Container-scoped typedef is registered and referenced by a leaf."""
    mod = parse_yang_string(CONTAINER_TYPEDEF)
    assert "status-bits" in mod.typedefs
    outer = mod.find_statement("outer")
    assert outer is not None
    assert outer.find_statement("flags") is not None


def test_validate_leaf_using_container_scoped_typedef() -> None:
    """Validation applies typedef constraints from a container-local typedef."""
    mod = parse_yang_string(CONTAINER_TYPEDEF)
    v = YangValidator(mod)
    ok, errors, _ = v.validate({"outer": {"flags": "on"}})
    assert ok, errors
    ok, errors, _ = v.validate({"outer": {"flags": "nope"}})
    assert not ok
    assert errors


def test_parse_typedef_inside_grouping() -> None:
    """Grouping typedef is registered and visible after ``uses`` expansion."""
    mod = parse_yang_string(GROUPING_TYPEDEF)
    assert "code" in mod.typedefs
    c = mod.find_statement("c")
    assert c is not None
    assert c.find_statement("value") is not None


def test_uses_registers_grouping_typedef_on_importing_module(tmp_path: Path) -> None:
    """``uses`` of an imported grouping copies typedefs onto the importing module."""
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "provider.yang").write_text(
        """module provider {
  yang-version 1.1;
  namespace "urn:example:provider";
  prefix p;
  grouping g {
    typedef code {
      type enumeration {
        enum a;
        enum b;
      }
    }
    leaf value { type code; }
  }
}
""",
        encoding="utf-8",
    )
    main = tmp_path / "consumer.yang"
    main.write_text(
        """module consumer {
  yang-version 1.1;
  namespace "urn:example:consumer";
  prefix c;
  import provider { prefix p; }
  container data { uses p:g; }
}
""",
        encoding="utf-8",
    )
    mod = YangParser(include_path=(inc,)).parse_file(main)
    assert "code" in mod.typedefs
    v = YangValidator(mod)
    ok, errors, _ = v.validate({"data": {"value": "a"}})
    assert ok, errors
    ok, errors, _ = v.validate({"data": {"value": "nope"}})
    assert not ok
    assert errors
