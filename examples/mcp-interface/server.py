"""A minimal MCP server (revision 2026-07-28) for the topology tools, checked by xYang.

Two transports, one server:

  python server.py                       stdio: one JSON-RPC message per line
  python server.py --http 127.0.0.1:8787 Streamable HTTP: POST /mcp

No MCP SDK is needed. The cloud version (worker/) follows the same rules.

MCP 2026-07-28 is stateless: there is no initialize handshake and no protocol
session. Every request carries its protocol version in params._meta, and a
server that keeps state across calls mints a handle from a creation tool.
Here, open-session mints the handle and every other tool takes it as its
'session' argument (mirrored into the Mcp-Param-Session header on HTTP).

Each handle keys one session record (see session/valid.json). A tools/call is:

  1. checked as the tool's rpc input, with that record as context, so its
     rules can reach earlier calls (xYang rpc validation);
  2. run;
  3. a structured result is checked as the rpc's output, same context;
  4. appended to the record, and the whole record validated. This catches
     result rules that need the arguments, which an rpc output cannot see.

Errors follow MCP 2026-07-28 ("Tools > Error Handling", "Versioning",
"Streamable HTTP"):

  JSON-RPC errors (the call is not run):
    -32700  not JSON                    -32600  not a JSON-RPC 2.0 request
    -32601  unknown method              -32602  malformed params, unknown tool,
    -32022  unsupported protocol version        missing _meta protocol version
    -32020  HTTP headers missing or not matching the body (HTTP only)
    -32603  the server's own result or record breaks the model

  Tool execution errors (a result with "isError": true):
    - the arguments break the tool's schema or a session rule: one line per
      argument, and the same errors as data in _meta["xyang/errors"]. Not
      recorded.
    - the session handle is unknown or expired: start a new session.
    - valid arguments the tool cannot satisfy (no path): recorded as failed.
"""

from __future__ import annotations

import argparse
import base64
import copy
import inspect
import json
import re
import secrets
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from xyang import YangValidator, parse_yang_file, validate

from compile_mcp import compile_tools

HERE = Path(__file__).resolve().parent
MODELS = HERE / "models"
MODULE_PATH = MODELS / "example-topology-tools@2026-11-11.yang"
MODULE = "example-topology-tools"
ROOT = f"{MODULE}:session"

PROTOCOL_VERSION = "2026-07-28"
SUPPORTED_VERSIONS = [PROTOCOL_VERSION]
SERVER_INFO = {"name": "topology-builder", "version": "0.2.0"}
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
ERRORS_META_KEY = "xyang/errors"
INSTRUCTIONS = (
    "Call open-session first and pass the returned handle as 'session' on every other call. "
    "Add nodes before linking them. When a call returns isError, read which argument broke "
    "which rule, fix it, and call again."
)
SESSION_TTL_SECONDS = 24 * 3600
LIST_TTL_MS = 300_000

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
HEADER_MISMATCH = -32020
UNSUPPORTED_VERSION = -32022

# validate(module, data, rpc=, direction=, context=), added in xYang #151.
RPC_VALIDATION = "rpc" in inspect.signature(validate).parameters


class ToolFailed(Exception):
    """The arguments were valid, but the tool could not do what was asked."""


class ProtocolError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code, self.message, self.data = code, message, data


@dataclass
class Session:
    record: dict[str, Any]
    last_used: float
    next_id: int = 1
    extra: dict[str, Any] = field(default_factory=dict)


