/**
 * RPC input and output instances (RFC 7950 §7.14, accessible tree §6.4.1).
 *
 * The module and the caller's data are never modified. The accessible tree is built from a
 * shallow copy of the module whose statement list holds the server data nodes plus one
 * operation node named after the rpc; that node carries the `input` or `output` body as its
 * children.
 */
import { YangModule, YangStatement } from "../core/model";

export type OperationDirection = "input" | "output";

export const DIRECTIONS: readonly OperationDirection[] = ["input", "output"];

export type OperationOptions = {
  /** Name of an rpc of the module. When set, `data` is that rpc's `direction` instance. */
  rpc?: string;
  /** Which instance of `rpc`. Default `"input"`. */
  direction?: OperationDirection;
  /** Server data next to the operation node (RFC 7950 §6.4.1). Not validated. */
  context?: Record<string, unknown>;
};

/** Reject option combinations that make no sense. The thrown `Error` is a usage error. */
export function checkOperationOptions(options: OperationOptions): void {
  const { rpc, direction = "input", context } = options;
  if (!DIRECTIONS.includes(direction)) {
    throw new Error(`direction must be 'input' or 'output', got ${JSON.stringify(direction)}`);
  }
  if (rpc === undefined) {
    if (direction !== "input") {
      throw new Error("direction applies only together with rpc");
    }
    if (context !== undefined) {
      throw new Error("context applies only together with rpc");
    }
  } else if (typeof rpc !== "string" || rpc.length === 0) {
    throw new Error("rpc must be a non-empty rpc name");
  }
  if (context !== undefined && (context === null || typeof context !== "object" || Array.isArray(context))) {
    throw new Error("context must be a JSON object");
  }
}

export function findRpc(module: YangModule, name: string): YangStatement {
  const rpcs = module.statements.filter((stmt) => stmt.keyword === "rpc" && stmt.name);
  const found = rpcs.find((stmt) => stmt.name === name);
  if (!found) {
    const known = rpcs.map((stmt) => stmt.name as string).sort();
    throw new Error(`module '${module.name}' has no rpc '${name}' (rpcs: ${known.length ? known.join(", ") : "none"})`);
  }
  return found;
}

export function findBody(rpc: YangStatement, direction: OperationDirection): YangStatement | undefined {
  return rpc.statements.find((stmt) => stmt.keyword === direction);
}

/** The operation node of RFC 7950 §6.4.1: named after the rpc, parameters as children. */
export function operationNode(rpc: YangStatement, body: YangStatement | undefined): YangStatement {
  const node = new YangStatement({ keyword: "container", name: rpc.name });
  if (body) {
    node.statements = body.statements;
  }
  return node;
}

/**
 * Copy of `module` whose top level is its data nodes plus `operation`. Operations are not data
 * nodes and are left out, so a path step to the rpc name finds the operation node only.
 */
export function accessibleModule(module: YangModule, operation: YangStatement): YangModule {
  const accessible = Object.assign(Object.create(Object.getPrototypeOf(module)), module) as YangModule;
  accessible.statements = [...module.statements.filter((stmt) => stmt.keyword !== "rpc"), operation];
  return accessible;
}

/** RFC 8040 §3.6 member name of the operation body: `module:input` or `module:output`. */
export function wrapperMember(module: YangModule, direction: OperationDirection): string {
  return `${module.name}:${direction}`;
}
