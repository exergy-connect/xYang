// MCP 2026-07-28 protocol pieces shared by the Worker and its Durable Object.
// Mirrors server.py: same messages, codes and HTTP statuses, so the same agent
// and the same tests run against either.

import tools from "../../out/tools-list.json";

export const PROTOCOL_VERSION = "2026-07-28";
export const SUPPORTED_VERSIONS = [PROTOCOL_VERSION];
export const SERVER_INFO = { name: "topology-builder", version: "0.2.0" };
export const META_VERSION = "io.modelcontextprotocol/protocolVersion";
export const META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo";
export const META_SERVER_INFO = "io.modelcontextprotocol/serverInfo";
export const ERRORS_META_KEY = "xyang/errors";
export const INSTRUCTIONS =
  "Call open-session first and pass the returned handle as 'session' on every other call. " +
  "Add nodes before linking them. When a call returns isError, read which argument broke " +
  "which rule, fix it, and call again.";
export const LIST_TTL_MS = 300_000;
export const SESSION_TTL_MS = 24 * 3600 * 1000;

export const PARSE_ERROR = -32700;
export const INVALID_REQUEST = -32600;
export const METHOD_NOT_FOUND = -32601;
export const INVALID_PARAMS = -32602;
export const INTERNAL_ERROR = -32603;
export const HEADER_MISMATCH = -32020;
export const UNSUPPORTED_VERSION = -32022;

export type Json = null | boolean | number | string | Json[] | { [k: string]: Json };
export type JsonObject = { [k: string]: Json };
export type ToolIssue = { path: string; code: string; message: string };
export type Tool = { name: string; inputSchema: { properties?: Record<string, { "x-mcp-header"?: string }> } };

export const TOOL_LIST = (tools as { tools: Tool[] }).tools;
export const TOOLS: Record<string, Tool> = Object.fromEntries(TOOL_LIST.map((t) => [t.name, t]));

/** A JSON-RPC error raised while handling a request. */
export class ProtocolError extends Error {
  constructor(readonly code: number, message: string, readonly data?: Json) {
    super(message);
  }
}

export function rpcError(id: Json | undefined, code: number, message: string, data?: Json): JsonObject {
  const error: JsonObject = { code, message };
  if (data !== undefined) error.data = data;
  return { jsonrpc: "2.0", id: id ?? null, error };
}

