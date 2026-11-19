import pytest
from xyang import generate_json_schema, parse_yang_string, parse_json_schema

@pytest.fixture(scope="module")
def module():
    return parse_yang_string('''module m { namespace "urn:m"; prefix m;
      feature f;
      typedef ext { type leafref { path "/m:outside/m:name"; } }
      container outside { leaf name { type string { length "2..8"; } } }
      container top {
        must "count(nodes) > 0";
        must "/m:outside/name = 'foo'";
        list nodes { key "name"; leaf name { type string; } }
        leaf via { type ext; }
        leaf other { type leafref { path "/m:outside/m:name"; } }
        leaf choice { if-feature f; mandatory true; type string; }
        leaf conditional { when "/m:outside/m:name = 'foo'"; type string; }
      }
    }''')

def test_descriptions_stay_on_the_schema_where_the_model_has_them():
    module = parse_yang_string('''module d { namespace "urn:d"; prefix d;
      typedef mac { type string; description "A MAC address."; }
      container top {
        leaf hw { type mac; }
        leaf labeled { type mac; description "Hardware address."; }
        leaf kind { type enumeration { enum init { description "Compiler initialization marker."; } enum run; } }
        leaf named { type string; description "The node name."; }
      }
    }''')
    full = generate_json_schema(module).schema
    kind = full["properties"]["top"]["properties"]["kind"]
    assert kind["x-yang"]["enums"][0] == {"name": "init", "description": "Compiler initialization marker."}
    assert kind["x-yang"]["enums"][1] == {"name": "run"}
    assert "description" not in kind
    assert full["$defs"]["mac"]["description"] == "A MAC address."
    restored = parse_json_schema(full)
    top = next(stmt for stmt in restored.statements if stmt.name == "top")
    restored_kind = next(stmt for stmt in top.statements if stmt.name == "kind")
    assert restored_kind.type.enum_descriptions["init"] == "Compiler initialization marker."
    schema = generate_json_schema(module, path="/d:top").schema
    assert schema["properties"]["hw"]["description"] == "A MAC address."
    assert schema["properties"]["labeled"]["description"] == "Hardware address."
    assert schema["properties"]["kind"]["description"] == "init: Compiler initialization marker."
    assert schema["properties"]["named"]["description"] == "The node name."
    assert schema["properties"]["kind"]["x-yang"]["enums"][0]["description"] == "Compiler initialization marker."

def test_projection_filters_external_constraints(module):
    result = generate_json_schema(module, path="/m:top")
    assert [d.constraint for d in result.diagnostics] == ["must", "leafref", "leafref", "when"]
    assert result.schema["properties"]["via"]["minLength"] == 2
    assert len(result.schema["x-yang"]["must"]) == 1
    with pytest.raises(ValueError, match="projection"):
        parse_json_schema(result.schema)

def test_disabled_enum_and_bit_values_leave_the_schema():
    module = parse_yang_string('''module e { yang-version 1.1; namespace "urn:e"; prefix e; feature f;
      typedef mode { type enumeration { enum basic; enum advanced { if-feature f; } } }
      container top { leaf mode { type mode; } leaf flags { type bits { bit read; bit write { if-feature f; } } } }
    }''')
    enabled = generate_json_schema(module, path="/e:top").schema
    assert enabled["$defs"]["mode"]["enum"] == ["basic", "advanced"]
    assert "write" in enabled["properties"]["flags"]["x-yang"]["bits"]
    disabled = generate_json_schema(module, path="/e:top", features={"e": set()}).schema
    assert disabled["$defs"]["mode"]["enum"] == ["basic"]
    assert "enums" not in disabled["$defs"]["mode"].get("x-yang", {})
    assert set(disabled["properties"]["flags"]["x-yang"]["bits"]) == {"read"}
    assert "write" not in disabled["properties"]["flags"]["pattern"]

def test_feature_filter(module):
    schema = generate_json_schema(module, path="/m:top", features={"m": set()}).schema
    assert "choice" not in schema["properties"]
    assert "choice" not in schema.get("required", [])
    assert "choice" in generate_json_schema(module, path="/m:top").schema["properties"]

def test_native_list_and_unknown_path(module):
    nodes = generate_json_schema(module, path="/m:top", native_json=True).schema["properties"]["nodes"]
    assert nodes["anyOf"][1]["additionalProperties"].get("required") == []
    with pytest.raises(ValueError, match="not found"):
        generate_json_schema(module, path="/m:missing")

def test_disabled_choice_branch():
    module = parse_yang_string('''module c { namespace "urn:c"; prefix c; feature f;
      container top { choice selection { case gated { if-feature f; leaf a { type string; } } case open { leaf b { type string; } } } }
    }''')
    schema = generate_json_schema(module, path="/c:top", features={"c": set()}).schema
    import json
    output = json.dumps(schema)
    assert '"a"' not in output
    assert '"b"' in output

