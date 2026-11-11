# MCP interface from YANG: a tool set, checked sessions, and an agent

A toy example of xYang behind an MCP server. One YANG source gives:

1. **A standard MCP interface.** Each `rpc` compiles into an MCP `tools/list` entry: name, description, `inputSchema`, and `outputSchema` when the rpc has an output. Any MCP client can use it.
2. **A gate on each call.** The server checks a call's arguments as the rpc's input, with the session so far as context, before running it. A link may only join nodes that an earlier successful call created.
3. **A record checked against itself.** The same rules check every call in a stored session against the calls before it.

It speaks MCP revision **[2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/changelog)**: no `initialize`, no protocol sessions, version and client information in every request's `_meta`, and `server/discover`. It runs locally in Python (stdio or HTTP), or as a **Cloudflare Worker** that loads the model from xYang's native JSON and keeps each session in a Durable Object. A sample agent drives either one over stdio, HTTP/1.1 or HTTP/3, makes a mistake, and repairs it from the structured errors.

Plain JSON Schema checks each call alone. In this example, 9 of the 13 invalid sessions pass that check, and xYang rejects all 13.

> **Needs an xYang with rpc validation ([#151](https://github.com/exergy-connect/xYang/pull/151)).** With an older xYang, the server refuses to start, its tests are skipped, and `check.py` skips its rpc cases, each with a message saying so.

All names and data are synthetic.

## Files

| File | What it is |
| --- | --- |
| [`models/example-mcp@2026-11-11.yang`](models/example-mcp@2026-11-11.yang) | Base: the `tool` identity, the `session-handle` type, the `session` argument every tool takes, the `http-header` extension, and the `session` record grouping |
| [`models/example-topology-tools@2026-11-11.yang`](models/example-topology-tools@2026-11-11.yang) | A tool set: `open-session`, `add-node`, `add-link`, `find-path` as rpcs whose groupings carry the rules, plus the session record container |
| [`compile_mcp.py`](compile_mcp.py) | rpcs → `tools/list` tools, in two profiles |
| [`out/tools-list.json`](out/tools-list.json) | Standard profile: plain JSON Schema, with `x-mcp-header` |
| [`out/tools-list.xyang.json`](out/tools-list.xyang.json) | xYang profile: the same schemas with `x-yang` kept |
| [`out/example-topology-tools.yang.json`](out/example-topology-tools.yang.json) | The model as native JSON (`xyang convert`), which the Worker loads: no filesystem and no YANG parsing at runtime |
| [`session/valid.json`](session/valid.json) | One session's record: seven calls that build a three-node topology and find a path |
| [`session/invalid/`](session/invalid/) | One mutation of the valid record per rule, made by [`build_fixtures.py`](build_fixtures.py) |
| [`session/expected-errors.json`](session/expected-errors.json) | The exact xYang errors for every fixture |
| [`calls/cases.json`](calls/cases.json) | Single calls: an rpc input or output, the context it is checked in, and its exact expected errors |
| [`check.py`](check.py) | End-to-end check of the model, the interface and the fixtures |
| [`server.py`](server.py) | The MCP server: stdio, or Streamable HTTP with `--http` |
| [`agent_client.py`](agent_client.py) | The sample agent: stdio, HTTP/1.1, or HTTP/3 |
| [`h3_dev_server.py`](h3_dev_server.py) | A local HTTP/3 endpoint for testing the agent's HTTP/3 transport (self-signed) |
| [`worker/`](worker/) | The Cloudflare Worker: [`src/index.ts`](worker/src/index.ts) (HTTP and routing), [`src/session.ts`](worker/src/session.ts) (one Durable Object per session), [`src/mcp.ts`](worker/src/mcp.ts) (protocol rules), [`wrangler.toml`](worker/wrangler.toml) |
| [`test_server.py`](test_server.py), [`test_agent.py`](test_agent.py), [`test_http.py`](test_http.py) | Server rules, one test per error kind; the agent's run over every transport; the HTTP rules against any deployment (`MCP_URL`) |

## Sessions are handles

MCP 2026-07-28 has no protocol-level session. A server that keeps state across calls mints an explicit handle from a creation tool and takes it as an ordinary argument on later calls ([Stateful Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#stateful-tools)). Here:

- `open-session` takes no arguments and returns `{"session": "ses_<32 hex>"}`: 128 random bits, with no structure.
- Every other tool takes `session` as its first argument. Its description states the lifetime: 24 hours without a call.
- An unknown or expired handle is a tool execution error that says to start a new session.
- The `session` argument carries `mcp:http-header "Session"`, which the compiler emits as `"x-mcp-header": "Session"`. On HTTP, the client mirrors it into `Mcp-Param-Session`, so an intermediary such as Cloudflare can route a call to its session without parsing the body.
- Each handle keys one session record, the context its calls are checked in. A rule on every tool's `session` argument checks that it names the record it is checked against (`call-in-other-session`).

## How one tool is declared

Each tool is one grouping, and the grouping carries the rules:

```yang
grouping add-link-input {
  uses mcp:session-argument { refine session { must ". = /topo:session/topo:handle"; } }
  leaf source {
    must "/topo:session/topo:call[derived-from-or-self(tool, 'topo:add-node')][result/status = 'ok']
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
| `rpc input` | `inputSchema` (`type: object`, with the `$defs` it references). No input: `{"type": "object", "additionalProperties": false}`, as the spec recommends |
| `rpc output` | `outputSchema` |
| `mandatory true` | `required` |
| `range`, `pattern`, `enumeration`, `default` | `minimum`/`maximum`, `pattern`, `enum`, `default` |
| `mcp:http-header "Session"` | `"x-mcp-header": "Session"`, checked against the spec's rules (a token, unique ignoring case, on a string, integer or boolean property) |
| `must`, `when`, `leafref` | `x-yang` (xYang profile only; generic validators ignore it). The cross-call rules travel here too, so an xYang-aware client can check a call against its own copy of the session before sending it. |

xYang's JSON Schema does not carry extension invocations, so the compiler reads `mcp:http-header` from the parsed YANG.

## Rules

| Rule | Where | Fixture |
| --- | --- | --- |
| A call names a declared tool | `tool` is an identityref with base `mcp:tool` | `undeclared-tool` |
| A call carries exactly its own tool's arguments | base: `count(*) = 1` on `arguments`; tools: `when` on each argument container | `arguments-for-other-tool`, `missing-arguments` |
| A call's `session` is the handle of the record it is in | groupings: `session = /topo:session/topo:handle` | `call-in-other-session` |
| A node name is added successfully at most once (a later attempt may be recorded as failed) | grouping: `add-node/name` | `duplicate-node` |
| A link joins two different nodes | grouping: `target != source` | `self-loop` |
| Link ends, path ends and path hops are nodes that an earlier successful `add-node` created | groupings: the absolute-path rule above | `hallucinated-link-target`, `link-before-node`, `link-to-failed-node`, `hallucinated-path-hop` |
| A path contains its `from` and `to` and is at most `max-hops` long | `find-path` result | `path-missing-endpoint`, `path-too-long` |
| Argument types and ranges | YANG types | `bandwidth-out-of-range` |

Instance data is RFC 7951 JSON. The root is `example-topology-tools:session`. Nodes below it come from the same module, so they are not prefixed. Tool values are identities: `"example-topology-tools:add-link"`. Call ids increase in receive order, and rules use `id <` to mean "earlier".

## The server

```bash
python examples/mcp-interface/server.py                          # stdio
python examples/mcp-interface/server.py --http 127.0.0.1:8787    # Streamable HTTP, POST /mcp
```

It handles `server/discover`, `tools/list` and `tools/call`. It needs no MCP SDK. Every result carries `resultType: "complete"` and the server's identity in `_meta["io.modelcontextprotocol/serverInfo"]`. `server/discover` and `tools/list` are cacheable (`ttlMs`, `cacheScope: "public"`), and tools are listed in a fixed order.

Each `tools/call` (other than `open-session`) is handled in four steps:

1. **Gate.** It validates the arguments as the tool's rpc input, with the session's record as context. If any rule fails, the call is not run.
2. **Run.** It runs the tool.
3. **Output.** It validates a structured result as the rpc's output, with the same context.
4. **Record.** It appends the call and validates the whole record. This catches result rules that need the arguments, such as a path containing its `from` and `to`.

Steps 3 and 4 check the server's own work, so a failure there is a server bug, not the model's.

### Errors

These follow MCP 2026-07-28 (["Error Handling"](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#error-handling), ["Versioning"](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning), ["Streamable HTTP"](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)). Problems the model can fix come back as a result with `isError: true`; everything else is a JSON-RPC error.

| Situation | Response | HTTP status | Recorded? |
| --- | --- | --- | --- |
| Body is not JSON | `-32700` | 400 | no |
| Not a JSON-RPC 2.0 request | `-32600` | 400 | no |
| No `_meta` protocol version | `-32602` on stdio. On HTTP the header check fails first: `-32020` | 400 on HTTP | no |
| Protocol version not supported | `-32022` with `{"supported": [...], "requested": ...}` | 400 | no |
| A required header is missing or differs from the body: `MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name`, `Mcp-Param-Session` | `-32020` HeaderMismatch | 400 | no |
| Unknown method (`initialize` and `ping` were removed in 2026-07-28) | `-32601` | 404 | no |
| Unknown tool, missing `name`, `arguments` not an object | `-32602`, for example `Unknown tool: delete-node` | 200 | no |
| Unknown or expired session handle | result, `isError: true`, code `unknown-session` | 200 | no |
| Arguments break the tool's schema or a session rule | result, `isError: true`: one line per argument and what is wrong, ending "Fix the arguments and call the tool again." The same errors as data in `_meta["xyang/errors"]` | 200 | no |
| Valid arguments, but the tool cannot do it (no path) | result, `isError: true`, for example `find-path failed: no path from r1 to h2 within 8 hops` | 200 | yes, `status: error` |
| The server's own result, or its record, breaks the model | `-32603`, with the errors in `error.data` | 200 | no |
| Success | `structuredContent` when the tool has an `outputSchema`, and the same JSON as text | 200 | yes |

HTTP only: a POST to a path other than `/mcp` is 404, and GET or DELETE on `/mcp` is 405, since the GET stream and protocol sessions are gone. A request with an `Origin` the server does not allow is 403. A notification is accepted with 202.

Error paths are relative to the call (`arguments.target`, `result.hop.1`), not to the session record. For example, an agent links `r1` to a node it never created:

```json
{"jsonrpc": "2.0", "id": 3, "result": {
  "resultType": "complete",
  "content": [{"type": "text", "text": "add-link was not run: its arguments break 1 rule.\n- arguments.target: target must name a node that an earlier successful add-node call created.\nFix the arguments and call the tool again."}],
  "isError": true,
  "_meta": {"xyang/errors": [{"path": "arguments.target", "code": "must", "message": "target must name a node that an earlier successful add-node call created."}],
            "io.modelcontextprotocol/serverInfo": {"name": "topology-builder", "version": "0.2.0"}}}}
```

## The agent

```bash
python examples/mcp-interface/agent_client.py stdio
python examples/mcp-interface/agent_client.py http://127.0.0.1:8787/mcp          # with server.py --http
python examples/mcp-interface/agent_client.py https://<host>/mcp                 # HTTP/3 (QUIC)
python examples/mcp-interface/agent_client.py https://<host>/mcp --http1         # same host, HTTP/1.1
```

The agent is deterministic, with no LLM, so a run is repeatable. It calls `server/discover`, lists the tools, and opens a session. Then it carries out a plan built in a careless order: it links `r1` and `r2` before creating them. It reads the two errors from `_meta["xyang/errors"]`, sees that both name a node no earlier call created, creates `r1` and `r2`, and retries. It also restarts the session if the handle has expired. Then it finishes the plan:

```
server   topology-builder 0.2.0, versions ['2026-07-28'], over HTTP/3
tools    open-session, add-node, add-link, find-path (mirrored headers: Session)
session  ses_767d231c3d5f437eb73d2b28053643de
-> add-link {"source": "r1", "target": "r2"}
<- isError arguments.source: source must name a node that an earlier successful add-node call created.
<- isError arguments.target: target must name a node that an earlier successful add-node call created.
   repair: create node 'r1' first
  -> add-node {"name": "r1"}
  <- {"name": "r1"}
   repair: create node 'r2' first
  -> add-node {"name": "r2"}
  <- {"name": "r2"}
-> add-link {"source": "r1", "target": "r2"}
-> add-node {"name": "h1", "role": "host"}
<- {"name": "h1"}
-> add-link {"source": "r2", "target": "h1", "bandwidth-mbps": 100}
-> find-path {"from": "r1", "to": "h1", "max-hops": 4}
<- {"hop": ["r1", "r2", "h1"]}
done     8 calls, 2 repairs, path r1 -> r2 -> h1
```

Every request carries `_meta` with the protocol version, `clientInfo` and `clientCapabilities`. On HTTP, every POST also carries `MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name` (for `tools/call`) and one `Mcp-Param-<name>` for each argument a tool marks with `x-mcp-header`. Values that aren't safe as header text use the spec's `=?base64?…?=` encoding. The client reads either a JSON response or an SSE stream.

### HTTP/3

The HTTP/3 transport uses [aioquic](https://github.com/aiortc/aioquic) (`pip install aioquic`) over one QUIC connection for the whole run. It falls back to an IPv4 socket on hosts without IPv6. To try it locally:

```bash
python examples/mcp-interface/h3_dev_server.py --port 4433       # self-signed certificate, made on start
python examples/mcp-interface/agent_client.py https://127.0.0.1:4433/mcp --insecure
```

`h3_dev_server.py` passes each request to the same Streamable HTTP handler as `server.py --http`, so both apply the same rules. It is for testing only. Behind Cloudflare, HTTP/3 is terminated at the edge. It is a setting on the zone (Speed › Settings › Protocol Optimization, per [Cloudflare's docs](https://developers.cloudflare.com/workers/reference/protocols/)), not something the Worker implements.

## Cloudflare Worker

[`worker/`](worker/) runs the same server on Cloudflare. It applies the same rules and messages as `server.py --http`, and the same HTTP tests pass against both.

- **Model:** `out/example-topology-tools.yang.json`, loaded with `parseJsonSchema` from `@exergy-connect/xyang/browser`. A Worker has no filesystem, so it can't resolve `import example-mcp` from `.yang` text. Native JSON carries the imported identities and the applied augments ([#160](https://github.com/exergy-connect/xYang/pull/160)), so one file is the whole model. `check.py` fails if the file is stale.
- **Routing:** `server/discover` and `tools/list` are answered by the Worker itself. Each `tools/call` goes to the Durable Object named by its session handle (`idFromName(handle)`). That object holds the session's record and validates the call against it.
- **Sessions:** `open-session` mints the handle and creates the object. Each call resets an alarm for 24 hours later, and the alarm deletes the record. The objects use SQLite-backed storage (`new_sqlite_classes`).
- **Size:** the bundle, including xYang and the model, is about 249 KiB (55 KiB gzipped).

Run it locally with Wrangler, which uses the same runtime (workerd) and a local Durable Object:

```bash
cd examples/mcp-interface/worker
npm install                  # wrangler, workers-types, and xYang from ../../../ts (build it first: cd ts && npm ci && npm run build)
npm run dev                  # http://127.0.0.1:8787/mcp
python ../agent_client.py http://127.0.0.1:8787/mcp
MCP_URL=http://127.0.0.1:8787/mcp python -m pytest ../test_http.py -q
npm run check                # type-check, and bundle with a dry-run deploy
```

After changing the YANG, run `npm run model` to regenerate the native JSON, and `python ../compile_mcp.py ...` for `out/tools-list*.json`.

### Deploy, and HTTP/3

```bash
npx wrangler login           # or set CLOUDFLARE_API_TOKEN
npm run deploy               # prints the workers.dev URL
```

HTTP/3 is not something the Worker implements. Cloudflare terminates QUIC at its edge and passes the Worker an ordinary request. It is a zone setting: **Speed › Settings › Protocol Optimization › HTTP/3 (with QUIC)** ([Cloudflare docs](https://developers.cloudflare.com/workers/reference/protocols/)). So to serve MCP over HTTP/3:

1. Add a route or custom domain on a zone you control, for example in `wrangler.toml`: `routes = [{ pattern = "mcp.example.com", custom_domain = true }]`.
2. Turn on HTTP/3 for that zone.
3. Run the agent against it. An `https://` target uses HTTP/3:

```bash
python examples/mcp-interface/agent_client.py https://mcp.example.com/mcp            # over HTTP/3 (QUIC)
python examples/mcp-interface/agent_client.py https://mcp.example.com/mcp --http1    # the same, over HTTP/1.1
MCP_URL=https://mcp.example.com/mcp python -m pytest examples/mcp-interface/test_http.py -q
```

Whether the `workers.dev` hostname also answers over HTTP/3 depends on Cloudflare's settings for that domain. The docs page above describes the zone setting only. Browser clients need their origin listed in `ALLOWED_ORIGINS` in `wrangler.toml`; agents and CLIs send no `Origin` and are always allowed.

Not tested from here: deployment to Cloudflare and HTTP/3 at Cloudflare's edge. This sandbox can't reach Cloudflare. The local runs above use the real Workers runtime over HTTP/1.1, and the agent's HTTP/3 transport is tested against `h3_dev_server.py`.

## Run the checks

From the repository root, with Python 3.11 or newer:

```bash
pip install -e . jsonschema pytest aioquic
cd examples/mcp-interface
python check.py                                                 # model, interface and fixtures
python -m pytest test_server.py test_agent.py test_http.py -q   # server rules, the agent over every transport, HTTP rules
```

`check.py` confirms:
- `out/` matches a fresh compile and a fresh native JSON conversion.
- Every tool schema is JSON Schema 2020-12 with `type: object`, and its `x-mcp-header` values follow the spec.
- The valid session passes the standard interface.
- xYang gives exactly the expected errors for every fixture, and `xyang-ts` gives the same paths and codes if `ts/dist` is built.
- Every case in `calls/cases.json` gives its exact errors through `--rpc`, `--output` and `--context`, in both CLIs.

Single calls can be checked by hand too:

```bash
xyang validate --rpc add-link --context session/valid.json --include-path models \
  models/example-topology-tools@2026-11-11.yang call.json
#   call.json: {"example-topology-tools:input": {"session": "ses_3f2a9c0e7b1d4e8fa6c5d2b1e0f9a8c7", "source": "r1", "target": "r9"}}
#   -> must at /example-topology-tools:input/target
```

`xyang validate --help` (or `xyang-ts validate --help`) explains `--rpc`, `--output` and `--context`.

## Limits

- **The session is the whole world.** A verdict covers the calls in one session's record. It says nothing about state the record does not contain. The `view` container (`caller`, `snapshot` digest) records which local view a session was checked in.
- **The record check grows.** xYang validates the context before each rpc check, and step 4 revalidates the whole record. Both are fine for a demo, but they grow with the session.
- **Handles are bearer tokens.** Both servers are unauthenticated, so anyone holding a handle can use its session, as the spec's guidance on handles notes. Sessions are dropped after 24 hours without a call: from memory in Python, and by a Durable Object alarm in the Worker.
- **No rate limiting.** The spec says servers MUST rate-limit tool calls. This example doesn't. On Cloudflare, a rate-limiting rule on the route would do it.
- **Optional MCP fields.** In revision 2026-07-28, a tool has `name`, `title`, `description`, `icons`, `inputSchema`, `outputSchema` and `annotations`. The compiler emits `name`, `description`, `inputSchema` and `outputSchema`. It sets no `$schema`, so both schemas use the spec's default, JSON Schema 2020-12. There is no `subscriptions/listen`, since the tool list never changes.