export function isObject(v: unknown): v is JsonObject {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function isRequestOrNotification(m: unknown): m is JsonObject & { method: string } {
  return isObject(m) && m.jsonrpc === "2.0" && typeof m.method === "string";
}

/** Every request declares its protocol version in _meta ("Versioning"). */
export function checkVersion(params: JsonObject): void {
  const meta = params._meta;
  const version = isObject(meta) ? meta[META_VERSION] : undefined;
  if (typeof version !== "string") {
    throw new ProtocolError(INVALID_PARAMS, `Invalid params: _meta['${META_VERSION}'] is required`);
  }
  if (!SUPPORTED_VERSIONS.includes(version)) {
    throw new ProtocolError(UNSUPPORTED_VERSION, "Unsupported protocol version", {
      supported: SUPPORTED_VERSIONS,
      requested: version,
    });
  }
}

/** /m:input/target -> arguments.target, relative to the call. */
export function relative(e: { path: string; code: string; message: string }, prefix: string, label: string): ToolIssue {
  let where = e.path;
  if (where === prefix || where.startsWith(prefix + "/")) {
    const rest = where.slice(prefix.length).replace(/^\/+/, "").replaceAll("/", ".");
    where = rest ? `${label}.${rest}` : label;
  }
  return { path: where, code: e.code, message: e.message };
}

export function toolOk(structured: JsonObject | null, text?: string): JsonObject {
  if (structured === null) return { content: [{ type: "text", text: text ?? "ok" }] };
  // Structured result plus the same JSON as text, for older clients ("Structured Content").
  return { content: [{ type: "text", text: text ?? JSON.stringify(structured) }], structuredContent: structured };
}

export function toolError(name: string, errors: ToolIssue[]): JsonObject {
  const lines = [`${name} was not run: its arguments break ${errors.length} rule${errors.length === 1 ? "" : "s"}.`];
  for (const e of errors) lines.push(`- ${e.path}: ${e.message}`);
  lines.push("Fix the arguments and call the tool again.");
  return {
    content: [{ type: "text", text: lines.join("\n") }],
    isError: true,
    _meta: { [ERRORS_META_KEY]: errors as unknown as Json },
  };
}

export function unknownSession(name: string): JsonObject {
  // "Stateful Tools": an unknown or expired handle is a tool execution error.
  const message = "Unknown or expired session. Call open-session to start a new one, then retry with its handle.";
  return toolError(name, [{ path: "arguments.session", code: "unknown-session", message }]);
}

// ---- Streamable HTTP header validation ("Server Validation") -----------------

const HEADER_SAFE = /^[\x20-\x7e\t]*$/;

export function decodeHeader(value: string): string {
  if (value.startsWith("=?base64?") && value.endsWith("?=")) {
    const bytes = Uint8Array.from(atob(value.slice("=?base64?".length, -2)), (c) => c.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  }
  return value;
}

/** Returns [HTTP status, JSON-RPC error] when the mirrored headers are missing or differ from the body. */
export function checkHttpHeaders(headers: Headers, message: JsonObject & { method: string }): [number, JsonObject] | null {
  const id = message.id;
  const params = isObject(message.params) ? message.params : {};
  const mismatch = (text: string): [number, JsonObject] => [400, rpcError(id, HEADER_MISMATCH, `Header mismatch: ${text}`)];

  const version = headers.get("MCP-Protocol-Version");
  if (version === null) return mismatch("MCP-Protocol-Version header is required");
  const meta = isObject(params._meta) ? params._meta : {};
  if (meta[META_VERSION] !== version) {
    return mismatch(`MCP-Protocol-Version header '${version}' does not match body _meta value ${JSON.stringify(meta[META_VERSION] ?? null)}`);
  }
  if (!SUPPORTED_VERSIONS.includes(version)) {
    return [400, rpcError(id, UNSUPPORTED_VERSION, "Unsupported protocol version", { supported: SUPPORTED_VERSIONS, requested: version })];
  }
  const method = headers.get("Mcp-Method");
  if (method !== message.method) {
    return mismatch(`Mcp-Method header ${JSON.stringify(method)} does not match body method '${message.method}'`);
  }

  if (["tools/call", "resources/read", "prompts/get"].includes(message.method)) {
    const source = message.method === "resources/read" ? params.uri : params.name;
    const raw = headers.get("Mcp-Name");
    if (raw === null) return mismatch("Mcp-Name header is required");
    if (!HEADER_SAFE.test(raw)) return mismatch("Mcp-Name header contains invalid characters");
    if (decodeHeader(raw) !== source) return mismatch(`Mcp-Name header value '${raw}' does not match body value ${JSON.stringify(source)}`);
  }

  if (message.method === "tools/call" && typeof params.name === "string" && TOOLS[params.name]) {
    const args = isObject(params.arguments) ? params.arguments : {};
    for (const [prop, schema] of Object.entries(TOOLS[params.name].inputSchema.properties ?? {})) {
      const header = schema["x-mcp-header"];
      if (!header) continue;
      const raw = headers.get(`Mcp-Param-${header}`);
      const value = args[prop];
      if (value === undefined || value === null) {
        if (raw !== null) return mismatch(`Mcp-Param-${header} is set but '${prop}' is not in the arguments`);
        continue;
      }
      if (raw === null) return mismatch(`Mcp-Param-${header} header is required when '${prop}' is given`);
      if (!HEADER_SAFE.test(raw)) return mismatch(`Mcp-Param-${header} header contains invalid characters`);
      const expected = typeof value === "boolean" ? String(value) : String(value);
      if (decodeHeader(raw) !== expected) {
        return mismatch(`Mcp-Param-${header} header value '${raw}' does not match body value ${JSON.stringify(value)}`);
      }
    }
  }
  return null;
}
