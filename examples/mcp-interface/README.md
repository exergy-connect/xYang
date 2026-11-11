# MCP interface from YANG: a tool set and a checked session

One YANG source gives three things:

1. **A standard MCP interface.** Each `rpc` compiles into an MCP `tools/list` entry: name, description, `inputSchema`, and `outputSchema` when the rpc has an output. Any MCP client can use it.
2. **A gate on each call.** The server checks a call's arguments as the rpc's input, with the session so far as context, before running it. A link may only join nodes that an earlier successful call created.
3. **A record checked against itself.** The same rules check every call in a stored session against the calls before it.

> **Needs an xYang with rpc validation ([#151](https://github.com/exergy-connect/xYang/pull/151)).** With an older xYang, the server refuses to start, `test_server.py` is skipped, and `check.py` skips its rpc cases, each with a message saying so. The compiler and the session checks work with any recent version.

Plain JSON Schema checks each call alone. In this example, 8 of the 12 invalid sessions pass that check, and xYang rejects all 12.

All names and data are synthetic.

## Files

| File | What it is |
| --- | --- |
| [`models/example-mcp@2026-11-11.yang`](models/example-mcp@2026-11-11.yang) | Base: the `tool` identity and the `session` grouping (protocol version, server, the local view, the list of calls) |
| [`models/example-topology-tools@2026-11-11.yang`](models/example-topology-tools@2026-11-11.yang) | A tool set: `add-node`, `add-link`, `find-path` as rpcs whose groupings carry the rules, plus the session container |
| [`compile_mcp.py`](compile_mcp.py) | rpcs → `tools/list` result, in two profiles |
| [`out/tools-list.json`](out/tools-list.json) | Standard profile: plain JSON Schema |
| [`out/tools-list.xyang.json`](out/tools-list.xyang.json) | xYang profile: the same schemas with `x-yang` kept |
| [`session/valid.json`](session/valid.json) | Seven calls that build a three-node topology and find a path |
| [`session/invalid/`](session/invalid/) | One mutation of the valid session per rule, made by [`build_fixtures.py`](build_fixtures.py) |
| [`session/expected-errors.json`](session/expected-errors.json) | The exact xYang errors for every fixture |
| [`calls/cases.json`](calls/cases.json) | Single calls: an rpc input or output, the context it is checked in, and its exact expected errors |
| [`check.py`](check.py) | End-to-end check (see below) |
| [`server.py`](server.py) | A minimal MCP server over stdio that checks every `tools/call` with xYang rpc validation before running it |
| [`test_server.py`](test_server.py) | One test per error kind, plus a stdio round trip |

## How one tool is declared

Each tool is one grouping, and the grouping carries the rules:

```yang
grouping add-link-input {
  leaf source {
    must "/session/call[derived-from-or-self(tool, 'topo:add-node')][result/status = 'ok']
                       [arguments/add-node/name = current()]
                       [not(current()/../../../id) or id < current()/../../../id]";
  }
  leaf target { must ". != ../source"; must "<same as source>"; }
  leaf bandwidth-mbps { type uint32 { range "1..400000"; } }
}

rpc add-link { input { uses add-link-input; } }        // → MCP tool, inputSchema, and the per-call gate
identity add-link { base mcp:tool; }                   // → a value a recorded call's 'tool' may name
augment "/topo:session/topo:call/topo:arguments" {      // → a recorded call's arguments
  container add-link { when "derived-from-or-self(../../tool, 'topo:add-link')"; uses add-link-input; }
}
```

**One rule, two contexts.** The `source` rule reads earlier calls from the session with an absolute path, and keeps those whose `id` is smaller than this call's own:

- For a **recorded call**, `current()/../../../id` is that call's id, so only calls before it count.
- For an **rpc input** checked with the session as context, the parameters sit under the operation node, directly below the root (RFC 7950 §6.4.1). So `current()/../../../id` selects nothing, and every recorded call counts as earlier.

The rule doesn't need to know whether it is gating a request that just arrived or auditing a line in the record. Each verdict is relative to the local view it was given.

One rule can't move into the grouping: "a path contains its `from` and `to`" compares a result with its own arguments. An rpc output cannot see its input (RFC 7950 §6.4.1), so that rule stays on the recorded call's result.

## Mapping

| YANG | MCP `tools/list` |
| --- | --- |
| `rpc` name | `name` |
| `rpc` description | `description` |
| `rpc input` | `inputSchema` (`type: object`, with the `$defs` it references) |
| `rpc output` | `outputSchema` |
| `mandatory true` | `required` |
| `range`, `pattern`, `enumeration`, `default` | `minimum`/`maximum`, `pattern`, `enum`, `default` |
| `must`, `when`, `leafref` | `x-yang` (xYang profile only; generic validators ignore it). The cross-call rules travel here too, so an xYang-aware client can check a call against its own copy of the session before sending it. |

## Rules

| Rule | Where | Fixture |
| --- | --- | --- |
| A call names a declared tool | `tool` is an identityref with base `mcp:tool` | `undeclared-tool` |
| A call carries exactly its own tool's arguments | base: `count(*) = 1` on `arguments`; tools: `when` on each argument container | `arguments-for-other-tool`, `missing-arguments` |
| A node name is added successfully at most once (a later attempt may be recorded as failed) | grouping: `add-node/name` | `duplicate-node` |
| A link joins two different nodes | grouping: `target != source` | `self-loop` |
| Link ends, path ends and path hops are nodes that an earlier successful `add-node` created | groupings: the absolute-path rule above | `hallucinated-link-target`, `link-before-node`, `link-to-failed-node`, `hallucinated-path-hop` |
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
# check one call against the session so far
xyang validate --rpc add-link --context examples/mcp-interface/session/valid.json \
  --include-path examples/mcp-interface/models \
  examples/mcp-interface/models/example-topology-tools@2026-11-11.yang call.json
#   call.json: {"example-topology-tools:input": {"source": "r1", "target": "r9"}}
#   -> must at /example-topology-tools:input/target
#   xyang validate --help (or xyang-ts validate --help) explains --rpc, --output and --context
cd examples/mcp-interface && python check.py
```

`check.py` confirms that `out/` matches a fresh compile, that every tool schema is JSON Schema 2020-12 with `type: object`, and that the valid session passes the standard interface. It then confirms that xYang gives exactly the expected errors for every fixture. If `ts/dist` is built, it also checks that `xyang-ts` reports the same paths and codes. Finally, it runs every case in `calls/cases.json` through `--rpc`, `--output` and `--context`, in both CLIs, and compares the errors exactly.

## The server and its errors

`server.py` handles `initialize`, `ping`, `tools/list` and `tools/call` as JSON-RPC 2.0, one message per line on stdin and stdout. It needs no MCP SDK. It keeps one session record, and handles each `tools/call` in four steps:

1. **Gate.** It validates the arguments as the tool's rpc input, with the record as context. If any rule fails, the call is not run.
2. **Run.** It runs the tool.
3. **Output.** It validates a structured result as the rpc's output, with the same context.
4. **Record.** It appends the call and validates the whole record. This catches result rules that need the arguments, such as a path containing its `from` and `to`.

Steps 3 and 4 check the server's own work, so a failure there is a server bug, not the model's.

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
- **The record check grows.** Step 4 revalidates the whole record on every call, which is fine for a demo but grows with the session.
- **Unprefixed paths.** The rules write `/session/call`, not `/topo:session/topo:call`. RFC 7950 allows both, but today xYang selects nothing for a prefixed step, in `must`, `when` and leafref paths alike ([#152](https://github.com/exergy-connect/xYang/issues/152)).
- **Optional MCP fields.** In MCP revision [2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools), a tool has `name`, `title`, `description`, `icons`, `inputSchema`, `outputSchema`, `annotations` and `execution`. The compiler emits `name`, `description`, `inputSchema` and `outputSchema`; the other four are optional and left out. It sets no `$schema`, so both schemas use the spec's default, JSON Schema 2020-12.