class TopologyServer:
    def __init__(self, caller: str = "local-client", clock: Callable[[], float] = time.time) -> None:
        if not RPC_VALIDATION:
            raise RuntimeError("server.py needs an xYang with rpc validation (validate(..., rpc=...)): "
                               "https://github.com/exergy-connect/xYang/pull/151")
        self.module = parse_yang_file(MODULE_PATH, include_path=(str(MODELS),))
        self.validator = YangValidator(self.module)
        # Deterministic order (MCP 2026-07-28 SHOULD): the rpc order in the module.
        self.tool_list = compile_tools(MODULE_PATH, (MODELS,), "standard")["tools"]
        self.tools = {t["name"]: t for t in self.tool_list}
        self.caller = caller
        self.clock = clock
        self.sessions: dict[str, Session] = {}

    # ---- JSON-RPC ---------------------------------------------------------

    def handle_line(self, line: str) -> dict[str, Any] | None:
        try:
            message = json.loads(line)
        except json.JSONDecodeError as e:
            return _error(None, PARSE_ERROR, f"Parse error: {e.msg}")
        return self.handle(message)

    def handle(self, message: Any) -> dict[str, Any] | None:
        if not _is_request_or_notification(message):
            rid = message.get("id") if isinstance(message, dict) else None
            return _error(rid, INVALID_REQUEST, "Invalid request: expected a JSON-RPC 2.0 request object")
        if "id" not in message:
            return None  # notifications: this revision defines none that this server needs
        rid, method = message["id"], message["method"]
        try:
            params = message.get("params", {})
            if not isinstance(params, dict):
                raise ProtocolError(INVALID_PARAMS, "Invalid params: expected an object")
            check_version(params)
            if method == "server/discover":
                result = {
                    "supportedVersions": SUPPORTED_VERSIONS,
                    "capabilities": {"tools": {}},
                    "instructions": INSTRUCTIONS,
                    "ttlMs": LIST_TTL_MS,
                    "cacheScope": "public",
                }
            elif method == "tools/list":
                result = {"tools": self.tool_list, "ttlMs": LIST_TTL_MS, "cacheScope": "public"}
            elif method == "tools/call":
                result = self.call_tool(params)
            else:
                raise ProtocolError(METHOD_NOT_FOUND, f"Method not found: {method}")
        except ProtocolError as e:
            return _error(rid, e.code, e.message, e.data)
        result = {"resultType": "complete", **result}
        result["_meta"] = {**result.get("_meta", {}), META_SERVER_INFO: dict(SERVER_INFO)}
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    # ---- tools/call -------------------------------------------------------

    def call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str):
            raise ProtocolError(INVALID_PARAMS, "Invalid params: 'name' must be a string")
        if name not in self.tools:
            raise ProtocolError(INVALID_PARAMS, f"Unknown tool: {name}")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ProtocolError(INVALID_PARAMS, "Invalid params: 'arguments' must be an object")

        if name == "open-session":
            errors = self._rpc_errors(name, "input", arguments, label="arguments", context=None)
            if errors:
                return _tool_error(name, errors)
            handle = "ses_" + secrets.token_hex(16)
            self.sessions[handle] = Session(record=self._new_record(handle), last_used=self.clock())
            out = {"session": handle}
            bad = self._rpc_errors(name, "output", out, label="result", context=None)
            if bad:
                raise ProtocolError(INTERNAL_ERROR, "Internal error: open-session minted an invalid handle",
                                    {ERRORS_META_KEY: bad})
            return _tool_ok(out, f"Started session {handle}. Pass it as 'session' on every call.")

        session = self._session(arguments.get("session"))
        if session is None:
            return _unknown_session(name, arguments.get("session"))

        # 1. Gate: the arguments are the rpc's input, checked against this session's record.
        errors = self._rpc_errors(name, "input", arguments, label="arguments", context=session.record)
        if errors:
            return _tool_error(name, errors)

        # 2. Run the tool. The model already guarantees the arguments make sense.
        call = {"id": session.next_id, "tool": f"{MODULE}:{name}", "arguments": {name: copy.deepcopy(arguments)}}
        try:
            structured = self._execute(session, name, arguments)
        except ToolFailed as e:
            # A business-logic failure: record it, and tell the model.
            self._record(session, call | {"result": {"status": "error", "message": str(e)}})
            return {"content": [{"type": "text", "text": f"{name} failed: {e}"}], "isError": True}

        # 3. Check what the server is about to return: the rpc's output, same context.
        if structured is not None:
            bad = self._rpc_errors(name, "output", structured, label="result", context=session.record)
            if bad:
                raise ProtocolError(INTERNAL_ERROR, f"Internal error: {name} produced a result the model rejects",
                                    {ERRORS_META_KEY: bad})

        # 4. Keep the call. Rules that compare a result with its own arguments
        #    (a path contains its from and to) can only be checked here, because an
        #    rpc output cannot see its input (RFC 7950, section 6.4.1).
        result: dict[str, Any] = {"status": "ok"}
        if name == "find-path":
            result["find-path"] = structured
        bad = self._record(session, call | {"result": result})
        if bad:
            raise ProtocolError(INTERNAL_ERROR, f"Internal error: {name} produced a result the model rejects",
                                {ERRORS_META_KEY: bad})
        return _tool_ok(structured)

    def _new_record(self, handle: str) -> dict[str, Any]:
        return {
            ROOT: {
                "handle": handle,
                "protocol-version": PROTOCOL_VERSION,
                "server": dict(SERVER_INFO),
                "view": {"caller": self.caller, "snapshot": "0" * 64},
                "call": [],
            }
        }

    def _session(self, handle: Any) -> Session | None:
        """The live session for a handle; expired ones are dropped (24 hours without a call)."""
        session = self.sessions.get(handle) if isinstance(handle, str) else None
        if session is None:
            return None
        now = self.clock()
        if now - session.last_used > SESSION_TTL_SECONDS:
            del self.sessions[handle]
            return None
        session.last_used = now
        return session

    def _rpc_errors(self, name: str, direction: str, body: dict[str, Any], *, label: str,
                    context: dict[str, Any] | None) -> list[dict[str, str]]:
        """Validate an rpc input or output, with a session record as context.

        xYang validates the context first and marks its errors "document": "context".
        A bad record is the server's fault, never the model's, so it is a -32603.
        """
        kwargs: dict[str, Any] = {"rpc": name, "direction": direction}
        if context is not None:
            kwargs["context"] = context
        verdict = validate(self.module, {f"{MODULE}:{direction}": body}, **kwargs)
        context_errors = [e for e in verdict["errors"] if e.get("document") == "context"]
        if context_errors:
            raise ProtocolError(
                INTERNAL_ERROR,
                "Internal error: the server's session record is invalid",
                {ERRORS_META_KEY: [{k: e[k] for k in ("path", "code", "message")} for e in context_errors]},
            )
        return [_relative(e, f"/{MODULE}:{direction}", label) for e in verdict["errors"]]

    def _record(self, session: Session, call: dict[str, Any]) -> list[dict[str, str]]:
        """Append the call if the whole record stays valid; else return the errors on that call."""
        doc = copy.deepcopy(session.record)
        doc[ROOT]["call"].append(call)
        index = len(doc[ROOT]["call"]) - 1
        name = call["tool"].split(":", 1)[1]
        errors = self.validator.validate_detailed(doc)["errors"]
        if errors:
            out = []
            for e in errors:
                r = _relative(e, f"/{ROOT}/call/{index}/result/{name}", "result")
                if r["path"] == e["path"]:
                    r = _relative(e, f"/{ROOT}/call/{index}", "call")
                out.append(r)
            return out
        session.record = doc
        session.next_id += 1
        return []

    def _execute(self, session: Session, name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        calls = session.record[ROOT]["call"]
        if name == "add-node":
            return {"name": args["name"]}
        if name == "add-link":
            return None
        # find-path: breadth-first search over the links added so far.
        neighbours: dict[str, set[str]] = {}
        for c in calls:
            link = c["arguments"].get("add-link")
            if link and c["result"]["status"] == "ok":
                neighbours.setdefault(link["source"], set()).add(link["target"])
                neighbours.setdefault(link["target"], set()).add(link["source"])
        start, goal, limit = args["from"], args["to"], args.get("max-hops", 8)
        queue, seen = deque([[start]]), {start}
        while queue:
            path = queue.popleft()
            if path[-1] == goal:
                return {"hop": path}
            if len(path) - 1 < limit:
                for nxt in sorted(neighbours.get(path[-1], ())):
                    if nxt not in seen:
                        seen.add(nxt)
                        queue.append(path + [nxt])
        raise ToolFailed(f"no path from {start} to {goal} within {limit} hops")


# ---- helpers shared by both transports --------------------------------------

def _is_request_or_notification(message: Any) -> bool:
    return isinstance(message, dict) and message.get("jsonrpc") == "2.0" and isinstance(message.get("method"), str)


def check_version(params: dict[str, Any]) -> None:
    """Every request declares its protocol version in _meta (MCP 2026-07-28, "Versioning")."""
    meta = params.get("_meta")
    version = meta.get(META_VERSION) if isinstance(meta, dict) else None
    if not isinstance(version, str):
        raise ProtocolError(INVALID_PARAMS, f"Invalid params: _meta['{META_VERSION}'] is required")
    if version not in SUPPORTED_VERSIONS:
        raise ProtocolError(UNSUPPORTED_VERSION, "Unsupported protocol version",
                            {"supported": SUPPORTED_VERSIONS, "requested": version})


def _relative(e: dict[str, Any], prefix: str, label: str) -> dict[str, str]:
    """Turn an xYang path into one relative to the call: /m:input/target -> arguments.target."""
    where = e["path"]
    if where == prefix or where.startswith(prefix + "/"):
        rest = where[len(prefix):].lstrip("/").replace("/", ".")
        where = f"{label}.{rest}" if rest else label
    return {"path": where, "code": e["code"], "message": e["message"]}


def _error(rid: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": rid, "error": err}


def _tool_ok(structured: dict[str, Any] | None, text: str | None = None) -> dict[str, Any]:
    if structured is None:
        return {"content": [{"type": "text", "text": text or "ok"}]}
    # Structured result plus the same JSON as text, for older clients ("Structured Content").
    return {"content": [{"type": "text", "text": text or json.dumps(structured)}], "structuredContent": structured}


def _tool_error(name: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    lines = [f"{name} was not run: its arguments break {len(errors)} rule{'s' if len(errors) != 1 else ''}."]
    lines += [f"- {e['path']}: {e['message']}" for e in errors]
    lines.append("Fix the arguments and call the tool again.")
    return {"content": [{"type": "text", "text": "\n".join(lines)}], "isError": True, "_meta": {ERRORS_META_KEY: errors}}


def _unknown_session(name: str, handle: Any) -> dict[str, Any]:
    # MCP 2026-07-28, "Stateful Tools": an unknown or expired handle is a tool execution error.
    message = "Unknown or expired session. Call open-session to start a new one, then retry with its handle."
    errors = [{"path": "arguments.session", "code": "unknown-session", "message": message}]
    return _tool_error(name, errors)


# ---- Streamable HTTP (MCP 2026-07-28) ---------------------------------------

HEADER_SAFE = re.compile(r"^[\x20-\x7e\t]*$")


def decode_header(value: str) -> str:
    """Undo the =?base64?...?= sentinel encoding of Mcp-Name and Mcp-Param-* values."""
    if value.startswith("=?base64?") and value.endswith("?="):
        return base64.b64decode(value[len("=?base64?"):-2]).decode("utf-8")
    return value


def check_http_headers(headers: Callable[[str], str | None], message: dict[str, Any],
                       tools: dict[str, dict[str, Any]]) -> tuple[int, dict[str, Any]] | None:
    """Server validation of the mirrored headers ("Streamable HTTP > Server Validation").

    Returns (HTTP status, JSON-RPC error response) on failure, else None.
    """
    rid = message.get("id")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}

    def mismatch(text: str) -> tuple[int, dict[str, Any]]:
        return 400, _error(rid, HEADER_MISMATCH, f"Header mismatch: {text}")

    version = headers("MCP-Protocol-Version")
    if version is None:
        return mismatch("MCP-Protocol-Version header is required")
    meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
    if meta.get(META_VERSION) != version:
        return mismatch(f"MCP-Protocol-Version header {version!r} does not match body _meta value {meta.get(META_VERSION)!r}")
    if version not in SUPPORTED_VERSIONS:
        return 400, _error(rid, UNSUPPORTED_VERSION, "Unsupported protocol version",
                           {"supported": SUPPORTED_VERSIONS, "requested": version})
    method = headers("Mcp-Method")
    if method != message["method"]:
        return mismatch(f"Mcp-Method header {method!r} does not match body method {message['method']!r}")

    if message["method"] in ("tools/call", "resources/read", "prompts/get"):
        source = params.get("name") if message["method"] != "resources/read" else params.get("uri")
        raw = headers("Mcp-Name")
        if raw is None:
            return mismatch("Mcp-Name header is required")
        if not HEADER_SAFE.match(raw):
            return mismatch("Mcp-Name header contains invalid characters")
        if decode_header(raw) != source:
            return mismatch(f"Mcp-Name header value {raw!r} does not match body value {source!r}")

    if message["method"] == "tools/call" and params.get("name") in tools:
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        for prop, schema in tools[params["name"]]["inputSchema"].get("properties", {}).items():
            header = schema.get("x-mcp-header")
            if not header:
                continue
            raw = headers(f"Mcp-Param-{header}")
            value = arguments.get(prop)
            if value is None:
                if raw is not None:
                    return mismatch(f"Mcp-Param-{header} is set but '{prop}' is not in the arguments")
                continue
            if raw is None:
                return mismatch(f"Mcp-Param-{header} header is required when '{prop}' is given")
            if not HEADER_SAFE.match(raw):
                return mismatch(f"Mcp-Param-{header} header contains invalid characters")
            expected = str(value).lower() if isinstance(value, bool) else str(value)
            if decode_header(raw) != expected:
                return mismatch(f"Mcp-Param-{header} header value {raw!r} does not match body value {value!r}")
    return None


def handle_http(server: TopologyServer, method: str, path: str, headers: Callable[[str], str | None],
                body: bytes, allowed_origins: set[str]) -> tuple[int, dict[str, Any] | None, dict[str, str]]:
    """One Streamable HTTP exchange (MCP 2026-07-28): (status, JSON body or None, extra headers).

    Shared by the HTTP/1.1 server below and the HTTP/3 dev server (h3_dev_server.py),
    so both apply the same transport rules.
    """
    if path.split("?", 1)[0] != "/mcp":
        return 404, None, {}
    if method != "POST":
        return 405, None, {"Allow": "POST"}  # no GET stream and no DELETE in 2026-07-28
    origin = headers("Origin")
    if origin is not None and origin not in allowed_origins:
        return 403, {"jsonrpc": "2.0", "error": {"code": INVALID_REQUEST, "message": f"Forbidden origin: {origin}"}}, {}
    try:
        message = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return 400, _error(None, PARSE_ERROR, f"Parse error: {e}"), {}
    if not _is_request_or_notification(message):
        rid = message.get("id") if isinstance(message, dict) else None
        return 400, _error(rid, INVALID_REQUEST, "Invalid request: expected a JSON-RPC 2.0 request object"), {}
    if "id" not in message:
        return 202, None, {}
    failed = check_http_headers(headers, message, server.tools)
    if failed:
        return failed[0], failed[1], {}
    response = server.handle(message)
    code = (response or {}).get("error", {}).get("code")
    return {METHOD_NOT_FOUND: 404, UNSUPPORTED_VERSION: 400}.get(code, 200), response, {}


def serve_http(server: TopologyServer, host: str, port: int) -> None:
    allowed_origins = {f"http://{host}:{port}", f"http://localhost:{port}", f"http://127.0.0.1:{port}"}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            pass

        def _exchange(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            status, payload, extra = handle_http(server, self.command, self.path, self.headers.get, body, allowed_origins)
            data = json.dumps(payload).encode() if payload is not None else b""
            self.send_response(status)
            if payload is not None:
                self.send_header("Content-Type", "application/json")
            for k, v in extra.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_POST = do_GET = do_DELETE = do_PUT = do_PATCH = _exchange

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"MCP {PROTOCOL_VERSION} on http://{host}:{port}/mcp", file=sys.stderr, flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MCP 2026-07-28 topology server checked by xYang")
    ap.add_argument("--http", metavar="HOST:PORT", help="serve Streamable HTTP on POST /mcp instead of stdio")
    args = ap.parse_args(argv)
    server = TopologyServer()
    if args.http:
        host, _, port = args.http.rpartition(":")
        serve_http(server, host or "127.0.0.1", int(port))
        return 0
    for line in sys.stdin:
        if not line.strip():
            continue
        response = server.handle_line(line)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
