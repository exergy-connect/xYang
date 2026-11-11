"""RFC 7950 ``augment`` substatement of ``uses`` (§7.17).

Expanded merge validation lives in ``tests/cases/reuse/uses-augment``.
"""

from __future__ import annotations

from xyang.ast import YangUsesStmt
from xyang.refine_expand import copy_yang_statement


def test_uses_augment_parsed_on_stmt():
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  grouping g { container a { } }
  grouping u {
    uses g {
      augment "a" { leaf x { type string; } }
    }
  }
}
"""
    from xyang.parser import YangParser

    mod = YangParser(expand_uses=False).parse_string(yang)
    u = mod.groupings["u"]
    uses = next(s for s in u.statements if isinstance(s, YangUsesStmt))
    assert len(uses.augmentations) == 1
    assert uses.augmentations[0].augment_path == "a"


def test_copy_yang_statement_augment():
    yang = """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  grouping g { container a { } }
  grouping u {
    uses g {
      augment "a" { leaf x { type string; } }
    }
  }
}
"""
    from xyang.parser import YangParser

    mod = YangParser(expand_uses=False).parse_string(yang)
    uses = next(s for s in mod.groupings["u"].statements if isinstance(s, YangUsesStmt))
    aug = uses.augmentations[0]
    copied = copy_yang_statement(aug)
    assert copied is not aug
    assert copied.augment_path == aug.augment_path
    assert len(copied.statements) == 1
    assert copied.statements[0] is not aug.statements[0]
