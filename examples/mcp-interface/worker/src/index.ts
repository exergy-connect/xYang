// Cloudflare Worker: the topology MCP server (revision 2026-07-28), checked by xYang.
//
// One endpoint, POST /mcp (Streamable HTTP). server/discover and tools/list are
// answered here; each tools/call is routed to the Durable Object named by its
// session handle, which Cloudflare can also see in the Mcp-Param-Session header.
// The rules and messages match server.py, so the same agent and tests apply.
//
// HTTP/3 is terminated at Cloudflare's edge and enabled per zone; nothing here
// depends on the HTTP version the client used.

import {
  INSTRUCTIONS, INVALID_PARAMS, INVALID_REQUEST, LIST_TTL_MS, META_CLIENT_INFO, META_SERVER_INFO, METHOD_NOT_FOUND,
  PARSE_ERROR, ProtocolError, SERVER_INFO, SUPPORTED_VERSIONS, TOOL_LIST, TOOLS, UNSUPPORTED_VERSION,
  checkHttpHeaders, checkVersion, isObject, isRequestOrNotification, rpcError, toolError, toolOk, unknownSession,
  type Json, type JsonObject,
} from "./mcp";
import { InternalError, rpcErrors, SessionObject, type CallOutcome } from "./session";

export { SessionObject };

interface Env {
  SESSIONS: DurableObjectNamespace<SessionObject>;
  ALLOWED_ORIGINS?: string;
}

const HANDLE = /^ses_[0-9a-f]{32}$/;

// The Durable Object's RPC methods, typed plainly: the generated stub type recurses
// too deeply on the JSON types.
type SessionStub = {
  create(handle: string, caller: string): Promise<void>;
  call(name: string, args: JsonObject): Promise<CallOutcome>;
};

function session(env: Env, handle: string): SessionStub {
  return env.SESSIONS.get(env.SESSIONS.idFromName(handle)) as unknown as SessionStub;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== "/mcp") return new Response(null, { status: 404 });
    // No GET stream and no DELETE in 2026-07-28.
    if (request.method !== "POST") return new Response(null, { status: 405, headers: { Allow: "POST" } });

    const origin = request.headers.get("Origin");
    const allowed = new Set((env.ALLOWED_ORIGINS ?? "").split(",").map((s) => s.trim()).filter(Boolean));
    if (origin !== null && !allowed.has(origin) && origin !== url.origin) {
      return json(403, { jsonrpc: "2.0", error: { code: INVALID_REQUEST, message: `Forbidden origin: ${origin}` } });
    }

    let message: unknown;
    try {
      message = await request.json();
    } catch (e) {
      return json(400, rpcError(null, PARSE_ERROR, `Parse error: ${(e as Error).message}`));
    }
    if (!isRequestOrNotification(message)) {
      const id = isObject(message) ? message.id : null;
      return json(400, rpcError(id, INVALID_REQUEST, "Invalid request: expected a JSON-RPC 2.0 request object"));
    }
    if (!("id" in message)) return new Response(null, { status: 202 });

    const failed = checkHttpHeaders(request.headers, message);
    if (failed) return json(failed[0], failed[1]);

    const response = await handle(message, env);
    const code = isObject(response.error) ? response.error.code : undefined;
    return json(code === METHOD_NOT_FOUND ? 404 : code === UNSUPPORTED_VERSION ? 400 : 200, response);
  },
};

async function handle(message: JsonObject & { method: string }, env: Env): Promise<JsonObject> {
  const id = message.id;
  try {
    const params = message.params ?? {};
    if (!isObject(params)) throw new ProtocolError(INVALID_PARAMS, "Invalid params: expected an object");
    checkVersion(params);
    let result: JsonObject;
    if (message.method === "server/discover") {
      result = {
        supportedVersions: SUPPORTED_VERSIONS,
        capabilities: { tools: {} },
        instructions: INSTRUCTIONS,
        ttlMs: LIST_TTL_MS,
        cacheScope: "public",
      };
    } else if (message.method === "tools/list") {
      result = { tools: TOOL_LIST as unknown as Json, ttlMs: LIST_TTL_MS, cacheScope: "public" };
    } else if (message.method === "tools/call") {
      result = await callTool(params, env);
    } else {
      throw new ProtocolError(METHOD_NOT_FOUND, `Method not found: ${message.method}`);
    }
    const meta = isObject(result._meta) ? result._meta : {};
    return { jsonrpc: "2.0", id, result: { resultType: "complete", ...result, _meta: { ...meta, [META_SERVER_INFO]: SERVER_INFO } } };
  } catch (e) {
    if (e instanceof ProtocolError) return rpcError(id, e.code, e.message, e.data);
    if (e instanceof InternalError) {
      return rpcError(id, -32603, e.message, { "xyang/errors": e.errors as unknown as Json });
    }
    throw e;
  }
}

async function callTool(params: JsonObject, env: Env): Promise<JsonObject> {
  const name = params.name;
  if (typeof name !== "string") throw new ProtocolError(INVALID_PARAMS, "Invalid params: 'name' must be a string");
  if (!TOOLS[name]) throw new ProtocolError(INVALID_PARAMS, `Unknown tool: ${name}`);
  const args = params.arguments ?? {};
  if (!isObject(args)) throw new ProtocolError(INVALID_PARAMS, "Invalid params: 'arguments' must be an object");

  if (name === "open-session") {
    const errors = rpcErrors(name, "input", args, "arguments", null);
    if (errors.length) return toolError(name, errors);
    const handle = "ses_" + [...crypto.getRandomValues(new Uint8Array(16))].map((b) => b.toString(16).padStart(2, "0")).join("");
    const meta = isObject(params._meta) ? params._meta : {};
    const client = isObject(meta[META_CLIENT_INFO]) ? meta[META_CLIENT_INFO] : {};
    await session(env, handle).create(handle, String(client.name ?? "anonymous").slice(0, 128));
    return toolOk({ session: handle }, `Started session ${handle}. Pass it as 'session' on every call.`);
  }

  const handle = args.session;
  if (typeof handle !== "string" || !HANDLE.test(handle)) return unknownSession(name);
  const outcome = await session(env, handle).call(name, args);
  if ("error" in outcome) throw new ProtocolError(outcome.error.code, outcome.error.message, outcome.error.data);
  return outcome.result;
}

function json(status: number, body: JsonObject): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
