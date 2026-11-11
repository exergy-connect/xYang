"""RPC validate API contracts and CLI --rpc/--output/--context (issue #149).

Validation outcomes live in tests/cases/operations/; this file keeps mutation,
legacy validate() text paths, and CLI exit/stdout contracts.
"""

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
