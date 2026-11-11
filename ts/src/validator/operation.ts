/**
 * rpc and action input and output instances (RFC 7950 §7.14, §7.15, accessible tree §6.4.1).
 *
 * The module and the caller's data are never modified. The accessible tree is built from a shallow
 * copy of the module. For an rpc, its top level holds the server data nodes plus one operation node
 * named after the rpc. For an action, the operation node is a child of the container or list
 * instance the action is invoked on; the statements on the way there are copied so the module keeps
 * its own. The operation node carries the `input` or `output` body as its children.
 *
 * An action is named by the RFC 8040 §3.5.3 data resource identifier of its node, the path a RESTCONF
 * client POSTs to under `{+restconf}/data`: `/module:container/list=key1,key2/action`.
 */
import { YangModule, YangStatement } from "../core/model";

export type OperationDirection = "input" | "output";

export const DIRECTIONS: readonly OperationDirection[] = ["input", "output"];

export type OperationOptions = {
  /** Name of an rpc of the module. When set, `data` is that rpc's `direction` instance. */
  rpc?: string;
  /** RFC 8040 §3.5.3 data resource identifier of an action node (`/m:list=key/action`). */
  action?: string;
  /** Which instance of the operation. Default `"input"`. */
  direction?: OperationDirection;
  /**
   * Server data. Optional for an rpc, required for an action (its parent instance must be in it).
   * Validated against the module before the operation reads it (RFC 7950 §6.4.1).
   */
  context?: Record<string, unknown>;
};

/** One container or list on the way to an action's parent instance. */
export type ParentStep = {
  stmt: YangStatement;
  /** Decoded key values of a list instance. */
  keys?: string[];
  /** `choice` / `case` statements between the previous data node and `stmt`. */
  wrappers: YangStatement[];
};

/** The rpc or action an instance belongs to and, for an action, its parent instance. */
export type OperationTarget = {
  operation: YangStatement;
  moduleName: string;
  label: string;
  parents: ParentStep[];
};

const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_.-]*$/;

/** Reject option combinations that make no sense. The thrown `Error` is a usage error. */
export function checkOperationOptions(options: OperationOptions): void {
  const { rpc, action, direction = "input", context } = options;
  if (!DIRECTIONS.includes(direction)) {
    throw new Error(`direction must be 'input' or 'output', got ${JSON.stringify(direction)}`);
  }
  if (rpc !== undefined && action !== undefined) {
    throw new Error("rpc and action are mutually exclusive");
  }
  if (rpc === undefined && action === undefined) {
    if (direction !== "input") {
      throw new Error("direction applies only together with rpc or action");
    }
    if (context !== undefined) {
      throw new Error("context applies only together with rpc or action");
    }
  }
  if (rpc !== undefined && (typeof rpc !== "string" || rpc.length === 0)) {
    throw new Error("rpc must be a non-empty rpc name");
  }
  if (action !== undefined) {
    if (typeof action !== "string" || action.length === 0) {
      throw new Error("action must be the data resource identifier of an action (RFC 8040 §3.5.3)");
    }
    if (context === undefined) {
      throw new Error(
        "action needs context: the instance it is invoked on must be in the server data (RFC 7950 §7.15)"
      );
    }
  }
  if (context !== undefined && (context === null || typeof context !== "object" || Array.isArray(context))) {
    throw new Error("context must be a JSON object");
  }
}

export function findRpc(module: YangModule, name: string): OperationTarget {
  const rpcs = module.statements.filter((stmt) => stmt.keyword === "rpc" && stmt.name);
  const found = rpcs.find((stmt) => stmt.name === name);
  if (!found) {
    const known = rpcs.map((stmt) => stmt.name as string).sort();
    throw new Error(`module '${module.name}' has no rpc '${name}' (rpcs: ${known.length ? known.join(", ") : "none"})`);
  }
  return { operation: found, moduleName: module.name ?? "", label: `rpc '${name}'`, parents: [] };
}

function definingModule(stmt: YangStatement, host: string): string {
  return stmt.defining_module || host;
}

function parseApiPath(text: string): Array<{ module?: string; name: string; keys?: string[] }> {
  if (!text.startsWith("/") || text === "/") {
    throw new Error(`action '${text}' must be a data resource identifier such as /module:list=key/action`);
  }
  const segments = text.slice(1).split("/").map((raw) => {
    const eq = raw.indexOf("=");
    const ident = eq < 0 ? raw : raw.slice(0, eq);
    const colon = ident.lastIndexOf(":");
    const module = colon < 0 ? undefined : ident.slice(0, colon);
    const name = colon < 0 ? ident : ident.slice(colon + 1);
    if ((module !== undefined && !IDENTIFIER.test(module)) || !IDENTIFIER.test(name)) {
      throw new Error(`action '${text}': '${raw}' is not an api-identifier (RFC 8040 §3.5.3)`);
    }
    const keys = eq < 0 ? undefined : raw.slice(eq + 1).split(",").map((value) => decodeURIComponent(value));
    return { module, name, keys };
  });
  if (segments[0]!.module === undefined) {
    throw new Error(`action '${text}': the first segment must be module-qualified (RFC 8040 §3.5.3)`);
  }
  return segments;
}

