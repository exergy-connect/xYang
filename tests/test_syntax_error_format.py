"""YangSyntaxError string format includes source location."""

from __future__ import annotations

import pytest

from xyang import parse_yang_string
from xyang.errors import YangSyntaxError


def test_syntax_error_str_includes_line_and_message() -> None:
    with pytest.raises(YangSyntaxError) as exc_info:
        parse_yang_string(
            """module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  typedef t {
    type string;
    bogus-stmt "x";
  }
}"""
        )
    err = exc_info.value
    assert err.line_num is not None
    text = str(err)
    assert f"{err.line_num}:" in text
    assert "typedef" in text
    assert "bogus-stmt" in text
