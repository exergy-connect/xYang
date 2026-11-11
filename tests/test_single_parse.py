"""YANG XPath expressions are tokenized during parse and reused during validation."""

from collections import defaultdict
from unittest.mock import patch

from xyang import parse_yang_string, YangValidator


def test_yang_expressions_parsed_once():
    parse_phase_count = defaultdict(int)
    validation_phase_count = defaultdict(int)
    original_tokenize = None
    yang_parsing_complete = False

    def tracked_tokenize(self):
        expr = getattr(self, "expression", "unknown")
        if yang_parsing_complete:
            validation_phase_count[expr] += 1
        else:
            parse_phase_count[expr] += 1
        return original_tokenize(self)

    yang_content = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";

  container data {
    leaf name {
      type string;
      must "string-length(.) > 0";
      must "string-length(.) <= 64";
    }

    leaf count {
      type uint8;
      must ". >= 0";
      must ". <= 255";
    }

    leaf status {
      type string;
      when "../count > 0";
      must ". != ''";
    }

    list items {
      key "id";
      leaf id {
        type string;
        must "string-length(.) > 0";
      }
      leaf value {
        type uint8;
        must ". >= 0";
      }
    }
  }
}
"""

    from xyang.xpath.tokenizer import XPathTokenizer

    original_tokenize = XPathTokenizer.tokenize

    with patch.object(XPathTokenizer, "tokenize", tracked_tokenize):
        module = parse_yang_string(yang_content)
        yang_parsing_complete = True
        validator = YangValidator(module)
        test_data = {
            "data": {
                "name": "test",
                "count": 10,
                "status": "active",
                "items": [
                    {"id": "item1", "value": 5},
                    {"id": "item2", "value": 10},
                ],
            }
        }
        for _ in range(3):
            is_valid, errors, _warnings = validator.validate(test_data)
            assert is_valid, f"Validation failed: {errors}"

    assert len(validation_phase_count) == 0, (
        f"Found {len(validation_phase_count)} expressions tokenized during validation. "
        f"Expressions: {list(validation_phase_count.keys())}"
    )

    expected_expressions = {
        "string-length(.) > 0",
        "string-length(.) <= 64",
        ". >= 0",
        ". <= 255",
        "../count > 0",
        ". != ''",
    }
    parsed_expressions = set(parse_phase_count.keys())
    for expected in expected_expressions:
        assert expected in parsed_expressions, (
            f"Expected expression '{expected}' was not tokenized during YANG parsing"
        )