def test_union_with_leafref_fails_loudly():
    module = parse_yang_string('''module u { namespace "urn:u"; prefix u;
      container top { leaf target { type string; } leaf value { type union {
        type leafref { path "../target"; } type string;
      } } }
    }''')
    with pytest.raises(ValueError, match="union containing a leafref"):
        generate_json_schema(module, path="/u:top")

def test_xsd_literal_anchors_export_as_valid_json_schema_pattern():
    import re
    module = parse_yang_string('''module p { namespace "urn:p"; prefix p;
      container top { leaf value { type string { pattern 'a$?'; } } }
    }''')
    pattern = generate_json_schema(module, path="/p:top").schema["properties"]["value"]["pattern"]
    assert re.fullmatch(pattern, "a")
    assert re.fullmatch(pattern, "a$")
    assert not re.fullmatch(pattern, "ab")

def test_disabled_choice_preserves_unconditional_siblings():
    module = parse_yang_string('''module c { namespace "urn:c"; prefix c; feature f;
      container top { leaf shared { type string; mandatory true; }
        choice selection { if-feature f; case gated { leaf a { type string; } } case other { leaf b { type string; } } }
      }
    }''')
    schema = generate_json_schema(module, path="/c:top", features={"c": set()}).schema
    assert set(schema["properties"]) == {"shared"}
    assert schema["required"] == ["shared"]

def test_disabled_leafref_target_keeps_resolved_type():
    module = parse_yang_string('''module r { namespace "urn:r"; prefix r; feature f;
      container top { leaf target { if-feature f; type uint32; } leaf ref { type leafref { path "../target"; } } }
    }''')
    result = generate_json_schema(module, path="/r:top", features={"r": set()})
    ref = result.schema["properties"]["ref"]
    assert ref["type"] == "integer"
    assert "path" not in ref["x-yang"]
    assert "disabled" in result.diagnostics[0].reason


def test_whole_module_returns_result_with_empty_diagnostics(module):
    result = generate_json_schema(module)
    assert result.schema["x-yang"]["module"] == "m"
    assert result.diagnostics == []

def test_imported_grouping_feature_context_fails_loudly(tmp_path):
    from xyang import parse_yang_file
    (tmp_path / "lib.yang").write_text('module lib { namespace "urn:lib"; prefix l; feature f; grouping g { leaf x { if-feature f; type string; } } }')
    (tmp_path / "main.yang").write_text('module main { namespace "urn:main"; prefix m; import lib { prefix l; } container top { uses l:g; } }')
    module = parse_yang_file(tmp_path / "main.yang")
    with pytest.raises(ValueError, match="unqualified if-feature"):
        generate_json_schema(module, path="/m:top")

def test_xsd_shorthand_fails_loudly_for_cross_runtime_parity():
    module = parse_yang_string(r'''module p { namespace "urn:p"; prefix p;
      container top { leaf value { type string { pattern '\d+'; } } }
    }''')
    with pytest.raises(ValueError, match="XSD regex"):
        generate_json_schema(module, path="/p:top")

def test_choice_shared_leafref_has_one_diagnostic():
    module = parse_yang_string('''module c { namespace "urn:c"; prefix c; feature f;
      container top { leaf target { if-feature f; type uint32; }
        leaf ref { type leafref { path "../target"; } }
        choice selection { case gated { if-feature f; leaf a { type string; } } case open { leaf b { type string; } } }
      }
    }''')
    result = generate_json_schema(module, path="/c:top", features={"c": set()})
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].reason == "target is disabled by feature selection"

def test_leafref_typedef_predicate_is_preserved_in_diagnostic():
    module = parse_yang_string('''module m { namespace "urn:m"; prefix m;
      list a { key name; leaf name { type string; } }
      typedef t { type leafref { path "/a[name = current()/../x]/name"; } }
      container top { leaf x { type string; } leaf v { type t; } }
    }''')
    result = generate_json_schema(module, path="/m:top")
    assert result.diagnostics[0].expression == "/a[name = current()/../x]/name"


def test_leafref_predicate_current_resolves_from_leaf_context():
    module = parse_yang_string('''module p { namespace "urn:p"; prefix p;
      container top {
        list nodes { key name; leaf name { type string; } leaf target { type string; } }
        list links { key index; leaf index { type uint32; } leaf node { type string; }
          leaf value { type leafref { path "/top/nodes[name = current()/../node]/target"; } }
        }
      }
    }''')
    assert not generate_json_schema(module, path="/p:top").diagnostics
    result = generate_json_schema(module, path="/p:top/links")
    assert result.diagnostics[0].expression == "/top/nodes[name = current()/../node]/target"
