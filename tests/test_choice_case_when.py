"""RFC 7950 ``when`` on ``choice`` and ``case`` (parser + validator)."""

from __future__ import annotations

from xyang import YangValidator, parse_yang_string

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


def test_choice_when_false_skips_branch_data_ok():
    m = parse_yang_string(_MODULE)
    v = YangValidator(m)
    ok, errors, _w = v.validate({"root": {"mode": "off"}})
    assert ok, errors


def test_choice_when_false_with_branch_data_errors():
    m = parse_yang_string(_MODULE)
    v = YangValidator(m)
    ok, errors, _w = v.validate({"root": {"mode": "off", "a": "x"}})
    assert not ok
    assert any("when" in e.lower() for e in errors)


def test_case_when_false_with_data_errors():
    m = parse_yang_string(_MODULE)
    v = YangValidator(m)
    ok, errors, _w = v.validate({"root": {"mode": "on", "a": "x"}})
    assert not ok
    assert any("when" in e.lower() for e in errors)


def test_case_b_without_case_when_when_choice_applies():
    m = parse_yang_string(_MODULE)
    v = YangValidator(m)
    ok, errors, _w = v.validate({"root": {"mode": "on", "b": "y"}})
    assert ok, errors
