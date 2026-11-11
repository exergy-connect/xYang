# MCP interface from YANG: a tool set and a checked session

One YANG source gives two things:

1. **A standard MCP interface.** Each `rpc` compiles into an MCP `tools/list` entry: name, description, `inputSchema`, and `outputSchema` when the rpc has an output. Any MCP client can use it.
2. **A session that is checked against itself.** A record of `tools/call` requests validates with xYang. Each call must agree with the calls before it: a link may only join nodes that an earlier successful call created, and a path may only pass through such nodes.

Plain JSON Schema checks each call alone. In this example, 8 of the 12 invalid sessions pass that check, and xYang rejects all 12.

All names and data are synthetic.

## Files

| File | What it is |
| --- | --- |
| [`models/example-mcp@2026-11-11.yang`](models/example-mcp@2026-11-11.yang) | Base: the `tool` identity and the `session` grouping (protocol version, server, the local view, the list of calls) |
| [`models/example-topology-tools@2026-11-11.yang`](models/example-topology-tools@2026-11-11.yang) | A tool set: `add-node`, `add-link`, `find-path` as rpcs, plus the session container and its cross-call rules |
| [`compile_mcp.py`](compile_mcp.py) | rpcs → `tools/list` result, in two profiles |
| [`out/tools-list.json`](out/tools-list.json) | Standard profile: plain JSON Schema |
| [`out/tools-list.xyang.json`](out/tools-list.xyang.json) | xYang profile: the same schemas with `x-yang` kept |
| [`session/valid.json`](session/valid.json) | Seven calls that build a three-node topology and find a path |
| [`session/invalid/`](session/invalid/) | One mutation of the valid session per rule, made by [`build_fixtures.py`](build_fixtures.py) |
| [`session/expected-errors.json`](session/expected-errors.json) | The exact xYang errors for every fixture |
| [`check.py`](check.py) | End-to-end check (see below) |
| [`server.py`](server.py) | A minimal MCP server over stdio that checks every `tools/call` with xYang before running it |
| [`test_server.py`](test_server.py) | One test per error kind, plus a stdio round trip |

## How one tool is declared

Each tool is one grouping, used in three places:

```yang
grouping add-link-input { leaf source {...} leaf target { must ". != ../source"; ... } leaf bandwidth-mbps {...} }

rpc add-link { input { uses add-link-input; } }        // → MCP tool and its inputSchema

identity add-link { base mcp:tool; }                   // → a value a call's 'tool' may name

augment "/topo:session/topo:call/topo:arguments" {      // → arguments of a call in a session
  container add-link {
    when "derived-from-or-self(../../tool, 'topo:add-link')";
    uses add-link-input { refine source { must "<an earlier successful add-node created it>"; } ... }
  }
}
```

Rules about one call's own arguments, such as "no self-loop", sit in the grouping, so they travel with the tool's `inputSchema` in the xYang profile. Rules that need other calls sit in the session, because that is where the other calls are.

## Mapping

| YANG | MCP `tools/list` |
| --- | --- |
| `rpc` name | `name` |
| `rpc` description | `description` |
| `rpc input` | `inputSchema` (`type: object`, with the `$defs` it references) |
| `rpc output` | `outputSchema` |
| `mandatory true` | `required` |
| `range`, `pattern`, `enumeration`, `default` | `minimum`/`maximum`, `pattern`, `enum`, `default` |
| `must`, `when`, `leafref` | `x-yang` (xYang profile only; generic validators ignore it) |

## Session rules

| Rule | Where | Fixture |
| --- | --- | --- |
| A call names a declared tool | `tool` is an identityref with base `mcp:tool` | `undeclared-tool` |
| A call carries exactly its own tool's arguments | base: `count(*) = 1` on `arguments`; tools: `when` on each argument container | `arguments-for-other-tool`, `missing-arguments` |
| A node name is added successfully at most once | `add-node/name` | `duplicate-node` |
| A link joins two different nodes | grouping: `target != source` | `self-loop` |
| Link ends, path ends and path hops are nodes that an earlier successful `add-node` created | `must` joins on `id <` and `status = 'ok'` | `hallucinated-link-target`, `link-before-node`, `link-to-failed-node`, `hallucinated-path-hop` |
| A path contains its `from` and `to` and is at most `max-hops` long | `find-path` result | `path-missing-endpoint`, `path-too-long` |
| Argument types and ranges | YANG types | `bandwidth-out-of-range` |

