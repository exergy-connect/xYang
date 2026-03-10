"""
Minimal test for leaf must with relative path ../../flag = 1.

Per spec, the context node for a leaf's must is the leaf itself.
From ref_rel leaf: .. = items entry, ../.. = top, ../../flag = top/flag.
"""

import pytest
from xyang import parse_yang_string, YangValidator


YANG = """
module test {
  yang-version 1.1;
  namespace "urn:test";
  prefix "t";
  container top {
    leaf flag {
      type int32;
      default 0;
    }
    list items {
      key id;
      leaf id { type int32; }
      leaf ref_rel {
        type string;
        must "../../flag = 1";
      }
    }
  }
}
"""


def test_leaf_must_relative_path_valid():
    """must "../../flag = 1" on leaf ref_rel: valid when top/flag = 1.
    From ref_rel: .. = items entry, ../.. = top."""
    module = parse_yang_string(YANG)
    validator = YangValidator(module)
    data = {
        "top": {
            "flag": 1,
            "items": [{"id": 1, "ref_rel": "ok"}],
        }
    }
    is_valid, errors, _ = validator.validate(data)
    assert is_valid, errors


def test_leaf_must_relative_path_invalid():
    """must "../../flag = 1" on leaf ref_rel: invalid when top/flag = 0."""
    module = parse_yang_string(YANG)
    validator = YangValidator(module)
    data = {
        "top": {
            "flag": 0,
            "items": [{"id": 1, "ref_rel": "bad"}],
        }
    }
    is_valid, errors, _ = validator.validate(data)
    assert not is_valid
    assert any("ref_rel" in str(e) for e in errors)
