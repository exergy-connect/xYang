"""YANG tokenizer: ``//`` comments must not eat ``//`` inside quoted strings."""

from __future__ import annotations

import pytest

from xyang.parser.parser_context import diagnostic_source_lines
from xyang import parse_yang_string


@pytest.mark.parametrize(
    "line,expected_lines",
    [
        ('  contact "https://github.com/foo";  ', ['  contact "https://github.com/foo";  ']),
        ("  leaf x 'a//b'; // tail", ["  leaf x 'a//b'; // tail"]),
        ('foo "x" // c', ['foo "x" // c']),
        ("no comment", ["no comment"]),
        ("// only comment", ["// only comment"]),
        ('  ', ['  ']),
    ],
)
def test_diagnostic_source_lines(line: str, expected_lines: list[str]) -> None:
    assert diagnostic_source_lines(line) == expected_lines


def test_parse_module_contact_with_https_url() -> None:
    yang = '''
module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix "t";
  contact "https://example.org/path";
  container data-model { leaf x { type string; } }
}
'''
    mod = parse_yang_string(yang)
    assert mod.contact == "https://example.org/path"


def test_parse_leaf_default_string_with_double_slash() -> None:
    yang = """
module t {
  yang-version 1.1;
  namespace "urn:t";
  prefix "t";
  leaf u {
    type string;
    default "https://example.org/a/b";
  }
}
"""
    mod = parse_yang_string(yang)
    leaves = mod.get_all_leaves()
    u = next((L for L in leaves if L.name == "u"), None)
    assert u is not None
    assert u.default == "https://example.org/a/b"
