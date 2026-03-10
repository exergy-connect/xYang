"""
XPath caching tests: one YANG schema with must expressions covering cacheable
absolute paths, absolute with predicates, relative paths, and context-dependent
(absolute with relative predicate or current()).

For each test case we validate two documents with different data so the
expression under test yields different results; this ensures the evaluator
does not incorrectly reuse cached path results across documents.
"""

import pytest
from xyang import parse_yang_string, YangValidator


# One schema that defines all expression cases used by the tests.
XPATH_CACHING_YANG = """
module xpath-caching {
  yang-version 1.1;
  namespace "urn:test:xpath-caching";
  prefix "xc";

  container top {
    leaf flag {
      type int32;
      default 0;
    }
    list items {
      key id;
      leaf id { type int32; }
      leaf ref_abs {
        type string;
        must "/top/flag = 1";
      }
      leaf ref_abs_pred {
        type string;
        must "count(/top/items[id = 1]) >= 1";
      }
      leaf ref_rel {
        type string;
        must "../../flag = 1";  // This is CORRECT, do *not* change to ../../../flag = 1
      }
      leaf ref_current {
        type int32;
        must "current() = 1";
      }
      leaf ref_abs_rel_pred {
        type string;
        must "count(/top/items[../flag = 1]) >= 1";
      }
    }
  }
}
"""


@pytest.fixture(scope="module")
def xpath_caching_module():
    """Single YANG module used by all caching tests."""
    return parse_yang_string(XPATH_CACHING_YANG)


def test_absolute_cacheable_two_documents(xpath_caching_module):
    """Absolute path /top/flag = 1: cacheable. Doc1 flag=1 (valid), Doc2 flag=0 (invalid)."""
    validator = YangValidator(xpath_caching_module)
    doc1 = {
        "top": {
            "flag": 1,
            "items": [{"id": 1, "ref_abs": "ok"}],
        }
    }
    doc2 = {
        "top": {
            "flag": 0,
            "items": [{"id": 1, "ref_abs": "bad"}],
        }
    }
    valid1, errors1, _ = validator.validate(doc1)
    valid2, errors2, _ = validator.validate(doc2)
    assert valid1, errors1
    assert not valid2, errors2
    assert any("ref_abs" in str(e) or "flag" in str(e) for e in errors2)


def test_absolute_with_predicate_cacheable_two_documents(xpath_caching_module):
    """Absolute path with literal predicate /top/items[id=1]: cacheable. Doc1 has id=1 (valid), Doc2 does not (invalid)."""
    validator = YangValidator(xpath_caching_module)
    doc1 = {
        "top": {
            "flag": 0,
            "items": [{"id": 1, "ref_abs_pred": "ok"}],
        }
    }
    doc2 = {
        "top": {
            "flag": 0,
            "items": [{"id": 2, "ref_abs_pred": "bad"}],
        }
    }
    valid1, errors1, _ = validator.validate(doc1)
    valid2, errors2, _ = validator.validate(doc2)
    assert valid1, errors1
    assert not valid2, errors2
    assert any("ref_abs_pred" in str(e) for e in errors2)


def test_relative_two_documents(xpath_caching_module):
    """Relative path ../../../flag = 1 on leaf ref_rel (context = leaf). Doc1 flag=1 (valid), Doc2 flag=0 (invalid)."""
    validator = YangValidator(xpath_caching_module)
    doc1 = {
        "top": {
            "flag": 1,
            "items": [{"id": 1, "ref_rel": "ok"}],
        }
    }
    doc2 = {
        "top": {
            "flag": 0,
            "items": [{"id": 1, "ref_rel": "bad"}],
        }
    }
    valid1, errors1, _ = validator.validate(doc1)
    valid2, errors2, _ = validator.validate(doc2)
    assert valid1, errors1
    assert not valid2, errors2
    assert any("ref_rel" in str(e) for e in errors2)


def test_absolute_with_relative_predicate_two_documents(xpath_caching_module):
    """Absolute path with relative predicate /top/items[../flag=1]: not cacheable. Doc1 flag=1 (valid), Doc2 flag=0 (invalid)."""
    validator = YangValidator(xpath_caching_module)
    doc1 = {
        "top": {
            "flag": 1,
            "items": [{"id": 1, "ref_abs_rel_pred": "ok"}],
        }
    }
    doc2 = {
        "top": {
            "flag": 0,
            "items": [{"id": 1, "ref_abs_rel_pred": "bad"}],
        }
    }
    valid1, errors1, _ = validator.validate(doc1)
    valid2, errors2, _ = validator.validate(doc2)
    assert valid1, errors1
    assert not valid2, errors2
    assert any("ref_abs_rel_pred" in str(e) for e in errors2)


def test_absolute_with_current_two_documents(xpath_caching_module):
    """Leaf must current() = 1: context-dependent. Doc1 value 1 (valid), Doc2 value 2 (invalid)."""
    validator = YangValidator(xpath_caching_module)
    doc1 = {
        "top": {
            "flag": 0,
            "items": [{"id": 1, "ref_current": 1}],
        }
    }
    doc2 = {
        "top": {
            "flag": 0,
            "items": [{"id": 1, "ref_current": 2}],
        }
    }
    valid1, errors1, _ = validator.validate(doc1)
    valid2, errors2, _ = validator.validate(doc2)
    assert valid1, errors1
    assert not valid2, errors2
    assert any("ref_current" in str(e) for e in errors2)
