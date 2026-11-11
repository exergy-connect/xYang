"""Validate rpc input and output instances (issue #149). Shared cases: tests/cases/operations."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from xyang import YangValidator, parse_yang_string, validate

MODULE = """
module example-topology-tools {
  yang-version 1.1;
  namespace "urn:example:topology-tools";
  prefix ett;

  typedef node-name { type string { pattern "[a-z][a-z0-9]*"; } }

  container topology {
    list node { key name; leaf name { type node-name; } }
  }

  rpc add-link {
    input {
      leaf source { type node-name; mandatory true; }
      leaf target {
        type node-name;
        mandatory true;
        must ". != ../source" { error-message "A link cannot connect a node to itself."; }
      }
      leaf via { type leafref { path "/topology/node/name"; } }
    }
    output { leaf link-id { type string; mandatory true; } }
  }
}
"""

SELF_LINK = {"example-topology-tools:input": {"source": "r1", "target": "r1"}}
OTHER_LINK = {"example-topology-tools:input": {"source": "r1", "target": "r2"}}


@pytest.fixture
def module():
    return parse_yang_string(MODULE)


def test_old_behavior_without_rpc_is_unknown_field(module):
    result = validate(module, SELF_LINK)
    assert [(e["path"], e["code"]) for e in result["errors"]] == [("/example-topology-tools:input", "unknown-field")]


def test_self_link_fails_must_with_the_error_message(module):
    result = validate(module, SELF_LINK, rpc="add-link")
    assert result["valid"] is False
    assert [(e["path"], e["code"], e["message"]) for e in result["errors"]] == [
        ("/example-topology-tools:input/target", "must", "A link cannot connect a node to itself.")
    ]


def test_other_target_passes(module):
    assert validate(module, OTHER_LINK, rpc="add-link", direction="input")["valid"] is True


def test_native_json_takes_bare_parameters(module):
    result = validate(module, SELF_LINK["example-topology-tools:input"], rpc="add-link", native_json=True)
    assert [(e["path"], e["code"]) for e in result["errors"]] == [("/target", "must")]


def test_output_direction(module):
    ok = validate(module, {"example-topology-tools:output": {"link-id": "l1"}}, rpc="add-link", direction="output")
    assert ok["valid"] is True
    bad = validate(module, {"example-topology-tools:output": {}}, rpc="add-link", direction="output")
    assert [(e["path"], e["code"]) for e in bad["errors"]] == [("/example-topology-tools:output/link-id", "mandatory")]


def test_context_joins_the_operation_node(module):
    data = {"example-topology-tools:input": {"source": "r1", "target": "r2", "via": "r3"}}
    context = {"example-topology-tools:topology": {"node": [{"name": "r3"}]}}
    assert validate(module, data, rpc="add-link", context=context)["valid"] is True
    without = validate(module, data, rpc="add-link")
    assert [(e["path"], e["code"]) for e in without["errors"]] == [("/example-topology-tools:input/via", "leafref")]


def test_wrapper_is_not_an_xpath_level(module):
    """``../source`` is resolved from the operation node, so the wrapper adds no level."""
    result = YangValidator(module).validate_detailed(OTHER_LINK, rpc="add-link")
    assert result["errors"] == []


def test_module_and_data_are_not_mutated(module):
    statements = list(module.statements)
    rpc = next(s for s in statements if type(s).__name__ == "YangRpcStmt")
    body = list(rpc.statements)
    names = [(s.name, type(s).__name__) for s in body]
    data = copy.deepcopy(SELF_LINK)
    context = {"example-topology-tools:topology": {"node": [{"name": "r1"}]}}
    snapshot = copy.deepcopy(context)
    validate(module, data, rpc="add-link", context=context)
    validate(module, data)
    assert data == SELF_LINK
    assert context == snapshot
    assert len(module.statements) == len(statements)
    assert all(a is b for a, b in zip(module.statements, statements))
    assert rpc.statements == body and [(s.name, type(s).__name__) for s in rpc.statements] == names
    assert rpc.statements[0].name == "input"


def test_validate_text_output_uses_the_wrapper_path(module):
    ok, errors, _warnings = YangValidator(module).validate(SELF_LINK, rpc="add-link")
    assert ok is False
    assert errors[0].startswith("/example-topology-tools:input/target: A link cannot connect a node to itself.")


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"rpc": "nope"}, "no rpc 'nope'"),
        ({"direction": "output"}, "direction applies only together with rpc"),
        ({"context": {}}, "context applies only together with rpc"),
        ({"rpc": "add-link", "direction": "sideways"}, "direction must be 'input' or 'output'"),
        ({"rpc": "add-link", "context": []}, "context must be a JSON object"),
        ({"rpc": ""}, "rpc must be a non-empty rpc name"),
    ],
)
def test_usage_errors_raise_value_error(module, kwargs, message):
    with pytest.raises(ValueError, match=message):
        validate(module, OTHER_LINK, **kwargs)


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "xyang", "validate", *args], capture_output=True, text=True, check=False
    )


@pytest.fixture
def files(tmp_path: Path):
    yang = tmp_path / "topology.yang"
    yang.write_text(MODULE, encoding="utf-8")

    def write(name: str, value) -> str:
        path = tmp_path / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return str(path)

    return str(yang), write


def test_cli_rpc_defaults_to_input(files):
    yang, write = files
    bad = _cli("--format", "json", "--rpc", "add-link", yang, write("self.json", SELF_LINK))
    assert bad.returncode == 1
    assert json.loads(bad.stdout)["errors"] == [
        {
            "path": "/example-topology-tools:input/target",
            "code": "must",
            "message": "A link cannot connect a node to itself.",
        }
    ]
    good = _cli("--rpc", "add-link", yang, write("other.json", OTHER_LINK))
    assert good.returncode == 0
    assert good.stdout.strip() == "Valid."


def test_cli_output_and_native_json(files):
    yang, write = files
    out = _cli(
        "--format",
        "json",
        "--rpc",
        "add-link",
        "--output",
        yang,
        write("out.json", {"example-topology-tools:output": {}}),
    )
    assert out.returncode == 1
    assert json.loads(out.stdout)["errors"][0]["path"] == "/example-topology-tools:output/link-id"
    native = _cli(
        "--format",
        "json",
        "--native-json",
        "--rpc",
        "add-link",
        yang,
        write("native.json", {"source": "a", "target": "a"}),
    )
    assert json.loads(native.stdout)["errors"][0]["path"] == "/target"


def test_cli_context(files):
    yang, write = files
    data = write("via.json", {"example-topology-tools:input": {"source": "r1", "target": "r2", "via": "r3"}})
    context = write("ctx.json", {"example-topology-tools:topology": {"node": [{"name": "r3"}]}})
    assert _cli("--rpc", "add-link", "--context", context, yang, data).returncode == 0
    assert _cli("--rpc", "add-link", yang, data).returncode == 1


@pytest.mark.parametrize(
    "extra",
    [["--rpc", "nope"], ["--output"], ["--context", "ctx.json"]],
)
def test_cli_usage_errors_exit_2(files, extra):
    yang, write = files
    extra = [write("ctx.json", {}) if item == "ctx.json" else item for item in extra]
    proc = _cli(*extra, yang, write("in.json", OTHER_LINK))
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr.startswith("Error:")


def test_cli_missing_context_file_exits_2(files):
    yang, write = files
    proc = _cli("--rpc", "add-link", "--context", "/nonexistent/ctx.json", yang, write("in.json", OTHER_LINK))
    assert proc.returncode == 2
