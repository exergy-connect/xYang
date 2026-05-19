"""
XPath parsing of ``must`` / ``when`` with YANG-style escaped quotes.

YANG keeps ``\\"`` in the expression text passed to :class:`~xyang.xpath.XPathParser`
(e.g. from ietf-subscribed-notifications / ietf-system). The XPath tokenizer
normalizes those to ordinary quotes before lexing.
"""

from __future__ import annotations

from xyang import parse_yang_string
from xyang.xpath import XPathParser
from xyang.xpath.tokenizer import XPathTokenizer, normalize_yang_escaped_quotes
from xyang.xpath.tokens import TokenType

_SUB_NOTIF_WHEN_EXPR = (
    "not(../transport) or derived-from(../transport,\n"
    '             \\"sn:configurable-encoding\\")'
)
_IETF_SYSTEM_MUST_EXPR = '(. != \\"sys:radius\\" or ../../radius/server)'


def test_normalize_yang_escaped_quotes() -> None:
    assert (
        normalize_yang_escaped_quotes('derived-from(x, \\"sn:foo\\")')
        == 'derived-from(x, "sn:foo")'
    )
    assert (
        normalize_yang_escaped_quotes(_IETF_SYSTEM_MUST_EXPR)
        == '(. != "sys:radius" or ../../radius/server)'
    )


def test_xpath_tokenizer_string_literal_after_yang_escape() -> None:
    tokens = [
        t
        for t in XPathTokenizer('derived-from(x, \\"sn:foo\\")').tokenize()
        if t.type is not TokenType.EOF
    ]
    string_tokens = [t for t in tokens if t.type is TokenType.STRING]
    assert len(string_tokens) == 1
    assert string_tokens[0].value == "sn:foo"
    assert tokens[-1].type is TokenType.PAREN_CLOSE


def test_xpath_parser_accepts_yang_escaped_quotes() -> None:
    for expression in [
        _SUB_NOTIF_WHEN_EXPR,
        'derived-from(../transport, \\"sn:configurable-encoding\\")',
        _IETF_SYSTEM_MUST_EXPR,
        '(. != \\"sys:radius\\" or ../../radius/server)',
    ]:
        XPathParser(expression).parse()


def test_parse_module_when_multiline_derived_from_ietf_sub_notif_pattern() -> None:
    yang = """
module example-sub-notif-when {
  yang-version 1.1;
  namespace "urn:example:sub-notif-when";
  prefix sn;

  container subscription-config {
    leaf transport { type string; }
    leaf encoding {
      when "not(../transport) or derived-from(../transport,
             \\"sn:configurable-encoding\\")";
      type string;
    }
  }
}
"""
    mod = parse_yang_string(yang)
    enc = mod.find_statement("subscription-config")
    assert enc is not None
    leaf = enc.find_statement("encoding")
    assert leaf is not None and leaf.when is not None
    assert "derived-from" in leaf.when.expression


def test_parse_module_must_ietf_system_radius_pattern() -> None:
    yang = """
module example-system-must {
  yang-version 1.1;
  namespace "urn:example:system-must";
  prefix sys;

  container authentication {
    container user-authentication-order {
      leaf user-authentication-order {
        type string;
        must "(. != \\"sys:radius\\" or ../../radius/server)";
      }
    }
    container radius {
      list server { key name; leaf name { type string; } }
    }
  }
}
"""
    mod = parse_yang_string(yang)
    leaf = mod.find_statement("authentication")
    assert leaf is not None


if __name__ == "__main__":  # pragma: no cover
    test_normalize_yang_escaped_quotes()
    test_xpath_tokenizer_string_literal_after_yang_escape()
    test_xpath_parser_accepts_yang_escaped_quotes()
    test_parse_module_when_multiline_derived_from_ietf_sub_notif_pattern()
    test_parse_module_must_ietf_system_radius_pattern()
    print("test_yang_escaped_quotes_in_xpath: ok")
