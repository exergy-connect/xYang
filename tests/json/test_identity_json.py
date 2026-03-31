"""JSON Schema round-trip for identity / identityref."""

from pathlib import Path

import pytest

from xyang.json import generate_json_schema, parse_json_schema

_EXAMPLES = Path(__file__).resolve().parent.parent.parent / "examples"
MINIMAL_YANG = _EXAMPLES / "identity_roundtrip.yang"


@pytest.fixture(scope="module")
def identity_module():
    from xyang import parse_yang_file

    if not MINIMAL_YANG.exists():
        pytest.skip("identity_roundtrip.yang not found")
    return parse_yang_file(str(MINIMAL_YANG))


def test_generate_json_schema_has_identity_defs_and_identityref_leaf(identity_module):
    data = generate_json_schema(identity_module)
    defs = data.get("$defs") or {}
    assert "animal" in defs
    assert defs["animal"].get("enum")
    assert defs["animal"].get("x-yang", {}).get("type") == "identity"
    assert "dog" in defs
    props = data.get("properties", {}).get("data", {})
    assert props.get("properties", {}).get("kind")


def test_parse_json_schema_roundtrip_restores_identities(identity_module):
    data = generate_json_schema(identity_module)
    back = parse_json_schema(data)
    assert "animal" in back.identities
    assert "dog" in back.identities
    assert back.identities["mammal"].bases == ["animal"]
    data_leaf = back.find_statement("data")
    assert data_leaf is not None
    kind = data_leaf.find_statement("kind")
    assert kind is not None and kind.type is not None
    assert kind.type.name == "identityref"
    assert kind.type.identityref_bases == ["animal"]
