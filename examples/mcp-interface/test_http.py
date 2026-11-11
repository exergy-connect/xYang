"""Streamable HTTP rules (MCP 2026-07-28), over a real HTTP connection.

The same tests run against any deployment of the server:

  python -m pytest test_http.py -q                                      # starts server.py --http
  MCP_URL=http://127.0.0.1:8787/mcp python -m pytest test_http.py -q    # e.g. the Worker under wrangler dev
  MCP_URL=https://<host>/mcp python -m pytest test_http.py -q           # a deployed Worker (HTTP/1.1)
"""

from __future__ import annotations

import io
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from agent_client import Agent, Http1Transport, McpClient  # noqa: E402
from server import PROTOCOL_VERSION, RPC_VALIDATION, TopologyServer, serve_http  # noqa: E402

pytestmark = pytest.mark.skipif(
    not RPC_VALIDATION and not os.environ.get("MCP_URL"),
    reason="needs an xYang with rpc validation: https://github.com/exergy-connect/xYang/pull/151",
)

META = {"io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
        "io.modelcontextprotocol/clientInfo": {"name": "test_http", "version": "1"}}


@pytest.fixture(scope="module")
def url():
    if os.environ.get("MCP_URL"):
        return os.environ["MCP_URL"]
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    threading.Thread(target=serve_http, args=(TopologyServer(), "127.0.0.1", port), daemon=True).start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return f"http://127.0.0.1:{port}/mcp"
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("server did not start")


