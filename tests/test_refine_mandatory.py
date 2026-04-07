"""RFC 7950 §7.13.2: mandatory substatement inside refine."""

from xyang.parser.yang_parser import YangParser
from xyang.ast import YangLeafStmt


def test_refine_mandatory_false_on_grouping_leaf():
    yang = """
module t {
  namespace "urn:test:r";
  prefix "r";
  grouping g {
    leaf entity {
      type string;
      mandatory true;
    }
  }
  container c {
    uses g {
      refine entity {
        mandatory false;
      }
    }
  }
}
"""
    mod = YangParser(expand_uses=True).parse_string(yang)
    container = mod.statements[0]
    leaf = container.statements[0]
    assert isinstance(leaf, YangLeafStmt)
    assert leaf.name == "entity"
    assert leaf.mandatory is False
