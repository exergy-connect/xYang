"""#161: extension definitions and invocations survive the native JSON form."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from xyang import YangValidator
from xyang.ast import YangChoiceStmt, YangExtensionInvocationStmt
from xyang.errors import YangExportError
from xyang.ext import ExtensionIdentity, ensure_builtin_extensions_loaded, register_extension_apply_callback
from xyang.ext.capabilities import apply_extension_invocations
from xyang.json import generate_json_schema, parse_json_schema
from xyang.parser.yang_parser import YangParser
from xyang.validator.document_validator import DocumentValidator

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


def test_rfc8791_structure_convert_round_trips(tmp_path):
    """#164 removed the #162 refusal: convert writes the structure and reloads it."""
    out = tmp_path / "m.yang.json"
    proc = subprocess.run(
        [sys.executable, "-m", "xyang", "convert", "--include-path", str(RFC), str(RFC / "m.yang"), "-o", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    written = json.loads(out.read_text())
    assert written == json.loads((RFC / "expected.yang.json").read_text())
    loaded = parse_json_schema(written)
    assert generate_json_schema(loaded) == written
    index = loaded.extension_runtime["ietf-yang-structure-ext:structure-index"]
    assert set(index) == {"msg"}


def test_cross_module_augment_structure_reloads_once():
    """#164: the imported structure stub receives the augment once, and a second apply does not repeat it."""
    case = RFC.parent / "json-form-augment-structure-cross-164"
    yang = YangParser(expand_uses=False, include_path=(case,)).parse_file(case / "m.yang")
    form = generate_json_schema(yang)
    loaded = parse_json_schema(form)
    assert generate_json_schema(loaded) == form

    def extras(module):
        stub = module.import_prefixes["b"]
        msg = stub.extension_runtime["ietf-yang-structure-ext:structure-index"]["msg"]
        box = next(child for child in msg.statements if child.name == "box")
        return msg, [child for child in box.statements if child.name == "extra"]

    msg, found = extras(loaded)
    assert len(found) == 1
    assert DocumentValidator(msg, enabled_features_by_module=None).validate({"box": {"id": "a", "extra": ""}})
    apply_extension_invocations(loaded)
    assert len(extras(loaded)[1]) == 1


def test_reloaded_augment_structure_if_feature_matches_the_yang_module():
    """#164: if-feature merged onto an augment-structure root is enforced after reload."""
    case = RFC.parent / "json-form-augment-structure-164"
    yang = YangParser(include_path=(case,)).parse_file(case / "m.yang")
    loaded = parse_json_schema(generate_json_schema(YangParser(expand_uses=False, include_path=(case,)).parse_file(case / "m.yang")))
    data = {"m:msg": {"enabled": "on", "extra-leaf": "z", "box": {"note": "hi"}}}
    for module in (yang, loaded):
        result = YangValidator(module, enabled_features_by_module={"m": []}).validate_detailed(data)
        assert [(e["code"], e["path"]) for e in result["errors"]] == [("if-feature", "/m:msg/extra-leaf")]


def test_other_apply_callback_still_fails_export(tmp_path):
    """#164: only RFC 8791 is exported. Another extension with an apply callback still fails."""
    ensure_builtin_extensions_loaded()
    register_extension_apply_callback(ExtensionIdentity("marked", "mark"), lambda invocation, _module: invocation)
    demo = tmp_path / "marked.yang"
    demo.write_text(
        """
module marked {
  yang-version 1.1;
  namespace "urn:marked";
  prefix m;
  extension mark { argument value; }
  m:mark "x";
}
""",
        encoding="utf-8",
    )
    module = YangParser(expand_uses=False).parse_file(demo)
    with pytest.raises(YangExportError, match="marked:mark"):
        generate_json_schema(module)
