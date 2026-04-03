"""
Nested mandatory choice directly under an outer choice case (no wrapper container).

YANG has no instance nodes for ``choice`` / ``case``; leaves from the active inner
case appear as siblings of other outer-case data under the same parent (e.g. xFrame
``open-type`` + ``primitive-type-and-enum``). xyang currently fails to match the
outer case when only inner leaves are present — this module locks that in.

Invalid trees (two inner cases, or inner + conflicting outer case, or ``primitive``
+ leaf-list ``enum`` like the meta-model) must be rejected; see
``test_flat_inner_*_invalid`` and ``test_flat_inner_primitive_and_enum_list_invalid``.
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


def test_flat_inner_both_branches_invalid(validator):
    """RFC 7950 §7.9: inner ``choice inner`` — at most one case; ``primitive`` and ``other`` together is invalid."""
    ok, errors, _ = validator.validate(
        {"root": {"primitive": "a", "other": "b"}}
    )
    assert not ok, (
        "expected validation failure when both inner choice cases have data under the same parent"
    )
    assert errors, f"expected errors, got: {errors!r}"
    joined = " ".join(errors).lower()
    assert "only one case" in joined or "multiple cases" in joined, (
        f"expected multi-branch choice error in: {errors!r}"
    )


def test_flat_inner_and_outer_alt_invalid(validator):
    """Cannot satisfy both ``inner_wrap`` (e.g. ``primitive``) and ``c_case`` (``alt``) on the same ``root``."""
    ok, errors, _ = validator.validate(
        {"root": {"primitive": "a", "alt": "z"}}
    )
    assert not ok, errors
    assert errors
    joined = " ".join(errors).lower()
    assert "only one case" in joined or "multiple cases" in joined
    assert "outer" in joined


# Meta-model-shaped sibling leaves: ``open-primitive`` vs ``closed-enum`` (leaf-list ``enum``).
YANG_NESTED_PRIMITIVE_OR_ENUM = """
module nested_primitive_or_enum {
  yang-version 1.1;
  namespace "urn:test:nested-primitive-or-enum";
  prefix "pe";

  container root {
    choice outer {
      mandatory true;
      case inner_wrap {
        choice inner {
          mandatory true;
          case open_primitive {
            leaf primitive {
              type string;
            }
          }
          case closed_enum {
            leaf-list enum {
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
def validator_primitive_or_enum():
    return YangValidator(parse_yang_string(YANG_NESTED_PRIMITIVE_OR_ENUM))


def test_flat_inner_primitive_and_enum_list_invalid(validator_primitive_or_enum):
    """Same rule as xFrame ``primitive-type-and-enum``: not both ``primitive`` and ``enum`` under one ``type``."""
    ok, errors, _ = validator_primitive_or_enum.validate(
        {"root": {"primitive": "string", "enum": ["G", "O"]}}
    )
    assert not ok, (
        "expected failure when open-primitive and closed-enum branches both have instance data"
    )
    assert errors
    joined = " ".join(errors).lower()
    assert "only one case" in joined or "multiple cases" in joined
