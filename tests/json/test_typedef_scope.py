"""Native JSON's optional scope restriction on a global typedef."""

import pytest

from xyang.json import generate_json_schema, parse_json_schema


def schema_for(context, scope, kind="leaf"):
    definition = {"type": "string", "x-yang": {}}
    if scope is not ...:
        definition["x-yang"]["scope"] = scope
    ref = {"$ref": "#/$defs/code"}
    leaf = {**ref, "x-yang": {"type": "leaf"}}
    if kind == "leaf-list":
        leaf = {"type": "array", "items": ref, "x-yang": {"type": "leaf-list"}}
    elif kind == "union":
        leaf = {"oneOf": [ref, {"type": "boolean"}], "x-yang": {"type": "leaf"}}
    props = {"value": leaf}
    for name in reversed(context):
        props = {name: {"type": "object", "properties": props, "x-yang": {"type": "container"}}}
    return {"x-yang": {"module": "m", "namespace": "urn:m", "prefix": "m"}, "$defs": {"code": definition}, "properties": props}


@pytest.mark.parametrize("context,scope,kind,allowed", [
    (("a",), "/a", "leaf", True),
    (("a~b",), "/a~0b", "leaf", True),
    (("a", "child"), "/a", "leaf", True),
    (("b",), "/a", "leaf", False),
    (("ab",), "/a", "leaf", False),
    ((), "/a", "leaf", False),
    (("b",), ..., "leaf", True),
    (("a",), "/a", "leaf-list", True),
    (("b",), "/a", "leaf-list", False),
    (("a",), "/a", "union", True),
    (("b",), "/a", "union", False),
])
def test_global_typedef_scope(context, scope, kind, allowed):
    schema = schema_for(context, scope, kind)
    if not allowed:
        with pytest.raises(Exception, match="Unknown typedef"):
            parse_json_schema(schema)
        return
    module = parse_json_schema(schema)
    exported = generate_json_schema(module)
    assert exported["$defs"]["code"].get("x-yang", {}).get("scope") == (None if scope is ... else scope)
    parse_json_schema(exported)


@pytest.mark.parametrize("scope", [None, 42, "", "a", "/a/", "/a//b", "/a~2b"])
def test_invalid_typedef_scope(scope):
    with pytest.raises(ValueError, match="typedef scope"):
        parse_json_schema(schema_for(("a",), scope))


def test_reexport_imported_scope_collisions():
    """Re-export must retain distinct keys for identical private names from two modules."""
    from pathlib import Path

    fixture = Path(__file__).parents[1] / "cases/types/typedef-scope-imported-collisions/expected.yang.json"
    import json

    first = generate_json_schema(parse_json_schema(fixture))
    assert first == json.loads(fixture.read_text())
    second = generate_json_schema(parse_json_schema(first))
    assert first == second
    a_ref = second["properties"]["a"]["properties"]["value"]["$ref"]
    b_ref = second["properties"]["b"]["properties"]["value"]["$ref"]
    assert a_ref != b_ref
