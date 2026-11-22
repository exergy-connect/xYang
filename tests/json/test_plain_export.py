import json
import subprocess
import sys

import pytest

from xyang import generate_json_schema, parse_json_schema, parse_yang_string

MODULE = '''module p { namespace "urn:p"; prefix p;
  typedef amount { type decimal64 { fraction-digits 2; } description "Money."; }
  container top {
    leaf x-tag { type string; description "Named like an extension keyword."; }
    leaf price { type amount; }
    leaf kind { type enumeration { enum a; enum b; } }
    list items { key "id"; leaf id { type uint8; } }
  }
}'''


def keywords(value, names=False):
    """Every object key that is a schema keyword, skipping data-name maps."""
    found = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if not names:
                found.add(key)
            found |= keywords(child, not names and key in {"properties", "patternProperties", "$defs", "dependentSchemas"})
    elif isinstance(value, list):
        for child in value:
            found |= keywords(child)
    return found


def test_plain_export_omits_xyang_keywords_and_keeps_the_schema():
    module = parse_yang_string(MODULE)
    full = generate_json_schema(module).schema
    plain = generate_json_schema(module, x_yang=False).schema
    assert "x-yang" in keywords(full)
    assert not {key for key in keywords(plain) if key.startswith("x-")}
    top = plain["properties"]["top"]
    assert top["properties"]["x-tag"]["description"] == "Named like an extension keyword."
    assert top["properties"]["kind"]["enum"] == ["a", "b"]
    assert plain["$defs"]["amount"]["description"] == "Money."
    assert top["properties"]["items"]["type"] == "array"
    # The annotated export is unchanged.
    assert generate_json_schema(module).schema == full


def test_plain_subtree_export_is_projected_before_annotations_are_removed():
    module = parse_yang_string(MODULE)
    annotated = generate_json_schema(module, path="/p:top/p:items")
    plain = generate_json_schema(module, path="/p:top/p:items", x_yang=False)
    assert plain.diagnostics == annotated.diagnostics
    assert plain.schema["type"] == "array"
    assert not {key for key in keywords(plain.schema) if key.startswith("x-")}


def test_plain_export_cannot_be_read_back_as_yang():
    plain = generate_json_schema(parse_yang_string(MODULE), x_yang=False).schema
    with pytest.raises(Exception):
        parse_json_schema(plain)


def test_convert_no_x_yang(tmp_path):
    source = tmp_path / "p.yang"
    source.write_text(MODULE, encoding="utf-8")
    out = tmp_path / "p.schema.json"
    subprocess.run([sys.executable, "-m", "xyang", "convert", "--no-x-yang", str(source), "-o", str(out)],
                   check=True, capture_output=True, text=True)
    assert "x-yang" not in keywords(json.loads(out.read_text(encoding="utf-8")))
