"""Refine targets must exist under the used grouping (RFC 7950-style)."""

from __future__ import annotations

import pytest

from xyang import YangRefineTargetNotFoundError, parse_yang_string


def test_refine_bad_path_raises():
    yang = """
module t {
  yang-version 1.1;
  namespace "urn:test:t";
  prefix "t";
  grouping g {
    leaf a { type string; }
  }
  container c {
    uses g {
      refine does_not_exist {
        description "x";
      }
    }
  }
}
"""
    with pytest.raises(YangRefineTargetNotFoundError) as exc_info:
        parse_yang_string(yang)
    assert "does_not_exist" in str(exc_info.value)


def test_refine_min_elements_bad_path_raises():
    yang = """
module t2 {
  yang-version 1.1;
  namespace "urn:test:t2";
  prefix "t";
  grouping g {
    leaf a { type string; }
  }
  container c {
    uses g {
      refine missing/list {
        max-elements 0;
      }
    }
  }
}
"""
    with pytest.raises(YangRefineTargetNotFoundError) as exc_info:
        parse_yang_string(yang)
    assert "missing/list" in exc_info.value.target_path
