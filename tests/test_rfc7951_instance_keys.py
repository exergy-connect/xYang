"""RFC 7951 instance member names (local vs module-qualified)."""

from __future__ import annotations

from pathlib import Path

from xyang.encoding.rfc7951 import instance_member_keys
from xyang.parser import YangParser


def test_augmented_leaf_uses_qualified_key(tmp_path: Path) -> None:
    (tmp_path / "lib.yang").write_text(
        """
module lib {
  yang-version 1.1;
  namespace "urn:lib";
  prefix l;
  container root { leaf x { type string; } }
}
""",
        encoding="utf-8",
    )
    (tmp_path / "main.yang").write_text(
        """
module main {
  yang-version 1.1;
  namespace "urn:main";
  prefix m;
  import lib { prefix l; }
  augment "/l:root" { leaf y { type string; } }
}
""",
        encoding="utf-8",
    )
    main = YangParser(expand_uses=True).parse_file(tmp_path / "main.yang")
    lib = main.import_prefixes["l"]
    y = lib.find_statement("root").find_statement("y")
    assert y is not None
    assert instance_member_keys(y, "lib") == {"main:y"}
