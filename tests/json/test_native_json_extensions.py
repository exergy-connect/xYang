"""#161: extension definitions and invocations survive the native JSON form."""

import json
import subprocess
import sys
from pathlib import Path

from xyang.ast import YangChoiceStmt, YangExtensionInvocationStmt
from xyang.json import generate_json_schema, parse_json_schema
from xyang.parser.yang_parser import YangParser

CASE = Path(__file__).resolve().parent.parent / "cases" / "modules" / "json-form-extensions-161"
RFC = Path(__file__).resolve().parent.parent / "cases" / "modules" / "json-form-rfc8791-extension-161"


def _body(inv: YangExtensionInvocationStmt) -> tuple:
    out = []
    for child in inv.statements:
        if isinstance(child, YangExtensionInvocationStmt):
            out.append(("ext", child.name, child.argument))
        else:
            out.append(("node", type(child).__name__, child.name))
    return tuple(out)


def _by_owner(module) -> dict:
    found: dict = {}

    def walk(owner, path: str) -> None:
        items = []
        for stmt in getattr(owner, "statements", []) or []:
            if isinstance(stmt, YangExtensionInvocationStmt):
                items.append((stmt.name, stmt.argument, stmt.description, _body(stmt)))
        if items:
            found[path] = items
        for stmt in getattr(owner, "statements", []) or []:
            if not isinstance(stmt, YangExtensionInvocationStmt):
                walk(stmt, f"{path}/{getattr(stmt, 'name', type(stmt).__name__)}")
        if isinstance(owner, YangChoiceStmt):
            for case in owner.cases:
                walk(case, f"{path}/{case.name}")

    walk(module, "")
    for name, typedef in module.typedefs.items():
        walk(typedef, f"$typedef/{name}")
    for name, identity in module.identities.items():
        walk(identity, f"$identity/{name}")
    return found


def _defs(module) -> dict:
    return {
        name: (ext.argument_name, ext.argument_yin_element, ext.description, ext.reference)
        for name, ext in module.extensions.items()
    }


def test_reloaded_extensions_match_the_yang_module_and_round_trip():
    yang = YangParser(expand_uses=False, include_path=(CASE,)).parse_file(CASE / "m.yang")
    form = generate_json_schema(yang)
    assert form == json.loads((CASE / "expected.yang.json").read_text())
    loaded = parse_json_schema(form)
    assert _defs(loaded) == _defs(yang)
    assert _by_owner(loaded) == _by_owner(yang)
    imported = loaded.import_prefixes["e"].extensions["tag"]
    assert (imported.argument_name, imported.description, imported.reference) == ("value", "Imported tag.", "ext")
    assert generate_json_schema(loaded) == form


def test_rfc8791_structure_fails_convert_without_writing(tmp_path):
    out = tmp_path / "m.yang.json"
    proc = subprocess.run(
        [sys.executable, "-m", "xyang", "convert", "--include-path", str(RFC), str(RFC / "m.yang"), "-o", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "RFC 8791 sx:structure" in proc.stderr
    assert proc.stdout == ""
    assert not out.exists()
