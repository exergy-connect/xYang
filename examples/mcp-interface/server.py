"""A minimal MCP server for the topology tools, checked by xYang.

Speaks JSON-RPC 2.0 over stdio, one JSON message per line, and handles
initialize, ping, tools/list and tools/call. No MCP SDK is needed.

Each tools/call is checked with xYang rpc validation (xYang #151):

  1. the arguments, as the tool's rpc input, with the session record as
     context, so rules can reach earlier calls;
  2. the tool runs;
  3. a structured result, as the rpc's output, with the same context;
  4. the call is appended to the record, and the whole record is
     validated. This catches rules that compare a result with its own
     arguments, which an rpc output cannot see.

The record is therefore always a valid session (see session/valid.json).

Errors follow MCP 2025-11-25, "Tools > Error Handling":

  Protocol errors (JSON-RPC "error", the call is not run):
    -32700  the line is not JSON
    -32600  not a JSON-RPC 2.0 request
    -32601  unknown method
    -32602  malformed tools/call params, or an unknown tool
    -32603  the server produced a result its own model rejects

  Tool execution errors (a normal "result" with "isError": true):
    - the arguments fail the tool's inputSchema or a session rule. The text
      names each argument and says what is wrong, so the model can retry.
      "_meta" carries the same errors as data. The call is not recorded.
    - the arguments are valid but the tool cannot do it (find-path finds no
      path). The call is recorded with status "error".

Run:  python server.py        (reads requests on stdin)
"""

from __future__ import annotations

import copy
import inspect
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any

from xyang import YangValidator, parse_yang_file, validate

from compile_mcp import compile_tools

HERE = Path(__file__).resolve().parent
MODELS = HERE / "models"
MODULE_PATH = MODELS / "example-topology-tools@2026-11-11.yang"
MODULE = "example-topology-tools"
ROOT = f"{MODULE}:session"
PROTOCOL_VERSION = "2025-11-25"
SERVER_INFO = {"name": "topology-builder", "version": "0.1.0"}
ERRORS_META_KEY = "xyang/errors"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


# validate(module, data, rpc=, direction=, context=), added in xYang #151.
RPC_VALIDATION = "rpc" in inspect.signature(validate).parameters


class ToolFailed(Exception):
    """The arguments were valid, but the tool could not do what was asked."""


class ProtocolError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code, self.message, self.data = code, message, data