function findDataChild(
  parent: { statements: YangStatement[] },
  name: string,
  moduleName: string,
  host: string
): { stmt?: YangStatement; wrappers: YangStatement[] } {
  for (const stmt of parent.statements) {
    if (stmt.keyword === "rpc" || stmt.keyword === "action") continue;
    if (stmt.keyword === "choice" || stmt.keyword === "case") {
      const branches = stmt.keyword === "choice" ? stmt.statements.filter((s) => s.keyword === "case") : [stmt];
      for (const branch of branches) {
        const found = findDataChild(branch, name, moduleName, host);
        if (found.stmt) {
          return { stmt: found.stmt, wrappers: [stmt, ...(branch === stmt ? [] : [branch]), ...found.wrappers] };
        }
      }
      // A choice shorthand: a data node directly under the choice.
      if (stmt.keyword === "choice") {
        const direct = stmt.statements.find((s) => s.keyword !== "case" && s.name === name && definingModule(s, host) === moduleName);
        if (direct) return { stmt: direct, wrappers: [stmt] };
      }
      continue;
    }
    if (stmt.name === name && definingModule(stmt, host) === moduleName) {
      return { stmt, wrappers: [] };
    }
  }
  return { wrappers: [] };
}

/** Resolve an action's data resource identifier; anything that does not name one is a usage error. */
export function resolveAction(module: YangModule, path: string): OperationTarget {
  const host = module.name ?? "";
  const segments = parseApiPath(path);
  if (segments[0]!.module !== host) {
    throw new Error(`action '${path}': the first segment must be in module '${host}'`);
  }
  if (segments.length < 2) {
    throw new Error(`action '${path}' names no container or list instance to invoke the action on`);
  }
  const parents: ParentStep[] = [];
  let schema: { statements: YangStatement[]; name?: string } = module;
  let namespace = host;
  for (const segment of segments.slice(0, -1)) {
    namespace = segment.module ?? namespace;
    const { stmt, wrappers } = findDataChild(schema, segment.name, namespace, host);
    const where = "/" + parents.map((p) => p.stmt.name).join("/");
    if (!stmt) {
      throw new Error(`action '${path}': no container or list '${namespace}:${segment.name}' under ${where}`);
    }
    if (stmt.keyword === "list") {
      const keyNames = (stmt.key ?? "").split(/\s+/).filter(Boolean);
      if (!segment.keys || segment.keys.length !== keyNames.length) {
        throw new Error(
          `action '${path}': list '${segment.name}' needs its ${keyNames.length} key value(s) ` +
            `(${keyNames.join(", ")}) as ${segment.name}=value (RFC 8040 §3.5.3)`
        );
      }
    } else if (stmt.keyword === "container") {
      if (segment.keys) {
        throw new Error(`action '${path}': container '${segment.name}' takes no key values`);
      }
    } else {
      throw new Error(`action '${path}': '${segment.name}' is not a container or list`);
    }
    parents.push({ stmt, ...(segment.keys ? { keys: segment.keys } : {}), wrappers });
    schema = stmt;
  }
  const last = segments[segments.length - 1]!;
  namespace = last.module ?? namespace;
  if (last.keys) {
    throw new Error(`action '${path}': the action segment takes no key values`);
  }
  const action = schema.statements.find(
    (s) => s.keyword === "action" && s.name === last.name && definingModule(s, host) === namespace
  );
  if (!action) {
    const known = schema.statements.filter((s) => s.keyword === "action" && s.name).map((s) => s.name as string).sort();
    throw new Error(
      `action '${path}': '${schema.name}' has no action '${namespace}:${last.name}' (actions: ${known.join(", ") || "none"})`
    );
  }
  return { operation: action, moduleName: namespace, label: `action '${path}'`, parents };
}

export function findBody(operation: YangStatement, direction: OperationDirection): YangStatement | undefined {
  return operation.statements.find((stmt) => stmt.keyword === direction);
}

/** The operation node of RFC 7950 §6.4.1: named after the rpc or action, parameters as children. */
export function operationNode(operation: YangStatement, body: YangStatement | undefined): YangStatement {
  const node = new YangStatement({ keyword: "container", name: operation.name });
  if (body) {
    node.statements = body.statements;
  }
  if (operation.defining_module) {
    node.defining_module = operation.defining_module;
  }
  return node;
}

function shallowCopy<T extends object>(value: T): T {
  const copy = Object.assign(Object.create(Object.getPrototypeOf(value)), value) as T;
  const registry = (value as { module_registry?: unknown }).module_registry;
  if (registry !== undefined) {
    Object.defineProperty(copy, "module_registry", { value: registry, enumerable: false });
  }
  return copy;
}

/**
 * Copy of `module` with the operation node in place, and the copies of the parent steps. rpc: the
 * top level is the data nodes plus `operation`; other operations are not data nodes and are left out.
 * action: each statement from the top level down to the parent is copied, and the parent's copy has
 * `operation` in place of the action.
 */
export function accessibleModule(
  module: YangModule,
  target: OperationTarget,
  operation: YangStatement
): { module: YangModule; parentCopies: YangStatement[] } {
  const accessible = shallowCopy(module);
  if (target.parents.length === 0) {
    accessible.statements = [...module.statements.filter((stmt) => stmt.keyword !== "rpc"), operation];
    return { module: accessible, parentCopies: [] };
  }
  const chain = target.parents.flatMap((step) => [...step.wrappers, step.stmt]);
  const copies = new Map<YangStatement, YangStatement>();
  let node: { statements: YangStatement[] } = accessible;
  for (const original of chain) {
    const child = shallowCopy(original);
    copies.set(original, child);
    node.statements = node.statements.map((s) => (s === original ? child : s));
    node = child;
  }
  node.statements = node.statements.map((s) => (s === target.operation ? operation : s));
  return { module: accessible, parentCopies: target.parents.map((step) => copies.get(step.stmt) as YangStatement) };
}

/** Canonical text of a decoded leaf value, as an RFC 8040 key value is written. */
export function lexical(value: unknown): string {
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

/** RFC 8040 §3.6 member name of the operation body: `module:input` or `module:output`. */
export function wrapperMember(moduleName: string, direction: OperationDirection): string {
  return `${moduleName}:${direction}`;
}
