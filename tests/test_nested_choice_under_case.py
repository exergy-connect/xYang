"""
Nested mandatory choice directly under an outer choice case (no wrapper container).

YANG has no instance nodes for ``choice`` / ``case``; leaves from the active inner
case appear as siblings of other outer-case data under the same parent (e.g. xFrame
``open-type`` + ``primitive-type-and-enum``). xyang currently fails to match the
outer case when only inner leaves are present — this module locks that in.
"""

from __future__ import annotations

import pytest

from xyang import YangValidator, parse_yang_string

# Outer mandatory choice; one case holds only an inner mandatory choice (two leaves).
YANG_NESTED_UNDER_CASE = """
module nested_choice_under_case {
  yang-version 1.1;
  namespace "urn:test:nested-choice-under-case";
  prefix "nc";

  container root {
    choice outer {
      mandatory true;
      case inner_wrap {
        choice inner {
          mandatory true;
          case a_case {
            leaf primitive {
              type string;
            }
          }
          case b_case {
            leaf other {
              type string;
            }
          }
        }
      }
      case c_case {
        leaf alt {
          type string;
        }
      }
    }
  }
}
"""


@pytest.fixture
def module():
    return parse_yang_string(YANG_NESTED_UNDER_CASE)


@pytest.fixture
def validator(module):
    return YangValidator(module)


def test_outer_leaf_branch_still_validates(validator):
    """Sibling outer case with a single leaf — already works."""
    ok, errors, _ = validator.validate({"root": {"alt": "z"}})
    assert ok, errors


def test_flat_inner_primitive_should_validate(validator):
    """Instance uses ``primitive`` only; no key for ``inner`` or ``outer`` choices."""
    ok, errors, _ = validator.validate({"root": {"primitive": "hello"}})
    assert ok, errors


def test_flat_inner_other_should_validate(validator):
    ok, errors, _ = validator.validate({"root": {"other": "y"}})
    assert ok, errors