class TopologyServer:
    def __init__(self, caller: str = "stdio-client", snapshot: str = "0" * 64) -> None:
        if not RPC_VALIDATION:
            raise RuntimeError("server.py needs an xYang with rpc validation (validate(..., rpc=...)): "
                               "https://github.com/exergy-connect/xYang/pull/151")
        self.module = parse_yang_file(MODULE_PATH, include_path=(str(MODELS),))
        self.validator = YangValidator(self.module)
        self.tools = {t["name"]: t for t in compile_tools(MODULE_PATH, (MODELS,), "standard")["tools"]}
        self.session: dict[str, Any] = {
            ROOT: {
                "protocol-version": PROTOCOL_VERSION,
                "server": dict(SERVER_INFO),
                "view": {"caller": caller, "snapshot": snapshot},
                "call": [],
            }
        }
        self.next_id = 1

    # ---- JSON-RPC ---------------------------------------------------------

    def handle_line(self, line: str) -> dict[str, Any] | None:
        try:
            message = json.loads(line)
        except json.JSONDecodeError as e:
            return _error(None, PARSE_ERROR, f"Parse error: {e.msg}")
        return self.handle(message)

    def handle(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            rid = message.get("id") if isinstance(message, dict) else None
            return _error(rid, INVALID_REQUEST, "Invalid request: expected a JSON-RPC 2.0 request object")
        if "id" not in message:
            return None  # notification, e.g. notifications/initialized
        rid, method, params = message["id"], message["method"], message.get("params") or {}
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": dict(SERVER_INFO),
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": list(self.tools.values())}
            elif method == "tools/call":
                result = self.call_tool(params)
            else:
                raise ProtocolError(METHOD_NOT_FOUND, f"Method not found: {method}")
        except ProtocolError as e:
            return _error(rid, e.code, e.message, e.data)
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    # ---- tools/call -------------------------------------------------------

    def call_tool(self, params: Any) -> dict[str, Any]:
        if not isinstance(params, dict):
            raise ProtocolError(INVALID_PARAMS, "Invalid params: expected an object")
        name = params.get("name")
        if not isinstance(name, str):
            raise ProtocolError(INVALID_PARAMS, "Invalid params: 'name' must be a string")
        if name not in self.tools:
            raise ProtocolError(INVALID_PARAMS, f"Unknown tool: {name}")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ProtocolError(INVALID_PARAMS, "Invalid params: 'arguments' must be an object")

        # 1. Gate: the arguments are the rpc's input, checked against the session so far.
        errors = self._rpc_errors(name, "input", arguments, label="arguments")
        if errors:
            return _tool_error(name, errors)

        # 2. Run the tool. The model already guarantees the arguments make sense.
        call = {"id": self.next_id, "tool": f"{MODULE}:{name}", "arguments": {name: copy.deepcopy(arguments)}}
        try:
            structured = self._execute(name, arguments)
        except ToolFailed as e:
            # A business-logic failure: record it, and tell the model.
            self._record(call | {"result": {"status": "error", "message": str(e)}})
            return {"content": [{"type": "text", "text": f"{name} failed: {e}"}], "isError": True}

        # 3. Check what the server is about to return: the rpc's output, against the session so far.
        if structured is not None:
            bad = self._rpc_errors(name, "output", structured, label="result")
            if bad:
                raise ProtocolError(INTERNAL_ERROR, f"Internal error: {name} produced a result the model rejects",
                                    {ERRORS_META_KEY: bad})

        # 4. Keep the call. Rules that compare a result with its own arguments
        #    (a path contains its from and to) can only be checked here, because an
        #    rpc output cannot see its input (RFC 7950, section 6.4.1).
        result: dict[str, Any] = {"status": "ok"}
        if name == "find-path":
            result["find-path"] = structured
        bad = self._record(call | {"result": result})
        if bad:
            raise ProtocolError(INTERNAL_ERROR, f"Internal error: {name} produced a result the model rejects",
                                {ERRORS_META_KEY: bad})
        return _tool_ok(structured)

    def _rpc_errors(self, name: str, direction: str, body: dict[str, Any], *, label: str) -> list[dict[str, str]]:
        """Validate an rpc input or output with the session record as context."""
        verdict = validate(
            self.module,
            {f"{MODULE}:{direction}": body},
            rpc=name,
            direction=direction,
            context=self.session,
        )
        return [_relative(e, f"/{MODULE}:{direction}", label) for e in verdict["errors"]]

    def _record(self, call: dict[str, Any]) -> list[dict[str, str]]:
        """Append the call if the whole record stays valid; else return the errors on that call."""
        doc = copy.deepcopy(self.session)
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
        self.session = doc
        self.next_id += 1
        return []

    def _execute(self, name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        calls = self.session[ROOT]["call"]
        if name == "add-node":
            return {"name": args["name"]}
        if name == "add-link":
            return None
        # find-path: breadth-first search over the links added so far.
        neighbours: dict[str, set[str]] = {}
        for c in calls:
            link = c["arguments"].get("add-link")
            if link:
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


def _tool_ok(structured: dict[str, Any] | None) -> dict[str, Any]:
    if structured is None:
        return {"content": [{"type": "text", "text": "ok"}]}
    # Structured result plus the same JSON as text, for older clients (MCP 2025-11-25, "Structured Content").
    return {"content": [{"type": "text", "text": json.dumps(structured)}], "structuredContent": structured}


def _tool_error(name: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    lines = [f"{name} was not run: its arguments break {len(errors)} rule{'s' if len(errors) != 1 else ''}."]
    lines += [f"- {e['path']}: {e['message']}" for e in errors]
    lines.append("Fix the arguments and call the tool again.")
    return {
        "content": [{"type": "text", "text": "\n".join(lines)}],
        "isError": True,
        "_meta": {ERRORS_META_KEY: errors},
    }


def main() -> int:
    server = TopologyServer()
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
