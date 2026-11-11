"""A sample agent that drives the topology MCP server (revision 2026-07-28).

The agent is deliberately simple and deterministic, so the run is repeatable:
it has a plan, makes its calls in a careless order, and repairs each mistake
from the structured errors the server returns. No LLM is involved; the point
is what an agent can do with an isError result that names the argument and
the rule it broke.

Transports, chosen from the target:

  python agent_client.py stdio                         spawn server.py, JSON-RPC over stdin/stdout
  python agent_client.py http://127.0.0.1:8787/mcp     Streamable HTTP over HTTP/1.1 (local server.py --http)
  python agent_client.py https://<host>/mcp            Streamable HTTP over HTTP/3 (QUIC), e.g. the Worker
  python agent_client.py https://<host>/mcp --http1    the same over HTTP/1.1

HTTP/3 needs `pip install aioquic`. On HTTP, every POST carries the headers
MCP 2026-07-28 requires: MCP-Protocol-Version, Mcp-Method, Mcp-Name, and one
Mcp-Param-<name> for each argument a tool marks with x-mcp-header (here the
session handle, as Mcp-Param-Session).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import itertools
import json
import re
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
PROTOCOL_VERSION = "2026-07-28"
CLIENT_INFO = {"name": "topology-agent", "version": "0.2.0"}
ERRORS_META_KEY = "xyang/errors"
HEADER_SAFE = re.compile(r"^[\x21-\x7e]([\x20-\x7e\t]*[\x21-\x7e])?$")


class McpError(Exception):
    """A JSON-RPC error response, with the HTTP status when there was one."""

    def __init__(self, error: dict[str, Any], status: int | None = None) -> None:
        super().__init__(f"{error.get('code')}: {error.get('message')}")
        self.code, self.message, self.data, self.status = error.get("code"), error.get("message"), error.get("data"), status


# ---- transports --------------------------------------------------------------

class StdioTransport:
    def __init__(self, command: list[str]) -> None:
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=HERE)
        self.name = "stdio"

    def send(self, message: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise ConnectionError("server closed stdout")
        return json.loads(line)

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.wait(timeout=10)


def _read_body(content_type: str, body: bytes, rid: Any) -> dict[str, Any]:
    """A single JSON object, or an SSE stream whose final event is the response."""
    if content_type.startswith("text/event-stream"):
        response = None
        for event in body.decode().split("\n\n"):
            data = "\n".join(line[5:].lstrip() for line in event.splitlines() if line.startswith("data:"))
            if data:
                msg = json.loads(data)
                if msg.get("id") == rid and ("result" in msg or "error" in msg):
                    response = msg
        if response is None:
            raise ConnectionError("SSE stream ended without a response")
        return response
    return json.loads(body)


class Http1Transport:
    def __init__(self, url: str, insecure: bool = False) -> None:
        self.url = url
        self.name = "HTTP/1.1"
        self.context = ssl._create_unverified_context() if insecure else None

    def send(self, message: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        req = urllib.request.Request(self.url, data=json.dumps(message).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30, context=self.context) as resp:
                return _read_body(resp.headers.get("Content-Type", ""), resp.read(), message["id"])
        except urllib.error.HTTPError as e:
            body = e.read()
            try:
                return json.loads(body) | {"_http_status": e.code}
            except json.JSONDecodeError:
                raise ConnectionError(f"HTTP {e.code} without a JSON-RPC body") from e

    def close(self) -> None:
        pass


class Http3Transport:
    """Streamable HTTP over one persistent HTTP/3 (QUIC) connection, via aioquic."""

    def __init__(self, url: str, insecure: bool = False) -> None:
        try:
            from aioquic.asyncio.protocol import QuicConnectionProtocol
            from aioquic.quic.connection import QuicConnection
            from aioquic.h3.connection import H3_ALPN, H3Connection
            from aioquic.h3.events import DataReceived, HeadersReceived
            from aioquic.quic.configuration import QuicConfiguration
        except ImportError as e:
            raise SystemExit("HTTP/3 needs aioquic: pip install aioquic (or pass --http1)") from e

        parts = urlsplit(url)
        self.host, self.port = parts.hostname or "", parts.port or 443
        self.authority = parts.netloc
        self.path = parts.path or "/"
        self.name = "HTTP/3"
        self.loop = asyncio.new_event_loop()

        class H3Client(QuicConnectionProtocol):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                self.http = H3Connection(self._quic)
                self.pending: dict[int, tuple[asyncio.Future, list[Any]]] = {}

            def quic_event_received(self, event: Any) -> None:
                for h3 in self.http.handle_event(event):
                    entry = self.pending.get(getattr(h3, "stream_id", -1))
                    if entry is None:
                        continue
                    entry[1].append(h3)
                    if getattr(h3, "stream_ended", False):
                        del self.pending[h3.stream_id]
                        entry[0].set_result(entry[1])

            async def post(self, authority: str, path: str, headers: dict[str, str], body: bytes) -> tuple[int, str, bytes]:
                stream = self._quic.get_next_available_stream_id()
                self.http.send_headers(stream, [
                    (b":method", b"POST"), (b":scheme", b"https"),
                    (b":authority", authority.encode()), (b":path", path.encode()),
                    *[(k.lower().encode(), v.encode()) for k, v in headers.items()],
                ])
                self.http.send_data(stream, body, end_stream=True)
                done: asyncio.Future = self._loop.create_future()
                self.pending[stream] = (done, [])
                self.transmit()
                events = await asyncio.wait_for(done, timeout=30)
                status, content_type, data = 0, "", b""
                for ev in events:
                    if isinstance(ev, HeadersReceived):
                        for k, v in ev.headers:
                            if k == b":status":
                                status = int(v)
                            elif k == b"content-type":
                                content_type = v.decode()
                    elif isinstance(ev, DataReceived):
                        data += ev.data
                return status, content_type, data

        config = QuicConfiguration(is_client=True, alpn_protocols=H3_ALPN, server_name=self.host)
        if insecure:
            config.verify_mode = ssl.CERT_NONE
        async def open_connection() -> Any:
            # Like aioquic.asyncio.client.connect, but falls back to an IPv4 socket on
            # hosts without IPv6 (aioquic always opens a dual-stack IPv6 socket).
            loop = asyncio.get_running_loop()
            infos = await loop.getaddrinfo(self.host, self.port, type=socket.SOCK_DGRAM)
            addr = infos[0][4]
            try:
                sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                sock.bind(("::", 0, 0, 0))
                if len(addr) == 2:
                    addr = ("::ffff:" + addr[0], addr[1], 0, 0)
            except OSError:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.bind(("0.0.0.0", 0))
                addr = next(i[4] for i in infos if i[0] == socket.AF_INET)
            self.transport, protocol = await loop.create_datagram_endpoint(
                lambda: H3Client(QuicConnection(configuration=config)), sock=sock)
            protocol.connect(addr)
            await protocol.wait_connected()
            return protocol

        self.client = self.loop.run_until_complete(open_connection())

    def send(self, message: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        status, content_type, body = self.loop.run_until_complete(
            self.client.post(self.authority, self.path, headers, json.dumps(message).encode())
        )
        if status >= 400:
            try:
                return json.loads(body) | {"_http_status": status}
            except json.JSONDecodeError:
                raise ConnectionError(f"HTTP {status} without a JSON-RPC body") from None
        return _read_body(content_type, body, message["id"])

    def close(self) -> None:
        async def shutdown() -> None:
            self.client.close()
            await self.client.wait_closed()
            self.transport.close()

        self.loop.run_until_complete(shutdown())
        self.loop.close()


# ---- MCP client ----------------------------------------------------------------

def encode_header(value: str) -> str:
    """Plain if header-safe ASCII, else the =?base64?...?= sentinel (Streamable HTTP, "Value Encoding")."""
    if HEADER_SAFE.match(value) and not (value.startswith("=?base64?") and value.endswith("?=")):
        return value
    return "=?base64?" + base64.b64encode(value.encode()).decode() + "?="


class McpClient:
    def __init__(self, transport: Any) -> None:
        self.transport = transport
        self.ids = itertools.count(1)
        self.tools: dict[str, dict[str, Any]] = {}

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(params or {})
        params["_meta"] = {
            "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
            "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
            "io.modelcontextprotocol/clientCapabilities": {},
        }
        message = {"jsonrpc": "2.0", "id": next(self.ids), "method": method, "params": params}
        response = self.transport.send(message, self._headers(method, params))
        if "error" in response:
            raise McpError(response["error"], response.get("_http_status"))
        return response["result"]

    def _headers(self, method: str, params: dict[str, Any]) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "Mcp-Method": method,
        }
        if method == "tools/call":
            headers["Mcp-Name"] = encode_header(params["name"])
            arguments = params.get("arguments") or {}
            schema = self.tools.get(params["name"], {}).get("inputSchema", {})
            for prop, spec in schema.get("properties", {}).items():
                value = arguments.get(prop)
                if spec.get("x-mcp-header") and value is not None:
                    text = str(value).lower() if isinstance(value, bool) else str(value)
                    headers[f"Mcp-Param-{spec['x-mcp-header']}"] = encode_header(text)
        return headers

    def discover(self) -> dict[str, Any]:
        return self.request("server/discover")

    def list_tools(self) -> list[dict[str, Any]]:
        tools = self.request("tools/list")["tools"]
        self.tools = {t["name"]: t for t in tools}
        return tools

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})


# ---- the agent -----------------------------------------------------------------

@dataclass
class Step:
    tool: str
    arguments: dict[str, Any]


# Built in a careless order: the first link names two nodes that do not exist yet.
# The server's errors say which arguments are wrong and why, and the agent repairs them.
PLAN = [
    Step("add-link", {"source": "r1", "target": "r2"}),
    Step("add-node", {"name": "h1", "role": "host"}),
    Step("add-link", {"source": "r2", "target": "h1", "bandwidth-mbps": 100}),
    Step("find-path", {"from": "r1", "to": "h1", "max-hops": 4}),
]
NODE_ARGUMENTS = {"source", "target", "from", "to"}


class Agent:
    def __init__(self, client: McpClient, out: Any = sys.stdout) -> None:
        self.client = client
        self.out = out
        self.session: str | None = None
        self.calls = 0
        self.repairs = 0

    def say(self, text: str) -> None:
        print(text, file=self.out, flush=True)

    def run(self) -> dict[str, Any]:
        info = self.client.discover()
        server = info.get("_meta", {}).get("io.modelcontextprotocol/serverInfo", {})
        self.say(f"server   {server.get('name')} {server.get('version')}, versions {info['supportedVersions']}, "
                 f"over {self.client.transport.name}")
        tools = self.client.list_tools()
        headers = sorted({p["x-mcp-header"] for t in tools for p in t["inputSchema"].get("properties", {}).values()
                          if "x-mcp-header" in p})
        self.say(f"tools    {', '.join(t['name'] for t in tools)} (mirrored headers: {', '.join(headers)})")
        self.open_session()
        result: dict[str, Any] = {}
        for step in PLAN:
            result = self.attempt(step.tool, step.arguments)
        self.say(f"done     {self.calls} calls, {self.repairs} repairs, path {' -> '.join(result.get('hop', []))}")
        return result

    def open_session(self) -> None:
        self.session = self.client.call("open-session", {})["structuredContent"]["session"]
        self.calls += 1
        self.say(f"session  {self.session}")

    def attempt(self, tool: str, arguments: dict[str, Any], depth: int = 0) -> dict[str, Any]:
        if depth > 3:
            raise RuntimeError(f"giving up on {tool}: too many repairs")
        args = {"session": self.session, **arguments}
        self.say(f"{'  ' * depth}-> {tool} {json.dumps(arguments)}")
        result = self.client.call(tool, args)
        self.calls += 1
        if not result.get("isError"):
            if "structuredContent" in result:
                self.say(f"{'  ' * depth}<- {json.dumps(result['structuredContent'])}")
            return result.get("structuredContent", {})
        errors = result.get("_meta", {}).get(ERRORS_META_KEY, [])
        for e in errors:
            self.say(f"{'  ' * depth}<- isError {e['path']}: {e['message']}")
        if not errors:
            raise RuntimeError(result["content"][0]["text"])
        # Repair from the structured errors, then retry the same call.
        for e in errors:
            field = e["path"].removeprefix("arguments.")
            if e["code"] == "unknown-session":
                self.repairs += 1
                self.say(f"{'  ' * depth}   repair: start a new session")
                self.open_session()
            elif e["code"] == "must" and field in NODE_ARGUMENTS and "add-node" in e["message"]:
                self.repairs += 1
                self.say(f"{'  ' * depth}   repair: create node {arguments[field]!r} first")
                self.attempt("add-node", {"name": arguments[field]}, depth + 1)
            else:
                raise RuntimeError(f"no repair for {e['path']}: {e['message']}")
        return self.attempt(tool, arguments, depth)


def make_transport(target: str, http1: bool, insecure: bool) -> Any:
    if target == "stdio":
        return StdioTransport([sys.executable, str(HERE / "server.py")])
    if target.startswith("http://") or (target.startswith("https://") and http1):
        return Http1Transport(target, insecure)
    if target.startswith("https://"):
        return Http3Transport(target, insecure)
    raise SystemExit(f"target must be 'stdio', http://... or https://...: {target}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sample agent for the topology MCP server (2026-07-28)")
    ap.add_argument("target", help="'stdio', http://host:port/mcp, or https://host/mcp (HTTP/3)")
    ap.add_argument("--http1", action="store_true", help="use HTTP/1.1 for an https:// target")
    ap.add_argument("--insecure", action="store_true", help="skip TLS certificate checks (local testing only)")
    args = ap.parse_args(argv)
    transport = make_transport(args.target, args.http1, args.insecure)
    try:
        Agent(McpClient(transport)).run()
    finally:
        transport.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
