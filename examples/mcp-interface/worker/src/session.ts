// One Durable Object per session handle. It holds that session's record, the
// context every call in the session is checked against, and runs the tools.
// The steps match server.py: gate the arguments as the rpc input, run, check
// the output, append to the record and revalidate it.

import { DurableObject } from "cloudflare:workers";
import { parseJsonSchema, YangValidator } from "@exergy-connect/xyang/browser";
import model from "../../out/example-topology-tools.yang.json";
import {
  ERRORS_META_KEY, INTERNAL_ERROR, PROTOCOL_VERSION, SERVER_INFO, SESSION_TTL_MS,
  relative, toolError, toolOk, unknownSession,
  type Json, type JsonObject, type ToolIssue,
} from "./mcp";

const MODULE = "example-topology-tools";
const ROOT = `${MODULE}:session`;

// Loaded once per isolate, from native JSON: no filesystem and no YANG parsing at runtime.
let validator: YangValidator | undefined;
function yang(): YangValidator {
  validator ??= new YangValidator(parseJsonSchema(model as Record<string, unknown>));
  return validator;
}

/** What the Worker gets back: a tools/call result, or a JSON-RPC error to send instead. */
export type CallOutcome = { result: JsonObject } | { error: { code: number; message: string; data?: Json } };

type Call = { id: number; tool: string; arguments: JsonObject; result: JsonObject };
type SessionRecord = { [ROOT]: { handle: string; "protocol-version": string; server: JsonObject; view: JsonObject; call: Call[] } };

class InternalError extends Error {
  constructor(message: string, readonly errors: ToolIssue[]) {
    super(message);
  }
}

class ToolFailed extends Error {}

export class SessionObject extends DurableObject {
  /** Called once by open-session. */
  async create(handle: string, caller: string): Promise<void> {
    const record: SessionRecord = {
      [ROOT]: {
        handle,
        "protocol-version": PROTOCOL_VERSION,
        server: { ...SERVER_INFO },
        view: { caller, snapshot: "0".repeat(64) },
        call: [],
      },
    };
    await this.ctx.storage.put("record", record);
    await this.touch();
  }

  async call(name: string, args: JsonObject): Promise<CallOutcome> {
    const record = await this.ctx.storage.get<SessionRecord>("record");
    if (!record) return { result: unknownSession(name) };
    await this.touch();
    try {
      return { result: await this.run(record, name, args) };
    } catch (e) {
      if (e instanceof InternalError) {
        return { error: { code: INTERNAL_ERROR, message: e.message, data: { [ERRORS_META_KEY]: e.errors as unknown as Json } } };
      }
      throw e;
    }
  }

  /** Expiry: 24 hours after the last call, the record is deleted. */
  async alarm(): Promise<void> {
    await this.ctx.storage.deleteAll();
  }

  private async touch(): Promise<void> {
    await this.ctx.storage.setAlarm(Date.now() + SESSION_TTL_MS);
  }

  private async run(record: SessionRecord, name: string, args: JsonObject): Promise<JsonObject> {
    // 1. Gate: the arguments are the rpc's input, checked against this session's record.
    const errors = rpcErrors(name, "input", args, "arguments", record);
    if (errors.length) return toolError(name, errors);

    // 2. Run the tool.
    const calls = record[ROOT].call;
    const call: Call = { id: calls.length + 1, tool: `${MODULE}:${name}`, arguments: { [name]: structuredClone(args) }, result: {} };
    let structured: JsonObject | null;
    try {
      structured = execute(calls, name, args);
    } catch (e) {
      if (!(e instanceof ToolFailed)) throw e;
      call.result = { status: "error", message: e.message };
      await this.record(record, call);
      return { content: [{ type: "text", text: `${name} failed: ${e.message}` }], isError: true };
    }

    // 3. Check what the server is about to return: the rpc's output, same context.
    if (structured !== null) {
      const bad = rpcErrors(name, "output", structured, "result", record);
      if (bad.length) throw new InternalError(`Internal error: ${name} produced a result the model rejects`, bad);
    }

    // 4. Keep the call; the whole record must stay valid (result rules that need the arguments).
    call.result = name === "find-path" ? { status: "ok", "find-path": structured } : { status: "ok" };
    const bad = await this.record(record, call);
    if (bad.length) throw new InternalError(`Internal error: ${name} produced a result the model rejects`, bad);
    return toolOk(structured);
  }

  private async record(record: SessionRecord, call: Call): Promise<ToolIssue[]> {
    const doc = structuredClone(record);
    doc[ROOT].call.push(call);
    const index = doc[ROOT].call.length - 1;
    const name = call.tool.split(":")[1];
    const errors = yang().validateDetailed(doc).errors;
    if (errors.length) {
      return errors.map((e) => {
        const r = relative(e, `/${ROOT}/call/${index}/result/${name}`, "result");
        return r.path === e.path ? relative(e, `/${ROOT}/call/${index}`, "call") : r;
      });
    }
    await this.ctx.storage.put("record", doc);
    return [];
  }
}

/** Validate an rpc input or output, with a session record as context (xYang rpc validation). */
export function rpcErrors(name: string, direction: "input" | "output", body: JsonObject, label: string,
                          context: SessionRecord | null): ToolIssue[] {
  const verdict = yang().validateDetailed(
    { [`${MODULE}:${direction}`]: body },
    context ? { rpc: name, direction, context } : { rpc: name, direction },
  );
  const contextErrors = verdict.errors.filter((e) => e.document === "context");
  if (contextErrors.length) {
    // A bad record is the server's fault, never the model's.
    throw new InternalError(
      "Internal error: the server's session record is invalid",
      contextErrors.map((e) => ({ path: e.path, code: e.code, message: e.message })),
    );
  }
  return verdict.errors.map((e) => relative(e, `/${MODULE}:${direction}`, label));
}

export { InternalError };

function execute(calls: Call[], name: string, args: JsonObject): JsonObject | null {
  if (name === "add-node") return { name: args.name };
  if (name === "add-link") return null;
  // find-path: breadth-first search over the links added so far.
  const neighbours = new Map<string, Set<string>>();
  for (const c of calls) {
    const link = c.arguments["add-link"] as JsonObject | undefined;
    if (!link || c.result.status !== "ok") continue;
    const [a, b] = [String(link.source), String(link.target)];
    (neighbours.get(a) ?? neighbours.set(a, new Set()).get(a)!).add(b);
    (neighbours.get(b) ?? neighbours.set(b, new Set()).get(b)!).add(a);
  }
  const start = String(args.from), goal = String(args.to);
  const limit = typeof args["max-hops"] === "number" ? args["max-hops"] : 8;
  const queue: string[][] = [[start]];
  const seen = new Set([start]);
  while (queue.length) {
    const path = queue.shift()!;
    if (path[path.length - 1] === goal) return { hop: path };
    if (path.length - 1 < limit) {
      for (const next of [...(neighbours.get(path[path.length - 1]) ?? [])].sort()) {
        if (!seen.has(next)) {
          seen.add(next);
          queue.push([...path, next]);
        }
      }
    }
  }
  throw new ToolFailed(`no path from ${start} to ${goal} within ${limit} hops`);
}
