"""Tests for YANG ``binary`` built-in type (RFC 7950 §9.8)."""

from __future__ import annotations

import base64

from xyang import YangValidator, parse_yang_string

MODULE = """
module bin-test {
  yang-version 1.1;
  namespace "urn:test:bin";
  prefix "b";

  container top {
    leaf data {
      type binary {
        length "0..16";
      }
    }
  }
}
"""


def test_binary_valid() -> None:
    mod = parse_yang_string(MODULE)
    v = YangValidator(mod)
    raw = b"hello"
    b64 = base64.b64encode(raw).decode("ascii")
    ok, errs, _ = v.validate({"top": {"data": b64}})
    assert ok
    assert errs == []


def test_binary_invalid_base64() -> None:
    mod = parse_yang_string(MODULE)
    v = YangValidator(mod)
    ok, errs, _ = v.validate({"top": {"data": "not!!!base64"}})
    assert not ok
    assert any("base64" in e.lower() for e in errs)


def test_binary_length_violation() -> None:
    mod = parse_yang_string(MODULE)
    v = YangValidator(mod)
    too_long = base64.b64encode(b"x" * 20).decode("ascii")
    ok, errs, _ = v.validate({"top": {"data": too_long}})
    assert not ok
    assert errs
