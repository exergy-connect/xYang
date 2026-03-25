"""
Standalone xYang test for YANG modules that contain nested uses statements.

Defines a minimal YANG module with nested grouping/uses (grouping A uses B,
B uses C) and checks that xYang parses it and can validate data against it.
"""
from __future__ import annotations

import pytest

from xyang import parse_yang_string, YangValidator
from xyang.errors import YangCircularUsesError


# Standalone YANG module with nested uses: outer uses middle, middle uses inner.
YANG_NESTED_USES = """
module nested_uses {
  yang-version 1.1;
  namespace "urn:test:nested-uses";
  prefix "nu";

  grouping inner {
    leaf x {
      type string;
      description "From inner grouping";
    }
  }

  grouping middle {
    uses inner;
    leaf y {
      type string;
      description "From middle grouping";
    }
  }

  grouping outer {
    uses middle;
    leaf z {
      type string;
      description "From outer grouping";
    }
  }

  container root {
    description "Root container that uses the nested grouping chain";
    uses outer;
  }
}
"""

# Refine targets list ``L`` behind ``uses list_g``; path includes choice ``outer_ch`` then case ``oc``.
YANG_REFINE_NESTED_LIST_PATH = """
module refine_nested_list_path {
  yang-version 1.1;
  namespace "urn:test:refine-nested-list-path";
  prefix "rnlp";

  grouping list_g {
    list L {
      key k;
      leaf k {
        type string;
      }
    }
  }

  grouping base_g {
    choice outer_ch {
      case oc {
        uses list_g;
      }
    }
  }

  grouping refined_g {
    uses base_g {
      refine outer_ch/oc/L {
        max-elements 0;
        min-elements 0;
      }
    }
  }

  container root {
    uses refined_g;
  }
}
"""

# Same cyclic shape as ``core``/``loop_back``; ``loop_back`` refines ``hold`` to
# ``max-elements 0`` / ``min-elements 0`` (cardinality only; does not affect compile-time
# ``uses`` expansion).
YANG_USES_CYCLE_BROKEN_BY_REFINE_ON_LIST = """
module uses_cycle_broken_by_refine {
  yang-version 1.1;
  namespace "urn:test:uses-cycle-broken-by-refine";
  prefix "ucbr";

  grouping sink {
    leaf ok { type string; }
  }

  grouping core {
    choice branch {
      case escape {
        uses sink;
      }
      case recurse {
        list hold {
          key id;
          leaf id { type string; }
          uses loop_back;
        }
      }
    }
  }

  grouping loop_back {
    uses core {
      refine branch/recurse/hold {
        max-elements 0;
        min-elements 0;
      }
    }
  }

  container root {
    uses loop_back;
  }
}
"""


def test_parse_nested_uses_module():
    """xYang parses a YANG module that contains nested uses statements."""
    module = parse_yang_string(YANG_NESTED_USES)
    assert module.name == "nested_uses"
    assert module.yang_version == "1.1"
    root = module.find_statement("root")
    assert root is not None


def test_validate_data_against_nested_uses():
    """xYang validates data against a schema built from nested uses."""
    module = parse_yang_string(YANG_NESTED_USES)
    validator = YangValidator(module)
    data = {"root": {"x": "a", "y": "b", "z": "c"}}
    is_valid, errors, _ = validator.validate(data)
    assert is_valid, errors


def test_parse_refine_targets_list_behind_uses():
    """Refine path reaches a list that lives under a nested ``uses`` (not yet expanded)."""
    module = parse_yang_string(YANG_REFINE_NESTED_LIST_PATH)
    assert module.name == "refine_nested_list_path"
    root = module.find_statement("root")
    assert root is not None


def test_parse_uses_cycle_through_list_raises_circular_uses():
    """Recursive ``uses`` through a list expands fully; list cardinality refine does not cut the cycle."""
    with pytest.raises(YangCircularUsesError) as exc:
        parse_yang_string(YANG_USES_CYCLE_BROKEN_BY_REFINE_ON_LIST)
    assert "loop_back" in str(exc.value)
