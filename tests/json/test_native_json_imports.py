"""#158: the native JSON form carries the imported identities it needs, and fails loudly otherwise."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from xyang.json import generate_json_schema, parse_json_schema

CASES = Path(__file__).resolve().parent.parent / "cases" / "modules"
FORMS = [CASES / "json-form-imported-identity-augment", CASES / "json-form-identity-alias"]


def _pointer(doc, ref):
    node = doc
    for part in ref.removeprefix("#/").split("/"):
        node = node[part]
    return node


def _refs(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref":
                yield value
            else:
                yield from _refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _refs(item)


@pytest.mark.parametrize("case", FORMS, ids=lambda p: p.name)
def test_form_is_self_contained_and_reversible(case):
    form = json.loads((case / "expected.yang.json").read_text())
    refs = list(_refs(form["properties"]))
    assert refs
    for ref in refs:
        assert _pointer(form, ref)["x-yang"]["type"] == "identity", f"dangling {ref}"
    assert generate_json_schema(parse_json_schema(form)) == form


def test_unrepresentable_augment_fails_convert_without_writing(tmp_path):
    case = CASES / "json-form-foreign-augment"
    out = tmp_path / "m.yang.json"
    proc = subprocess.run(
        [sys.executable, "-m", "xyang", "convert", "--include-path", str(case), str(case / "m.yang"), "-o", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "augment '/b:top'" in proc.stderr
    assert not out.exists()