def post(url, message, headers=None, method="POST", raw=None):
    data = raw if raw is not None else json.dumps(message).encode()
    req = urllib.request.Request(url, data=data if method == "POST" else None, method=method,
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json, text/event-stream", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else None), dict(resp.headers)
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, (json.loads(body) if body else None), dict(e.headers)


def request(rid, method, params=None):
    return {"jsonrpc": "2.0", "id": rid, "method": method, "params": {**(params or {}), "_meta": dict(META)}}


def headers_for(message, session=None):
    h = {"MCP-Protocol-Version": PROTOCOL_VERSION, "Mcp-Method": message["method"]}
    if message["method"] == "tools/call":
        h["Mcp-Name"] = message["params"]["name"]
    if session:
        h["Mcp-Param-Session"] = session
    return h


def call(url, name, arguments, rid=1, extra=None):
    message = request(rid, "tools/call", {"name": name, "arguments": arguments})
    return post(url, message, headers_for(message, arguments.get("session")) | (extra or {}))


def new_session(url):
    status, body, _ = call(url, "open-session", {})
    assert status == 200
    return body["result"]["structuredContent"]["session"]


def errors_of(body):
    result = body["result"]
    assert result["isError"] is True
    return [(e["path"], e["code"]) for e in result["_meta"]["xyang/errors"]]


# ---- the agent ------------------------------------------------------------------

def test_agent_completes_its_plan(url):
    out = io.StringIO()
    transport = Http1Transport(url)
    try:
        assert Agent(McpClient(transport), out).run() == {"hop": ["r1", "r2", "h1"]}
    finally:
        transport.close()
    assert "done     8 calls, 2 repairs, path r1 -> r2 -> h1" in out.getvalue()


# ---- protocol ---------------------------------------------------------------------

def test_discover(url):
    message = request(1, "server/discover")
    status, body, headers = post(url, message, headers_for(message))
    assert status == 200 and headers.get("Content-Type", "").startswith("application/json")
    result = body["result"]
    assert result["resultType"] == "complete" and result["supportedVersions"] == [PROTOCOL_VERSION]
    assert result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "topology-builder"


def test_tools_list_matches_the_compiled_interface(url):
    message = request(1, "tools/list")
    status, body, _ = post(url, message, headers_for(message))
    assert status == 200
    assert body["result"]["tools"] == json.loads((HERE / "out" / "tools-list.json").read_text())["tools"]
    assert body["result"]["cacheScope"] == "public" and body["result"]["ttlMs"] > 0


@pytest.mark.parametrize("method", ["GET", "DELETE"])
def test_only_post(url, method):
    status, body, headers = post(url, None, method=method)
    assert status == 405 and headers.get("Allow") == "POST"


def test_wrong_path(url):
    assert post(url.rsplit("/", 1)[0] + "/nope", request(1, "tools/list"))[0] == 404


def test_forbidden_origin(url):
    message = request(1, "tools/list")
    status, body, _ = post(url, message, headers_for(message) | {"Origin": "https://evil.example"})
    assert status == 403


def test_not_json(url):
    status, body, _ = post(url, None, {}, raw=b"not json")
    assert status == 400 and body["error"]["code"] == -32700


def test_notification_is_accepted(url):
    assert post(url, {"jsonrpc": "2.0", "method": "notifications/whatever"})[:2] == (202, None)


def test_unknown_method_is_404(url):
    message = request(1, "initialize")
    status, body, _ = post(url, message, headers_for(message))
    assert status == 404 and body["error"]["code"] == -32601


def test_unsupported_version(url):
    message = request(1, "tools/list")
    message["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] = "1900-01-01"
    status, body, _ = post(url, message, headers_for(message) | {"MCP-Protocol-Version": "1900-01-01"})
    assert status == 400 and body["error"]["code"] == -32022
    assert body["error"]["data"] == {"supported": [PROTOCOL_VERSION], "requested": "1900-01-01"}


@pytest.mark.parametrize(
    "change",
    [{"MCP-Protocol-Version": None}, {"Mcp-Method": "tools/list"}, {"Mcp-Name": None}, {"Mcp-Name": "add-link"},
     {"Mcp-Param-Session": None}, {"Mcp-Param-Session": "ses_" + "1" * 32}],
    ids=["no-version", "method-differs", "no-name", "name-differs", "no-session-header", "session-header-differs"],
)
def test_header_mismatch(url, change):
    handle = new_session(url)
    message = request(1, "tools/call", {"name": "add-node", "arguments": {"session": handle, "name": "r1"}})
    headers = headers_for(message, handle)
    for k, v in change.items():
        headers.pop(k) if v is None else headers.update({k: v})
    status, body, _ = post(url, message, headers)
    assert status == 400 and body["error"]["code"] == -32020


def test_base64_name_header(url):
    handle = new_session(url)
    status, body, _ = call(url, "add-node", {"session": handle, "name": "r1"},
                           extra={"Mcp-Name": "=?base64?YWRkLW5vZGU=?="})
    assert status == 200 and body["result"]["structuredContent"] == {"name": "r1"}


def test_unknown_tool(url):
    status, body, _ = call(url, "delete-node", {})
    assert status == 200 and body["error"] == {"code": -32602, "message": "Unknown tool: delete-node"}


# ---- sessions and tool errors ---------------------------------------------------------

def test_unknown_session(url):
    status, body, _ = call(url, "add-node", {"session": "ses_" + "0" * 32, "name": "r1"})
    assert errors_of(body) == [("arguments.session", "unknown-session")]


def test_state_persists_per_session_and_sessions_are_separate(url):
    a, b = new_session(url), new_session(url)
    assert a != b
    assert "isError" not in call(url, "add-node", {"session": a, "name": "r1"})[1]["result"]
    assert "isError" not in call(url, "add-node", {"session": a, "name": "r2"})[1]["result"]
    assert "isError" not in call(url, "add-link", {"session": a, "source": "r1", "target": "r2"})[1]["result"]
    assert errors_of(call(url, "add-link", {"session": b, "source": "r1", "target": "r2"})[1]) == [
        ("arguments.source", "must"), ("arguments.target", "must")]
    assert errors_of(call(url, "add-node", {"session": a, "name": "r1"})[1]) == [("arguments.name", "must")]


def test_argument_errors(url):
    handle = new_session(url)
    call(url, "add-node", {"session": handle, "name": "r1"})
    assert errors_of(call(url, "add-link", {"session": handle, "source": "r1", "target": "r1"})[1]) == [
        ("arguments.target", "must")]
    assert errors_of(call(url, "add-node", {"session": handle})[1]) == [("arguments.name", "mandatory")]
    body = call(url, "add-node", {"session": handle, "name": "r2", "colour": "red"})[1]
    assert ("arguments.colour", "unknown-field") in errors_of(body)


def test_no_path_is_a_tool_failure(url):
    handle = new_session(url)
    for n in ("r1", "r2"):
        call(url, "add-node", {"session": handle, "name": n})
    result = call(url, "find-path", {"session": handle, "from": "r1", "to": "r2"})[1]["result"]
    assert result["isError"] is True and "no path from r1 to r2" in result["content"][0]["text"]
