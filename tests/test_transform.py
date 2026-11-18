"""Python normalization integration and API contracts."""
import copy
from pathlib import Path

import pytest

from xyang import YangValidator, generate_json_schema, parse_json_schema, parse_yang_file
from xyang.ast import YangExtensionInvocationStmt
from xyang.encoding.instance import iter_instance, project_instance
from xyang.ext.transform import ExpressionError


CASE = Path(__file__).parent / "cases/normalization/conditional/m.yang"


@pytest.fixture(scope="module")
def module():
    return parse_yang_file(CASE)


def test_normalization_does_not_mutate_input(module):
    data = {"nodes": [{"name": "a"}, {"name": "b"}], "links": ["a-b"]}
    original = copy.deepcopy(data)
    assert YangValidator(module).validate_detailed(data)["valid"]
    assert data == original


def test_normalization_survives_native_json_round_trip(module):
    restored = parse_json_schema(generate_json_schema(module))
    data = {"nodes": [{"name": "a"}, {"name": "b"}], "links": ["a-b"]}
    assert YangValidator(restored).validate_detailed(data)["valid"]


def test_instance_iterator_applies_transform(module):
    data = {"nodes": [{"name": "a"}, {"name": "b"}], "links": ["a-b"]}
    projected, _ = project_instance(list(iter_instance(data, module)), module.name)
    assert projected["links"] == [{"left": "a", "right": "b"}]
    assert data["links"] == ["a-b"]


def test_unrelated_extension_with_same_name_is_not_a_transform(tmp_path):
    model = tmp_path / "m.yang"
    model.write_text('''module m {
      yang-version 1.1; namespace "urn:m"; prefix m;
      extension normalize;
      list links { key "left"; m:normalize; leaf left { type string; } }
    }''')
    result = YangValidator(parse_yang_file(model)).validate_detailed({"links": ["a-b"]})
    assert [(error["path"], error["code"]) for error in result["errors"]] == [("/links/0", "type")]


def test_root_normalization_cannot_discard_document(tmp_path):
    model = tmp_path / "m.yang"
    model.write_text('''module m {
      yang-version 1.1; namespace "urn:m"; prefix m;
      import xyang-transform { prefix xt; }
      xt:normalize { xt:if 'true'; xt:apply '"not an object"'; }
      leaf label { type string; }
    }''')
    result = YangValidator(parse_yang_file(model)).validate_detailed({"label": "a"})
    assert [(error["path"], error["code"]) for error in result["errors"]] == [("", "normalize")]


def test_unsupported_expression_fails_even_if_node_absent(module):
    restored = parse_json_schema(generate_json_schema(module))
    rule = next(s for s in restored.find_statement("links").statements if isinstance(s, YangExtensionInvocationStmt))
    rule.statements[1].argument = "unsupported(.)"
    with pytest.raises(ExpressionError, match="unsupported function"):
        YangValidator(restored).validate_detailed({})


def test_normalizes_rpc_input(tmp_path):
    model = tmp_path / "m.yang"
    model.write_text('''module m {
      yang-version 1.1; namespace "urn:m"; prefix m;
      import xyang-transform { prefix xt; }
      rpc run { input {
        list links { key "left right";
          xt:normalize {
            xt:if 'type == "string" and contains("-")';
            xt:apply 'split("-") | {left: .[0], right: .[1]}';
          }
          leaf left { type string; } leaf right { type string; }
        }
      } }
    }''')
    result = YangValidator(parse_yang_file(model)).validate_detailed(
        {"m:input": {"links": ["a-b"]}}, rpc="run"
    )
    assert result["valid"], result


def test_apply_only_rule_always_runs(tmp_path):
    model = tmp_path / "m.yang"
    model.write_text('''module m {
      yang-version 1.1; namespace "urn:m"; prefix m;
      import xyang-transform { prefix xt; }
      list links { key "left right";
        xt:normalize {
          xt:apply 'split("-") | {left: .[0], right: .[1]}';
        }
        leaf left { type string; } leaf right { type string; }
      }
    }''')
    result = YangValidator(parse_yang_file(model)).validate_detailed({"links": ["a-b"]})
    assert result["valid"], result


@pytest.mark.parametrize(
    "body,match",
    [
        ("", "xt:apply"),
        ("xt:if 'true';", "xt:apply"),
        ("xt:apply 'true'; xt:if 'true';", "xt:apply"),
        ("xt:if 'true'; xt:if 'true'; xt:apply 'true';", "xt:apply"),
    ],
)
def test_normalize_requires_apply_in_order(tmp_path, body, match):
    model = tmp_path / "m.yang"
    model.write_text(f'''module m {{
      yang-version 1.1; namespace "urn:m"; prefix m;
      import xyang-transform {{ prefix xt; }}
      leaf label {{ type string; xt:normalize {{ {body} }} }}
    }}''')
    with pytest.raises(ExpressionError, match=match):
        YangValidator(parse_yang_file(model)).validate_detailed({})


def test_dotted_keys_survive_native_json_round_trip_and_do_not_mutate():
    schema = CASE.parent.parent / "dotted/m.yang"
    module = parse_json_schema(generate_json_schema(parse_yang_file(schema)))
    data = {"nodes": {"a": {"bgp.as": 65000}}}
    original = copy.deepcopy(data)
    assert YangValidator(module).validate_detailed(data, native_json=True)["valid"]
    assert data == original


@pytest.mark.parametrize("value", ["TRUE", "yes", "1"])
def test_dotted_keys_rejects_invalid_setting(tmp_path, value):
    model = tmp_path / "m.yang"
    model.write_text(f'''module m {{
      yang-version 1.1; namespace "urn:m"; prefix m;
      import xyang-transform {{ prefix xt; }}
      xt:expand-dotted-keys {value};
    }}''')
    with pytest.raises(ExpressionError, match="requires true or false"):
        YangValidator(parse_yang_file(model)).validate_detailed({})


def test_dotted_keys_setting_is_module_level_only(tmp_path):
    model = tmp_path / "m.yang"
    model.write_text('''module m {
      yang-version 1.1; namespace "urn:m"; prefix m;
      import xyang-transform { prefix xt; }
      container c { xt:expand-dotted-keys true; }
    }''')
    with pytest.raises(ExpressionError, match="only at module level"):
        YangValidator(parse_yang_file(model)).validate_detailed({})


def test_dotted_keys_false_leaves_keys_unchanged(tmp_path):
    model = tmp_path / "m.yang"
    model.write_text('''module m {
      yang-version 1.1; namespace "urn:m"; prefix m;
      import xyang-transform { prefix xt; }
      xt:expand-dotted-keys false;
      container c { leaf v { type string; } }
    }''')
    result = YangValidator(parse_yang_file(model)).validate_detailed({"c.v": "x"})
    assert [(error["path"], error["code"]) for error in result["errors"]] == [("/c.v", "unknown-field")]
