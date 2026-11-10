"""
Test for list key uniqueness.

YANG lists with a key statement require unique key values within the list.
Enforced by StructureValidator._validate_list.
"""
import pytest
from xyang import parse_yang_string
from xyang.errors import YangSemanticError


@pytest.mark.parametrize("illegal_stmt", ["when \"../enabled = 'true'\";", "if-feature \"f\";"])
def test_list_key_leaf_rejects_when_and_if_feature(illegal_stmt):
    """RFC 7950: ``when`` and ``if-feature`` are illegal on list key leaves."""
    yang = f"""
module test-list-key-condition {{
  yang-version 1.1;
  namespace "urn:test-list-key-condition";
  prefix "t";

  feature f;

  container root {{
    leaf enabled {{
      type boolean;
    }}
    list items {{
      key name;
      leaf name {{
        {illegal_stmt}
        type string;
      }}
      leaf value {{
        type string;
      }}
    }}
  }}
}}
"""
    with pytest.raises(YangSemanticError, match="key leaf|list key|list keys"):
        parse_yang_string(yang)


def test_list_key_rejects_non_existing_leaf():
    """RFC 7950: every name in a list ``key`` must refer to a child leaf."""
    yang = """
module test-list-missing-key {
  yang-version 1.1;
  namespace "urn:test-list-missing-key";
  prefix "t";

  container root {
    list items {
      key missing;
      leaf name {
        type string;
      }
    }
  }
}
"""
    with pytest.raises(YangSemanticError, match="key leaf|missing|not found|does not exist"):
        parse_yang_string(yang)
