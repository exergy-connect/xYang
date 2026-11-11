"""Validate() does not mutate caller data during XPath comparisons.

Validity outcomes: tests/cases/xpath/type-coercion.
"""

from xyang import parse_yang_string, YangValidator

_BOOL_INT = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf enabled {
      type boolean;
      must "current() = true()";
    }
    leaf count {
      type int32;
      must "current() > 0";
    }
  }
}
"""


def test_validate_does_not_mutate_boolean_or_int_input():
    module = parse_yang_string(_BOOL_INT)
    validator = YangValidator(module)

    bool_data = {"data": {"enabled": "true"}}
    ok, errors, _ = validator.validate(bool_data)
    assert ok, errors
    assert bool_data["data"]["enabled"] == "true"
    assert isinstance(bool_data["data"]["enabled"], str)

    int_data = {"data": {"count": "123"}}
    ok, errors, _ = validator.validate(int_data)
    assert not ok
    assert int_data["data"]["count"] == "123"
    assert isinstance(int_data["data"]["count"], str)
