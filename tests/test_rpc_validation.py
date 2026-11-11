"""RPC and action validate API contracts and CLI --rpc/--output/--context (issue #149).

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


ACTION_MODULE = """
module ex {
  yang-version 1.1;
  namespace "urn:ex";
  prefix ex;

  container interfaces {
    list interface {
      key name;
      leaf name { type string; }
      leaf mtu { type uint16; }
      action reset {
        input {
          leaf delay {
            type uint16;
            must ". < ../../ex:mtu" { error-message "delay must be below the interface mtu."; }
          }
        }
        output { leaf ok { type boolean; mandatory true; } }
      }
    }
  }
}
"""

SERVER = {"ex:interfaces": {"interface": [{"name": "eth0", "mtu": 1500}, {"name": "eth1", "mtu": 9000}]}}
ETH0 = "/ex:interfaces/interface=eth0/reset"


@pytest.fixture
def action_module():
    return parse_yang_string(ACTION_MODULE)


def test_action_must_reads_the_selected_parent_entry(action_module):
    data = {"ex:input": {"delay": 1600}}
    bad = validate(action_module, data, action=ETH0, context=SERVER)
    assert [(e["path"], e["code"], e["message"]) for e in bad["errors"]] == [
        ("/ex:input/delay", "must", "delay must be below the interface mtu.")
    ]
    assert validate(action_module, data, action="/ex:interfaces/interface=eth1/reset", context=SERVER)["valid"]


def test_action_output(action_module):
    result = validate(action_module, {"ex:output": {}}, action=ETH0, direction="output", context=SERVER)
    assert [(e["path"], e["code"]) for e in result["errors"]] == [("/ex:output/ok", "mandatory")]


def test_action_parent_missing_from_context(action_module):
    result = validate(action_module, {"ex:input": {}}, action="/ex:interfaces/interface=eth9/reset", context=SERVER)
    assert result["errors"][0]["document"] == "context"
    assert (result["errors"][0]["path"], result["errors"][0]["code"]) == ("", "action-parent")


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"action": ETH0}, "action needs context"),
        ({"action": ETH0, "rpc": "x", "context": {}}, "mutually exclusive"),
        ({"action": "/ex:interfaces/interface/reset", "context": {}}, "needs its 1 key value"),
        ({"action": "/ex:interfaces/interface=eth0/nope", "context": {}}, "has no action 'ex:nope'"),
        ({"action": "interfaces/interface=eth0/reset", "context": {}}, "data resource identifier"),
    ],
)
def test_action_usage_errors(action_module, kwargs, message):
    with pytest.raises(ValueError, match=message):
        validate(action_module, {"ex:input": {}}, **kwargs)


def test_invalid_context_is_reported_before_the_operation(action_module):
    bad_server = {"ex:interfaces": {"interface": [{"name": "eth0", "mtu": "big"}]}}
    result = validate(action_module, {"ex:input": {"delay": 99999}}, action=ETH0, context=bad_server)
    assert result["errors"] == [
        {
            "document": "context",
            "code": "type",
            "path": "/ex:interfaces/interface/0/mtu",
            "message": result["errors"][0]["message"],
            "severity": "error",
        }
    ]
    ok, messages, _warnings = YangValidator(action_module).validate({"ex:input": {}}, action=ETH0, context=bad_server)
    assert not ok and messages[0].startswith("context /interfaces/interface")


def test_action_does_not_mutate_module_or_context(action_module):
    server = copy.deepcopy(SERVER)
    interface = action_module.statements[0].statements[0]
    before = list(interface.statements)
    validate(action_module, {"ex:input": {"delay": 1}}, action=ETH0, context=server)
    assert server == SERVER
    assert interface.statements == before and all(a is b for a, b in zip(interface.statements, before))


@pytest.fixture
def action_files(tmp_path: Path):
    yang = tmp_path / "ex.yang"
    yang.write_text(ACTION_MODULE, encoding="utf-8")

    def write(name: str, value) -> str:
        path = tmp_path / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return str(path)

    return str(yang), write


def test_cli_action(action_files):
    yang, write = action_files
    ctx = write("server.json", SERVER)
    bad = _cli(
        "--format", "json", "--action", ETH0, "--context", ctx, yang, write("in.json", {"ex:input": {"delay": 1600}})
    )
    assert bad.returncode == 1
    assert json.loads(bad.stdout)["errors"][0]["path"] == "/ex:input/delay"
    out = _cli("--action", ETH0, "--output", "--context", ctx, yang, write("out.json", {"ex:output": {"ok": True}}))
    assert out.returncode == 0


def test_cli_context_errors_carry_the_document(action_files):
    yang, write = action_files
    ctx = write("bad.json", {"ex:interfaces": {"interface": [{"name": "eth0", "mtu": "big"}]}})
    proc = _cli("--format", "json", "--action", ETH0, "--context", ctx, yang, write("in.json", {"ex:input": {}}))
    assert proc.returncode == 1
    (issue,) = json.loads(proc.stdout)["errors"]
    assert (issue["document"], issue["path"], issue["code"]) == ("context", "/ex:interfaces/interface/0/mtu", "type")


@pytest.mark.parametrize(
    "extra",
    [
        ["--action", ETH0],
        ["--action", ETH0, "--rpc", "x"],
        ["--action", "/ex:interfaces/interface/reset", "--context", "CTX"],
    ],
)
def test_cli_action_usage_errors_exit_2(action_files, extra):
    yang, write = action_files
    ctx = write("server.json", SERVER)
    proc = _cli(*[ctx if item == "CTX" else item for item in extra], yang, write("in.json", {"ex:input": {}}))
    assert proc.returncode == 2
    assert proc.stdout == ""


def test_cli_undeclared_xpath_prefix_exits_2(tmp_path: Path):
    yang = tmp_path / "m.yang"
    yang.write_text(
        'module m { yang-version 1.1; namespace "urn:m"; prefix m;'
        ' container top { leaf a { type leafref { path "/x:top/x:b"; } } leaf b { type string; } } }',
        encoding="utf-8",
    )
    data = tmp_path / "d.json"
    data.write_text("{}", encoding="utf-8")
    proc = _cli("--format", "json", str(yang), str(data))
    assert proc.returncode == 2
    assert "unknown prefix 'x'" in proc.stderr
