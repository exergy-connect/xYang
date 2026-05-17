"""Revision statement parsing: description and reference substatements."""

from __future__ import annotations

from xyang import parse_yang_string


def test_revision_reference_parsed() -> None:
    mod = parse_yang_string(
        """module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  revision 2019-09-11 {
    description "Initial revision.";
    reference "RFC 8632: A YANG Data Model for Alarm Management";
  }
}"""
    )
    assert len(mod.revisions) == 1
    rev = mod.revisions[0]
    assert rev["date"] == "2019-09-11"
    assert rev["description"] == "Initial revision."
    assert rev["reference"] == "RFC 8632: A YANG Data Model for Alarm Management"


def test_revision_description_only() -> None:
    mod = parse_yang_string(
        """module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  revision 2020-01-01 {
    description "Only description.";
  }
}"""
    )
    rev = mod.revisions[0]
    assert rev["description"] == "Only description."
    assert rev["reference"] == ""
