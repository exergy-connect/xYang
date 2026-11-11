"""RFC 7950 ``when`` on ``choice`` and ``case`` (parser AST).

Validation coverage: tests/cases/choice/choice-case-when.
"""

from __future__ import annotations

from xyang import parse_yang_string

_MODULE = """
module test-choice-when {
  yang-version 1.1;
  namespace "urn:test:cw";
  prefix "cw";

  container root {
    leaf mode {
      type string;
    }
    choice c {
      when "./mode = 'on'";
      case a {
        when "./mode = 'off'";
        leaf a { type string; }
      }
      case b {
        leaf b { type string; }
      }
    }
  }
}
"""


def test_parse_choice_and_case_when():
    m = parse_yang_string(_MODULE)
    root = m.find_statement("root")
    assert root is not None
    ch = next(s for s in root.statements if s.name == "c")
    assert ch.when is not None
    assert "mode = 'on'" in ch.when.condition
    case_a = next(c for c in ch.cases if c.name == "a")
    assert case_a.when is not None
    assert "off" in case_a.when.condition
