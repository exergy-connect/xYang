"""
Tests for grouping and uses statements in YANG.

Validation of basic/nested uses, list uses, and refine-must lives in
``tests/cases/reuse/``. This file keeps parser-shape and when/must scenarios
that are not shared cases.
"""

from xyang import parse_yang_string, YangValidator


def test_grouping_status_and_nested_grouping_parse():
    """RFC 7950 status on grouping and nested grouping (ietf-yang-library shape)."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test:grouping-status";
  prefix t;

  grouping outer {
    status deprecated;
    grouping inner {
      leaf name { type string; }
    }
    uses inner;
  }

  container data {
    uses outer;
  }
}
"""
    module = parse_yang_string(yang_content)
    assert "outer" in module.groupings
    assert "inner" in module.groupings


def test_must_validation_context_nested_grouping():
    """must in a nested grouping inside a list sees the list entry sibling context."""
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  grouping base-fields {
    leaf id {
      type string;
      mandatory true;
    }
    leaf status {
      type string;
      must "../id != ''" {
        error-message "id must not be empty when status is set";
      }
    }
  }

  grouping extended-fields {
    uses base-fields;
    leaf name {
      type string;
    }
  }

  list items {
    key id;
    uses extended-fields;
  }
}
"""
    module = parse_yang_string(yang_content)
    assert module.name == "test"

    validator = YangValidator(module)

    valid_data = {
        "items": [
            {
                "id": "item1",
                "status": "active",
                "name": "Item 1"
            }
        ]
    }
    is_valid, errors, warnings = validator.validate(valid_data)
    assert is_valid, f"Expected valid data, got errors: {errors}"


def test_uses_when_under_choice_case_sees_container_sibling():
    """RFC 7950 §7.21.5: ``when`` on ``uses`` uses the closest data ancestor (the container).

    Also covers ``when`` on ``choice`` (whole payload) and on each ``case`` (branch), all
    referencing container leaf ``profile``. Instance data stays flat under ``data``.
    """
    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test:uses-when-choice";
  prefix "t";

  grouping extended-body {
    leaf extension-note {
      type string;
      mandatory true;
    }
  }

  container data {
    leaf profile {
      type string;
      default "basic";
    }
    choice payload {
      when "./profile != 'off'";
      case basic-case {
        when "./profile = 'basic'";
        leaf title {
          type string;
          mandatory true;
        }
      }
      case extended-case {
        uses extended-body {
          when "./profile = 'extended'";
        }
      }
    }
  }
}
"""
    module = parse_yang_string(yang_content)
    assert module.name == "test"

    validator = YangValidator(module)

    ok, errors, _ = validator.validate(
        {"data": {"profile": "basic", "title": "Hello"}}
    )
    assert ok, errors

    ok, errors, _ = validator.validate(
        {"data": {"profile": "extended", "extension-note": "more detail"}}
    )
    assert ok, errors

    ok, errors, _ = validator.validate(
        {"data": {"profile": "off", "title": "no payload when profile is off"}}
    )
    assert not ok, "choice when: no payload data when profile=off"
    assert errors

    ok, errors, _ = validator.validate(
        {"data": {"profile": "extended", "title": "wrong case for profile=extended"}}
    )
    assert not ok, "basic-case when: title invalid when profile=extended"
    assert errors

    ok, errors, _ = validator.validate(
        {"data": {"profile": "basic", "extension-note": "should not apply"}}
    )
    assert not ok, (
        "extension-note is only valid when profile=extended (case when + uses when)"
    )
    assert errors