Instance data is RFC 7951 JSON. The root is `example-topology-tools:session`. Nodes below it come from the same module, so they are not prefixed. Tool values are identities: `"example-topology-tools:add-link"`. Call ids increase in send order, and rules use `id <` to mean "earlier".

## Run it

From the repository root, with Python 3.11 or newer:

```bash
pip install -e . jsonschema
python examples/mcp-interface/compile_mcp.py \
  examples/mcp-interface/models/example-topology-tools@2026-11-11.yang \
  --include-path examples/mcp-interface/models            # prints the tools/list result
xyang validate --include-path examples/mcp-interface/models \
  examples/mcp-interface/models/example-topology-tools@2026-11-11.yang \
  examples/mcp-interface/session/invalid/hallucinated-link-target.json
cd examples/mcp-interface && python check.py
```

`check.py` confirms that `out/` matches a fresh compile, that every tool schema is JSON Schema 2020-12 with `type: object`, and that the valid session passes the standard interface. It then confirms that xYang gives exactly the expected errors for every fixture. If `ts/dist` is built, it also checks that `xyang-ts` reports the same paths and codes.

## The server and its errors

`server.py` handles `initialize`, `ping`, `tools/list` and `tools/call` as JSON-RPC 2.0, one message per line on stdin and stdout. It needs no MCP SDK. It keeps one session record. For each `tools/call`, it appends the call to a copy of the record and validates the whole record with xYang. The call runs and is kept only if the record stays valid, so the record is always a valid session.

Errors follow MCP 2025-11-25, ["Error Handling"](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#error-handling): problems the model can fix come back as a result with `isError: true`, and malformed requests come back as JSON-RPC errors.

| Situation | Response | Recorded? |
| --- | --- | --- |
| Line is not JSON | JSON-RPC error `-32700` | no |
| Not a JSON-RPC 2.0 request | `-32600` | no |
| Unknown method | `-32601` | no |
| Unknown tool, missing `name`, `arguments` not an object | `-32602`, for example `Unknown tool: delete-node` | no |
| Arguments break the tool's schema or a session rule | result, `isError: true`: one line per argument and what is wrong, ending "Fix the arguments and call the tool again." The same errors as data in `_meta["xyang/errors"]` | no |
| Valid arguments, but the tool cannot do it (no path) | result, `isError: true`, for example `find-path failed: no path from r1 to h2 within 8 hops` | yes, `status: error` |
| The server's own result breaks the model | `-32603`, with the errors in `error.data` | no |
| Success | result with `structuredContent` when the tool has an `outputSchema`, and the same JSON as text | yes |

Example: an agent links `r1` to a node it never created.

```json
{"jsonrpc": "2.0", "id": 3, "result": {
  "content": [{"type": "text", "text": "add-link was not run: its arguments break 1 rule.\n- arguments.target: target must name a node that an earlier successful add-node call created.\nFix the arguments and call the tool again."}],
  "isError": true,
  "_meta": {"xyang/errors": [{"path": "arguments.target", "code": "must", "message": "target must name a node that an earlier successful add-node call created."}]}}}
```

Error paths are relative to the call (`arguments.target`, `result.hop.1`), not to the session record.

```bash
python examples/mcp-interface/server.py                    # serve on stdio
python -m pytest examples/mcp-interface/test_server.py -q  # 19 tests
```

## Limits

- **The session is the whole world.** A verdict covers the calls in this document. It says nothing about server state the document does not contain. The `view` container (`caller`, `snapshot` digest) records which local view a session was checked in.
- **One call alone.** The xYang profile carries a tool's own `must` rules in `x-yang`. xYang does not yet validate rpc input instances directly ([#149](https://github.com/exergy-connect/xYang/issues/149)), so the server checks each call inside its session record. It revalidates the whole record on every call, which is fine for a demo but grows with the session.
- **Optional MCP fields.** In MCP revision [2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools), a tool has `name`, `title`, `description`, `icons`, `inputSchema`, `outputSchema`, `annotations` and `execution`. The compiler emits `name`, `description`, `inputSchema` and `outputSchema`; the other four are optional and left out. It sets no `$schema`, so both schemas use the spec's default, JSON Schema 2020-12.
