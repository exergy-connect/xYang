import pytest
from xyang import infer_required_features, parse_yang_string

SOURCE = '''module example {
 yang-version 1.1; namespace "urn:example"; prefix ex;
 feature core; feature stats { if-feature "core"; } feature unused;
 container root { if-feature "core";
   list item { key "id"; leaf id { type string; }
     choice mode { if-feature "stats"; case detailed {
       leaf count { type uint32; }
     } }
   }
   leaf unsupported { if-feature "core or unused"; type string; }
   anydata payload;
 }
}'''


def test_inference():
    module = parse_yang_string(SOURCE)
    assert infer_required_features(module, {}) == []
    assert infer_required_features(module, {"example:root": {"item": []}}) == ["example:core"]
    assert infer_required_features(module, {"root": {"item": [
        {"id": "a", "count": 1}, {"id": "b", "count": 2}]}}) == ["example:core", "example:stats"]
    assert infer_required_features(module, {"root": {"payload": {"opaque": 1}}}) == ["example:core"]


@pytest.mark.parametrize("data, message", [
    ({"root": {"unknown": 1}}, "Unknown or ambiguous"),
    ({"root": {"unsupported": "x"}}, "Unsupported if-feature"),
    ({"root": {"item": {}}}, "List array expected"),
])
def test_errors(data, message):
    with pytest.raises(ValueError, match=message):
        infer_required_features(parse_yang_string(SOURCE), data)


def test_imported_prerequisites(tmp_path):
    from xyang import parse_yang_file
    (tmp_path / "lib.yang").write_text('''module lib {
      namespace "urn:lib"; prefix l; feature base;
      feature extra { if-feature "base"; }
    }''')
    path = tmp_path / "main.yang"
    path.write_text('''module main {
      namespace "urn:main"; prefix m; import lib { prefix other; }
      leaf value { if-feature "other:extra"; type string; }
    }''')
    assert infer_required_features(parse_yang_file(str(path)), {"value": "x"}) == ["lib:base", "lib:extra"]


@pytest.mark.parametrize("condition", ["missing", "not a", "(a)", "a and", "a a"])
def test_invalid_conditions(condition):
    module = parse_yang_string('''module m { namespace "urn:m"; prefix m;
      feature a; leaf x { type string; if-feature "''' + condition + '''"; } }''')
    with pytest.raises(ValueError):
        infer_required_features(module, {"x": "v"})
