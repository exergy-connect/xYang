"""
Parse tests for YANG import / include / submodule patterns from yangson docs example ex3.

Source: https://github.com/CZ-NIC/yangson/tree/master/docs/examples/ex3

``include`` loads the submodule file from the same directory as the main module (or
``YangParser(include_path=...)`` / ``parse_yang_file(..., include_path=...)``) and merges
typedefs, identities, groupings, and top-level statements into the parent module.

``yang-library-ex3.json`` is legacy ``modules-state`` instance data (RFC 7895-style).
``rfc8525-ex3.json`` is the NMDA ``yang-library`` shape (RFC 8525). Both are validated
against ``yang-library-ex3.yang``, a minimal ``ietf-yang-library`` stub (no imports or
leafrefs). Strip the JSON namespace prefix so the root key matches the container name
(``modules-state`` or ``yang-library``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xyang import YangValidator, parse_yang_file
from xyang.ast import YangAugmentStmt, YangLeafStmt
from xyang.errors import YangSyntaxError
from xyang.parser import YangParser

EX3_DIR = Path(__file__).resolve().parent / "data" / "yangson-ex3"

YANG_LIBRARY_SCHEMA = EX3_DIR / "yang-library-ex3.yang"


@pytest.fixture
def ietf_yang_library_module():
    assert YANG_LIBRARY_SCHEMA.is_file(), f"Missing {YANG_LIBRARY_SCHEMA}"
    return parse_yang_file(str(YANG_LIBRARY_SCHEMA))


@pytest.fixture
def parse_ex3() -> YangParser:
    return YangParser(expand_uses=False)


def test_example_3_a_parses(parse_ex3: YangParser) -> None:
    mod = parse_ex3.parse_file(EX3_DIR / "example-3-a@2017-08-01.yang")
    assert mod.name == "example-3-a"
    assert mod.namespace == "http://example.com/example-3/a"
    assert "gquux" in mod.groupings


def test_example_3_a_include_merges_grouping_and_expand_uses() -> None:
    mod = YangParser(expand_uses=True).parse_file(EX3_DIR / "example-3-a@2017-08-01.yang")
    assert "gquux" in mod.groupings
    top = mod.find_statement("top")
    assert top is not None
    names = {s.name for s in top.statements}
    assert "quux" in names
    assert "foo" in names


def test_example_3_b_parses_with_imports(parse_ex3: YangParser) -> None:
    mod = parse_ex3.parse_file(EX3_DIR / "example-3-b@2016-08-22.yang")
    assert mod.name == "example-3-b"
    augments = [s for s in mod.statements if isinstance(s, YangAugmentStmt)]
    assert len(augments) == 1
    assert augments[0].augment_path == "/ex3a:top"


def test_example_3_b_import_loads_modules_and_expands_prefixed_uses() -> None:
    mod = YangParser(expand_uses=True).parse_file(EX3_DIR / "example-3-b@2016-08-22.yang")
    assert set(mod.import_prefixes.keys()) == {"oin", "ex3a"}
    assert mod.import_prefixes["ex3a"].name == "example-3-a"
    assert mod.import_prefixes["oin"].name == "ietf-inet-types"
    assert not any(isinstance(s, YangAugmentStmt) for s in mod.statements)
    ex3a = mod.import_prefixes["ex3a"]
    top = ex3a.find_statement("top")
    assert top is not None
    names = {s.name for s in top.statements}
    assert "bar" in names
    assert "baz" in names


def test_example_3_a_merges_submodule_import_prefixes() -> None:
    """Submodule ``import`` entries are merged into the parent so ``inet:`` resolves."""
    mod = YangParser(expand_uses=True).parse_file(EX3_DIR / "example-3-a@2017-08-01.yang")
    assert "inet" in mod.import_prefixes
    assert mod.import_prefixes["inet"].name == "ietf-inet-types"
    assert not any(isinstance(s, YangAugmentStmt) for s in mod.statements)
    top = mod.find_statement("top")
    assert top is not None
    baz = top.find_statement("baz")
    assert isinstance(baz, YangLeafStmt)
    assert baz.type is not None
    assert baz.type.name == "inet:ipv4-address-no-zone"


def test_example_3_suba_parses_submodule(parse_ex3: YangParser) -> None:
    mod = parse_ex3.parse_file(EX3_DIR / "example-3-suba@2017-08-01.yang")
    assert mod.name == "example-3-suba"
    assert mod.belongs_to_module == "example-3-a"


def test_yang_library_ex3_json_validates(ietf_yang_library_module) -> None:
    """Legacy modules-state JSON (ex3) validates against yang-library-ex3.yang."""
    raw = json.loads((EX3_DIR / "yang-library-ex3.json").read_text(encoding="utf-8"))
    assert "ietf-yang-library:modules-state" in raw
    data = {"modules-state": raw["ietf-yang-library:modules-state"]}
    valid, errors, warnings = YangValidator(ietf_yang_library_module).validate(data)
    assert valid, f"expected valid instance, got errors={errors!r} warnings={warnings!r}"


def test_rfc8525_ex3_json_validates(ietf_yang_library_module) -> None:
    """RFC 8525 yang-library JSON validates against yang-library-ex3.yang."""
    raw = json.loads((EX3_DIR / "rfc8525-ex3.json").read_text(encoding="utf-8"))
    assert "ietf-yang-library:yang-library" in raw
    data = {"yang-library": raw["ietf-yang-library:yang-library"]}
    valid, errors, warnings = YangValidator(ietf_yang_library_module).validate(data)
    assert valid, f"expected valid instance, got errors={errors!r} warnings={warnings!r}"


def test_include_without_source_path_errors() -> None:
    src = """
module ex {
  yang-version 1.1;
  namespace "urn:ex";
  prefix ex;
  include other { }
}
"""
    with pytest.raises(YangSyntaxError, match="parse_file|source_path"):
        YangParser().parse_string(src)
