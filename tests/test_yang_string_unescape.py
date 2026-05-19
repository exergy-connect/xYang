"""RFC 7950 §6.2 quoted string unescaping."""

from __future__ import annotations

import re
from pathlib import Path

from xyang import parse_yang_file, parse_yang_string
from xyang.parser.yang_strings import unescape_yang_quoted_string


def test_unescape_double_quoted_backslash() -> None:
    assert unescape_yang_quoted_string("\\\\d{4}", '"') == "\\d{4}"


def test_unescape_double_quoted_quote_and_newline() -> None:
    assert unescape_yang_quoted_string('say \\"hi\\"', '"') == 'say "hi"'
    assert unescape_yang_quoted_string("line1\\nline2", '"') == "line1\nline2"


def test_unescape_single_quoted_backslash() -> None:
    assert unescape_yang_quoted_string("\\\\.", "'") == "\\."


def test_date_and_time_pattern_matches_rfc3339() -> None:
    mod = parse_yang_string(
        """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  typedef date-and-time {
    type string {
      pattern "\\\\d{4}-\\\\d{2}-\\\\d{2}T\\\\d{2}:\\\\d{2}:\\\\d{2}(\\\\.\\\\d+)?"
            + "(Z|[\\\\+\\\\-]\\\\d{2}:\\\\d{2})";
    }
  }
  leaf t { type date-and-time; }
}
"""
    )
    pat = mod.typedefs["date-and-time"].type.patterns[0].pattern
    assert re.search(pat, "2026-01-22T06:20:36.511Z")


def test_ietf_yang_types_date_and_time_from_vendor_module() -> None:
    path = Path("examples/ietf-yang-push/modules/ietf-yang-types@2013-07-15.yang")
    mod = parse_yang_file(path, include_path=("examples/ietf-yang-push/modules",))
    pat = mod.typedefs["date-and-time"].type.patterns[0].pattern
    assert "\\d{4}" in pat
    assert "\\\\d{4}" not in pat
    assert re.search(pat, "2026-01-22T06:20:36.511Z")
