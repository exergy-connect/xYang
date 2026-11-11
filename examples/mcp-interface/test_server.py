"""Tests for server.py (MCP 2026-07-28): protocol, sessions, tool errors, HTTP rules.

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

import server as srv  # noqa: E402
from server import (  # noqa: E402
    ERRORS_META_KEY, META_SERVER_INFO, PROTOCOL_VERSION, ROOT, RPC_VALIDATION, SESSION_TTL_SECONDS,
    TopologyServer, handle_http,
)

pytestmark = pytest.mark.skipif(
    not RPC_VALIDATION,
    reason="needs an xYang with rpc validation: https://github.com/exergy-connect/xYang/pull/151",
)

META = {"io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION}


def req(rid, method, params=None, meta=True):
    params = dict(params or {})
    if meta:
        params["_meta"] = dict(META)
    return {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}


def call(server, name, arguments=None, rid=1):
    params = {"name": name}
    if arguments is not None:
        params["arguments"] = arguments
    return server.handle(req(rid, "tools/call", params))


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def server(clock):
    return TopologyServer(clock=clock)


def open_session(server):
    return call(server, "open-session", {})["result"]["structuredContent"]["session"]


@pytest.fixture
def built(server):
    """r1 - r2 - h1 in one session, as in session/valid.json. Returns (server, handle)."""
    h = open_session(server)
    for args in ({"name": "r1"}, {"name": "r2"}, {"name": "h1", "role": "host"}):
        assert "isError" not in call(server, "add-node", {"session": h, **args})["result"]
    for args in ({"source": "r1", "target": "r2"}, {"source": "r2", "target": "h1", "bandwidth-mbps": 100}):
        assert "isError" not in call(server, "add-link", {"session": h, **args})["result"]
    return server, h


def tool_errors(response):
    result = response["result"]
    assert result["isError"] is True
    assert result["content"][0]["type"] == "text"
    return [(e["path"], e["code"]) for e in result["_meta"][ERRORS_META_KEY]]


def recorded(server, h):
    return len(server.sessions[h].record[ROOT]["call"])


# ---- protocol (MCP 2026-07-28) ------------------------------------------------

def test_discover(server):
    result = server.handle(req(1, "server/discover"))["result"]
    assert result["resultType"] == "complete"
    assert result["supportedVersions"] == [PROTOCOL_VERSION]
    assert result["capabilities"] == {"tools": {}}
    assert result["_meta"][META_SERVER_INFO]["name"] == "topology-builder"
    assert result["ttlMs"] > 0 and result["cacheScope"] == "public"


def test_tools_list_is_cacheable_and_matches_the_compiled_interface(server):
    result = server.handle(req(1, "tools/list"))["result"]
    assert result["tools"] == json.loads((HERE / "out" / "tools-list.json").read_text())["tools"]
    assert result["resultType"] == "complete" and result["cacheScope"] == "public" and result["ttlMs"] > 0
    assert [t["name"] for t in result["tools"]] == ["open-session", "add-node", "add-link", "find-path"]


def test_every_result_names_the_server(built):
    server, h = built
    result = call(server, "add-node", {"session": h, "name": "r9"})["result"]
    assert result["resultType"] == "complete"
    assert result["_meta"][META_SERVER_INFO] == srv.SERVER_INFO


def test_missing_version_is_invalid_params(server):
    assert server.handle(req(1, "tools/list", meta=False))["error"]["code"] == -32602


def test_unsupported_version(server):
    message = req(1, "tools/list")
    message["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] = "2025-11-25"
    error = server.handle(message)["error"]
    assert error["code"] == -32022
    assert error["data"] == {"supported": [PROTOCOL_VERSION], "requested": "2025-11-25"}


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("not json", -32700),
        ('{"id": 1, "method": "tools/list"}', -32600),
        (json.dumps(req(1, "initialize")), -32601),
        (json.dumps(req(1, "ping")), -32601),
        (json.dumps(req(1, "tools/call", {"name": "delete-node"})), -32602),
        (json.dumps(req(1, "tools/call", {"arguments": {}})), -32602),
        (json.dumps(req(1, "tools/call", {"name": "add-node", "arguments": []})), -32602),
    ],
    ids=["parse", "not-jsonrpc", "initialize-removed", "ping-removed", "unknown-tool", "no-name", "arguments-not-object"],
)
def test_protocol_errors(server, message, code):
    response = server.handle_line(message)
    assert response["error"]["code"] == code
    assert server.sessions == {}


def test_unknown_tool_message_matches_spec_example(server):
    assert call(server, "delete-node", {})["error"] == {"code": -32602, "message": "Unknown tool: delete-node"}


# ---- sessions (stateful tools) --------------------------------------------------

def test_open_session_mints_distinct_opaque_handles(server):
    a, b = open_session(server), open_session(server)
    assert a != b and a.startswith("ses_") and len(a) == 36
    assert server.sessions[a].record[ROOT]["handle"] == a


def test_open_session_takes_no_arguments(server):
    assert tool_errors(call(server, "open-session", {"name": "x"})) == [("arguments.name", "unknown-field")]


def test_unknown_session(server):
    errors = tool_errors(call(server, "add-node", {"session": "ses_" + "0" * 32, "name": "r1"}))
    assert errors == [("arguments.session", "unknown-session")]


def test_missing_session(server):
    assert tool_errors(call(server, "add-node", {"name": "r1"})) == [("arguments.session", "unknown-session")]


def test_sessions_are_separate(built):
    server, h = built
    other = open_session(server)
    errors = tool_errors(call(server, "add-link", {"session": other, "source": "r1", "target": "r2"}))
    assert errors == [("arguments.source", "must"), ("arguments.target", "must")]


def test_session_expires_after_24_hours_idle(built, clock):
    server, h = built
    clock.now += SESSION_TTL_SECONDS + 1
    assert tool_errors(call(server, "add-node", {"session": h, "name": "r3"})) == [("arguments.session", "unknown-session")]
    assert h not in server.sessions


def test_activity_keeps_a_session_alive(built, clock):
    server, h = built
    for _ in range(3):
        clock.now += SESSION_TTL_SECONDS - 60
        assert "isError" not in call(server, "find-path", {"session": h, "from": "r1", "to": "h1"})["result"]


# ---- tool execution errors: arguments ---------------------------------------------

def test_missing_required_argument(built):
    server, h = built
    assert tool_errors(call(server, "add-node", {"session": h})) == [("arguments.name", "mandatory")]


def test_wrong_type_and_unknown_argument(built):
    server, h = built
    errors = tool_errors(call(server, "add-node", {"session": h, "name": 5, "colour": "red"}))
    assert ("arguments.colour", "unknown-field") in errors
    assert any(path == "arguments.name" for path, _ in errors)


def test_out_of_range(built):
    server, h = built
    errors = tool_errors(call(server, "add-link", {"session": h, "source": "r1", "target": "h1", "bandwidth-mbps": 0}))
    assert errors == [("arguments.bandwidth-mbps", "range")]


def test_self_loop(built):
    server, h = built
    assert tool_errors(call(server, "add-link", {"session": h, "source": "r1", "target": "r1"})) == [("arguments.target", "must")]


def test_hallucinated_node(built):
    server, h = built
    response = call(server, "add-link", {"session": h, "source": "r1", "target": "r9"})
    assert tool_errors(response) == [("arguments.target", "must")]
    text = response["result"]["content"][0]["text"]
    assert "earlier successful add-node" in text and "call the tool again" in text


def test_duplicate_node(built):
    server, h = built
    assert ("arguments.name", "must") in tool_errors(call(server, "add-node", {"session": h, "name": "r1"}))


def test_rejected_calls_are_not_recorded(built):
    server, h = built
    before = recorded(server, h)
    call(server, "add-link", {"session": h, "source": "r1", "target": "r9"})
    call(server, "add-node", {"session": h})
    assert recorded(server, h) == before
    assert server.validator.validate_detailed(server.sessions[h].record)["valid"]


# ---- results ------------------------------------------------------------------------

def test_structured_result(built):
    server, h = built
    result = call(server, "find-path", {"session": h, "from": "r1", "to": "h1", "max-hops": 4})["result"]
    assert result["structuredContent"] == {"hop": ["r1", "r2", "h1"]}
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    assert "isError" not in result


def test_no_path_is_a_recorded_tool_failure(built):
    server, h = built
    call(server, "add-node", {"session": h, "name": "h2", "role": "host"})
    before = recorded(server, h)
    result = call(server, "find-path", {"session": h, "from": "r1", "to": "h2"})["result"]
    assert result["isError"] is True and "no path" in result["content"][0]["text"]
    assert recorded(server, h) == before + 1
    assert server.sessions[h].record[ROOT]["call"][-1]["result"]["status"] == "error"
    assert server.validator.validate_detailed(server.sessions[h].record)["valid"]


def test_server_bug_is_an_internal_error(built, monkeypatch):
    server, h = built
    monkeypatch.setattr(server, "_execute", lambda session, name, args: {"hop": ["r1", "r9", "h1"]})
    before = recorded(server, h)
    response = call(server, "find-path", {"session": h, "from": "r1", "to": "h1"})
    assert response["error"]["code"] == -32603
    assert response["error"]["data"][ERRORS_META_KEY][0]["path"].startswith("result.hop")
    assert recorded(server, h) == before


def test_corrupt_record_is_an_internal_error(built):
    server, h = built
    server.sessions[h].record[ROOT]["call"][0]["tool"] = "example-topology-tools:delete-node"
    response = call(server, "add-node", {"session": h, "name": "r3"})
    assert response["error"]["code"] == -32603
    assert "session record is invalid" in response["error"]["message"]


# ---- Streamable HTTP rules (MCP 2026-07-28) --------------------------------------------

ORIGINS = {"http://127.0.0.1:8787"}


def http(server, message, headers=None, method="POST", path="/mcp"):
    body = message if isinstance(message, bytes) else json.dumps(message).encode()
    lower = {k.lower(): v for k, v in (headers or {}).items()}
    return handle_http(server, method, path, lambda name: lower.get(name.lower()), body, ORIGINS)


def good_headers(message, session=None):
    headers = {"MCP-Protocol-Version": PROTOCOL_VERSION, "Mcp-Method": message["method"]}
    if message["method"] == "tools/call":
        headers["Mcp-Name"] = message["params"]["name"]
    if session:
        headers["Mcp-Param-Session"] = session
    return headers


def test_http_ok(built):
    server, h = built
    message = req(7, "tools/call", {"name": "add-node", "arguments": {"session": h, "name": "r5"}})
    status, body, _ = http(server, message, good_headers(message, h))
    assert status == 200 and body["result"]["structuredContent"] == {"name": "r5"}


@pytest.mark.parametrize("method", ["GET", "DELETE"])
def test_http_get_and_delete_are_not_allowed(server, method):
    status, body, extra = http(server, b"", method=method)
    assert (status, body, extra) == (405, None, {"Allow": "POST"})


def test_http_wrong_path(server):
    assert http(server, req(1, "tools/list"), path="/")[0] == 404


def test_http_forbidden_origin(server):
    message = req(1, "tools/list")
    status, body, _ = http(server, message, good_headers(message) | {"Origin": "https://evil.example"})
    assert status == 403 and "id" not in body


def test_http_notification_is_accepted(server):
    assert http(server, {"jsonrpc": "2.0", "method": "notifications/whatever"})[:2] == (202, None)


@pytest.mark.parametrize(
    "drop_or_change",
    [
        {"MCP-Protocol-Version": None},
        {"MCP-Protocol-Version": "2026-01-01"},
        {"Mcp-Method": None},
        {"Mcp-Method": "tools/list"},
        {"Mcp-Name": None},
        {"Mcp-Name": "add-link"},
        {"Mcp-Param-Session": None},
        {"Mcp-Param-Session": "ses_" + "1" * 32},
    ],
    ids=["no-version", "version-differs-from-body", "no-method", "method-differs", "no-name", "name-differs",
         "no-session-header", "session-header-differs"],
)
def test_http_header_mismatch(built, drop_or_change):
    server, h = built
    message = req(1, "tools/call", {"name": "add-node", "arguments": {"session": h, "name": "r5"}})
    headers = good_headers(message, h)
    for k, v in drop_or_change.items():
        headers.pop(k) if v is None else headers.update({k: v})
    status, body, _ = http(server, message, headers)
    assert status == 400 and body["error"]["code"] == -32020
    assert recorded(server, h) == 5


def test_http_session_header_without_argument_is_a_mismatch(server):
    message = req(1, "tools/call", {"name": "open-session", "arguments": {}})
    status, body, _ = http(server, message, good_headers(message, "ses_" + "1" * 32))
    assert status == 200  # open-session has no session argument, so the header is not checked
    message = req(2, "tools/call", {"name": "add-node", "arguments": {"name": "r1"}})
    status, body, _ = http(server, message, good_headers(message, "ses_" + "1" * 32))
    assert status == 400 and body["error"]["code"] == -32020


def test_http_base64_name_header(built):
    server, h = built
    message = req(1, "tools/call", {"name": "add-node", "arguments": {"session": h, "name": "r6"}})
    headers = good_headers(message, h) | {"Mcp-Name": "=?base64?YWRkLW5vZGU=?="}  # "add-node"
    assert http(server, message, headers)[0] == 200


def test_http_unsupported_version(server):
    message = req(1, "tools/list")
    message["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] = "1900-01-01"
    headers = good_headers(message) | {"MCP-Protocol-Version": "1900-01-01"}
    status, body, _ = http(server, message, headers)
    assert status == 400 and body["error"]["code"] == -32022


def test_http_unknown_method_is_404(server):
    message = req(1, "resources/list")
    status, body, _ = http(server, message, good_headers(message))
    assert status == 404 and body["error"]["code"] == -32601


# ---- stdio ---------------------------------------------------------------------------

def test_stdio_round_trip():
    lines = [
        req(1, "server/discover"),
        req(2, "tools/call", {"name": "open-session", "arguments": {}}),
        {"jsonrpc": "2.0", "method": "notifications/whatever"},
        req(3, "tools/call", {"name": "delete-node", "arguments": {}}),
    ]
    proc = subprocess.run(
        [sys.executable, str(HERE / "server.py")],
        input="".join(json.dumps(m) + "\n" for m in lines),
        capture_output=True, text=True, check=True, cwd=HERE,
    )
    out = [json.loads(line) for line in proc.stdout.splitlines()]
    assert [o["id"] for o in out] == [1, 2, 3]  # the notification gets no response
    assert out[0]["result"]["supportedVersions"] == [PROTOCOL_VERSION]
    assert out[1]["result"]["structuredContent"]["session"].startswith("ses_")
    assert out[2]["error"]["code"] == -32602
