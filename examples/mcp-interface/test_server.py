"""Tests for server.py: one per error kind, plus a stdio round trip.

Run: python -m pytest examples/mcp-interface/test_server.py -q
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from server import ERRORS_META_KEY, ROOT, RPC_VALIDATION, TopologyServer  # noqa: E402

pytestmark = pytest.mark.skipif(
    not RPC_VALIDATION,
    reason="needs rpc validation in xYang: https://github.com/exergy-connect/xYang/issues/149",
)


def req(rid, method, params=None):
    msg = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def call(server, name, arguments=None, rid=1):
    params = {"name": name}
    if arguments is not None:
        params["arguments"] = arguments
    return server.handle(req(rid, "tools/call", params))


@pytest.fixture
def server():
    return TopologyServer()


@pytest.fixture
def built(server):
    """r1 - r2 - h1, as in session/valid.json."""
    for name in ("r1", "r2"):
        assert "isError" not in call(server, "add-node", {"name": name})["result"]
    assert "isError" not in call(server, "add-node", {"name": "h1", "role": "host"})["result"]
    assert "isError" not in call(server, "add-link", {"source": "r1", "target": "r2"})["result"]
    assert "isError" not in call(server, "add-link", {"source": "r2", "target": "h1", "bandwidth-mbps": 100})["result"]
    return server


def tool_errors(response):
    result = response["result"]
    assert result["isError"] is True
    assert result["content"][0]["type"] == "text"
    return [(e["path"], e["code"]) for e in result["_meta"][ERRORS_META_KEY]]


def recorded(server):
    return len(server.session[ROOT]["call"])


# ---- protocol --------------------------------------------------------------

def test_initialize_and_list(server):
    init = server.handle(req(1, "initialize", {}))["result"]
    assert init["protocolVersion"] == "2025-11-25"
    assert init["capabilities"] == {"tools": {"listChanged": False}}
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert server.handle(req(2, "ping"))["result"] == {}
    listed = server.handle(req(3, "tools/list"))["result"]
    assert listed == json.loads((HERE / "out" / "tools-list.json").read_text())


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("not json", -32700),
        ('{"id": 1, "method": "tools/list"}', -32600),
        ('{"jsonrpc": "2.0", "id": 1, "method": "resources/list"}', -32601),
        ('{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "delete-node"}}', -32602),
        ('{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"arguments": {}}}', -32602),
        ('{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "add-node", "arguments": []}}', -32602),
    ],
    ids=["parse", "not-jsonrpc", "unknown-method", "unknown-tool", "no-name", "arguments-not-object"],
)
def test_protocol_errors(server, message, code):
    response = server.handle_line(message)
    assert response["error"]["code"] == code
    assert "result" not in response
    assert recorded(server) == 0


def test_unknown_tool_message_matches_spec_example(server):
    assert call(server, "delete-node", {})["error"] == {"code": -32602, "message": "Unknown tool: delete-node"}


# ---- tool execution errors: arguments ---------------------------------------

def test_missing_required_argument(server):
    assert tool_errors(call(server, "add-node", {})) == [("arguments.name", "mandatory")]


def test_wrong_type_and_unknown_argument(server):
    errors = tool_errors(call(server, "add-node", {"name": 5, "colour": "red"}))
    assert ("arguments.colour", "unknown-field") in errors
    assert any(path == "arguments.name" for path, _ in errors)


def test_out_of_range(built):
    errors = tool_errors(call(built, "add-link", {"source": "r1", "target": "h1", "bandwidth-mbps": 0}))
    assert errors == [("arguments.bandwidth-mbps", "range")]


def test_self_loop(built):
    assert tool_errors(call(built, "add-link", {"source": "r1", "target": "r1"})) == [("arguments.target", "must")]


def test_hallucinated_node(built):
    response = call(built, "add-link", {"source": "r1", "target": "r9"})
    assert tool_errors(response) == [("arguments.target", "must")]
    text = response["result"]["content"][0]["text"]
    assert "earlier successful add-node" in text and "call the tool again" in text


def test_duplicate_node(built):
    errors = tool_errors(call(built, "add-node", {"name": "r1"}))
    assert ("arguments.name", "must") in errors


def test_rejected_calls_are_not_recorded(built):
    before = recorded(built)
    call(built, "add-link", {"source": "r1", "target": "r9"})
    call(built, "add-node", {})
    assert recorded(built) == before
    assert built.validator.validate_detailed(built.session)["valid"]


# ---- results ----------------------------------------------------------------

def test_structured_result(built):
    result = call(built, "find-path", {"from": "r1", "to": "h1", "max-hops": 4})["result"]
    assert result["structuredContent"] == {"hop": ["r1", "r2", "h1"]}
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    assert "isError" not in result


def test_no_path_is_a_recorded_tool_failure(built):
    call(built, "add-node", {"name": "h2", "role": "host"})
    before = recorded(built)
    result = call(built, "find-path", {"from": "r1", "to": "h2"})["result"]
    assert result["isError"] is True and "no path" in result["content"][0]["text"]
    assert recorded(built) == before + 1
    assert built.session[ROOT]["call"][-1]["result"]["status"] == "error"
    assert built.validator.validate_detailed(built.session)["valid"]


def test_server_bug_is_an_internal_error(built, monkeypatch):
    monkeypatch.setattr(built, "_execute", lambda name, args: {"hop": ["r1", "r9", "h1"]})
    before = recorded(built)
    response = call(built, "find-path", {"from": "r1", "to": "h1"})
    assert response["error"]["code"] == -32603
    assert response["error"]["data"][ERRORS_META_KEY][0]["path"].startswith("result.hop")
    assert recorded(built) == before


# ---- stdio ------------------------------------------------------------------

def test_stdio_round_trip():
    lines = [
        req(1, "initialize", {}),
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        req(2, "tools/call", {"name": "add-node", "arguments": {"name": "r1"}}),
        req(3, "tools/call", {"name": "add-link", "arguments": {"source": "r1", "target": "r9"}}),
        req(4, "tools/call", {"name": "delete-node", "arguments": {}}),
    ]
    proc = subprocess.run(
        [sys.executable, str(HERE / "server.py")],
        input="".join(json.dumps(m) + "\n" for m in lines),
        capture_output=True, text=True, check=True, cwd=HERE,
    )
    out = [json.loads(line) for line in proc.stdout.splitlines()]
    assert [o["id"] for o in out] == [1, 2, 3, 4]  # the notification gets no response
    assert out[1]["result"]["structuredContent"] == {"name": "r1"}
    assert out[2]["result"]["isError"] is True
    assert out[3]["error"]["code"] == -32602
