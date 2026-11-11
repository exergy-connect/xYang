"""The sample agent completes its plan over every transport: stdio, HTTP/1.1 and HTTP/3.

Run: python -m pytest examples/mcp-interface/test_agent.py -q
HTTP/3 needs aioquic (pip install aioquic); without it that test is skipped.
"""

from __future__ import annotations

import asyncio
import io
import socket
import sys
import threading
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from agent_client import Agent, Http1Transport, McpClient, McpError, StdioTransport, make_transport  # noqa: E402
from server import RPC_VALIDATION, TopologyServer, serve_http  # noqa: E402

pytestmark = pytest.mark.skipif(
    not RPC_VALIDATION,
    reason="needs an xYang with rpc validation: https://github.com/exergy-connect/xYang/pull/151",
)


def free_port(kind: int = socket.SOCK_STREAM) -> int:
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_agent(transport) -> tuple[dict, str]:
    out = io.StringIO()
    try:
        result = Agent(McpClient(transport), out).run()
    finally:
        transport.close()
    return result, out.getvalue()


def check_run(result: dict, log: str, transport_name: str) -> None:
    assert result == {"hop": ["r1", "r2", "h1"]}
    assert f"over {transport_name}" in log
    assert "mirrored headers: Session" in log
    assert log.count("repair: create node") == 2
    assert "done     8 calls, 2 repairs, path r1 -> r2 -> h1" in log


def test_agent_over_stdio():
    check_run(*run_agent(StdioTransport([sys.executable, str(HERE / "server.py")])), "stdio")


@pytest.fixture(scope="module")
def http_url():
    port = free_port()
    threading.Thread(target=serve_http, args=(TopologyServer(), "127.0.0.1", port), daemon=True).start()
    url = f"http://127.0.0.1:{port}/mcp"
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return url
        except OSError:
            asyncio.run(asyncio.sleep(0.1))
    raise RuntimeError("HTTP server did not start")


def test_agent_over_http1(http_url):
    check_run(*run_agent(Http1Transport(http_url)), "HTTP/1.1")


def test_http_client_sends_the_required_headers(http_url):
    # A client that drops Mcp-Param-Session is rejected with HeaderMismatch.
    client = McpClient(Http1Transport(http_url))
    client.list_tools()
    handle = client.call("open-session", {})["structuredContent"]["session"]
    original = client._headers
    client._headers = lambda method, params: {k: v for k, v in original(method, params).items()
                                              if k != "Mcp-Param-Session"}
    with pytest.raises(McpError) as e:
        client.call("add-node", {"session": handle, "name": "r1"})
    assert (e.value.status, e.value.code) == (400, -32020)


def test_agent_over_http3():
    pytest.importorskip("aioquic")
    import h3_dev_server

    port = free_port(socket.SOCK_DGRAM)
    loop = asyncio.new_event_loop()
    ready, stop = asyncio.Event(), asyncio.Event()

    def serve() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(h3_dev_server.run("127.0.0.1", port, ready, stop))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    for _ in range(100):
        if ready.is_set():
            break
        threading.Event().wait(0.05)
    try:
        transport = make_transport(f"https://127.0.0.1:{port}/mcp", http1=False, insecure=True)
        check_run(*run_agent(transport), "HTTP/3")
    finally:
        loop.call_soon_threadsafe(stop.set)
        thread.join(timeout=10)
