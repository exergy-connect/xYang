"""Post-parse pass order: uses, then augment, then RFC 8791 extensions (only when expand_uses)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from xyang.parser import YangParser

EXT = (
    Path(__file__).resolve().parents[1]
    / "examples/ietf-yang-push/modules/ietf-yang-structure-ext@2020-06-17.yang"
)
INDEX = "ietf-yang-structure-ext:structure-index"

YANG = """
module m {
  yang-version 1.1;
  namespace "urn:m";
  prefix m;
  import ietf-yang-structure-ext { prefix sx; }
  grouping g { leaf n { type uint8; } }
  sx:structure msg { uses g; }
}
"""


def _parse(expand_uses: bool):
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        shutil.copy(EXT, dest / EXT.name)
        source = dest / "m.yang"
        source.write_text(YANG, encoding="utf-8")
        return YangParser(expand_uses=expand_uses).parse_file(source)


def test_structure_index_sees_expanded_uses() -> None:
    mod = _parse(True)
    msg = mod.extension_runtime[INDEX]["msg"]
    names = [getattr(child, "name", None) for child in msg.statements]
    kinds = [type(child).__name__ for child in msg.statements]
    assert "n" in names
    assert "YangLeafStmt" in kinds
    assert "YangUsesStmt" not in kinds


def test_structure_index_absent_without_expand_uses() -> None:
    mod = _parse(False)
    assert not mod.extension_runtime.get(INDEX)
