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
from xyang.xpath import Context, Node, XPathEvaluator, XPathParser


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
      leaf ref_abs_current_pred {
        type string;
        must "count(/top/items[current() = 1]) >= 0";
      }
    }
  }
}
"""


@pytest.fixture(scope="module")
def xpath_caching_module():
    """Single YANG module used by all caching tests."""
    return parse_yang_string(XPATH_CACHING_YANG)


@pytest.fixture
def validator_with_cache_stats(xpath_caching_module):
    """Validator with cache stats cleared before test and printed after."""
    validator = YangValidator(xpath_caching_module)
    validator._doc_validator._evaluator.clear_cache_stats()
    yield validator
    stats = validator._doc_validator._evaluator.get_cache_stats()
    print(f"\n  Cache stats: {stats}")


def test_absolute_cacheable_two_documents(validator_with_cache_stats):
    """Absolute path /top/flag = 1: cacheable. Doc1 flag=1 (valid), Doc2 flag=0 (invalid)."""
    validator = validator_with_cache_stats
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
    stats = validator._doc_validator._evaluator.get_cache_stats()
    assert stats["lookups"] == 2
    assert stats["hits"] == 1
    assert stats["purged"] == 0


def test_absolute_with_predicate_cacheable_two_documents(validator_with_cache_stats):
    """Absolute path with literal predicate /top/items[id=1]: cacheable. Doc1 has id=1 (valid), Doc2 does not (invalid)."""
    validator = validator_with_cache_stats
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
    stats = validator._doc_validator._evaluator.get_cache_stats()
    assert stats["lookups"] == 3
    assert stats["hits"] == 1
    assert stats["purged"] == 0


def test_relative_two_documents(validator_with_cache_stats):
    """Relative path ../../../flag = 1 on leaf ref_rel (context = leaf). Doc1 flag=1 (valid), Doc2 flag=0 (invalid)."""
    validator = validator_with_cache_stats
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
    stats = validator._doc_validator._evaluator.get_cache_stats()
    assert stats["lookups"] == 2
    assert stats["hits"] == 1
    assert stats["purged"] == 0


def test_absolute_with_relative_predicate_two_documents(validator_with_cache_stats):
    """Absolute path with relative predicate /top/items[../flag=1]: not cacheable. Doc1 flag=1 (valid), Doc2 flag=0 (invalid)."""
    validator = validator_with_cache_stats
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
    stats = validator._doc_validator._evaluator.get_cache_stats()
    # Trace with: pytest -s --log-cli-level=DEBUG -k test_absolute_with_relative_predicate
    # 3 lookups: #1 /top/items (miss), #2 ../flag (miss), #3 /top/items (hit from same validate)
    assert stats["lookups"] == 3
    assert stats["hits"] == 1
    assert stats["purged"] == 0


def test_absolute_with_current_two_documents(validator_with_cache_stats):
    """Leaf must current() = 1: context-dependent. Doc1 value 1 (valid), Doc2 value 2 (invalid)."""
    validator = validator_with_cache_stats
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
    stats = validator._doc_validator._evaluator.get_cache_stats()
    assert stats["lookups"] == 0, "current() does not use path cache"
    assert stats["hits"] == 0
    assert stats["purged"] == 0


def test_non_cacheable_path_purged(validator_with_cache_stats):
    """Path with current() in predicate is not cacheable; one entry is purged after eval."""
    validator = validator_with_cache_stats
    doc = {
        "top": {
            "flag": 0,
            "items": [{"id": 1, "ref_abs_current_pred": "ok"}],
        }
    }
    valid, errors, _ = validator.validate(doc)
    assert valid, errors
    stats = validator._doc_validator._evaluator.get_cache_stats()
    assert stats["lookups"] == 2
    assert stats["hits"] == 0
    assert stats["purged"] == 2


def test_local_expression_cache_hit(xpath_caching_module):
    """Same path evaluated twice in one expression (/top/flag = 1 and /top/flag = 1) yields a cache hit."""
    data = {"top": {"flag": 1}}
    root = Node(data, xpath_caching_module, None)
    ctx = Context(current=root, root=root, path_cache={})
    ev = XPathEvaluator()
    ev.clear_cache_stats()
    ast = XPathParser("/top/flag = 1 and /top/flag = 1").parse()
    result = ev.eval(ast, ctx, root)
    assert result is True
    stats = ev.get_cache_stats()
    assert stats["lookups"] == 2
    assert stats["hits"] == 1
    assert stats["purged"] == 0
    print(f"\n  Cache stats: {stats}")
