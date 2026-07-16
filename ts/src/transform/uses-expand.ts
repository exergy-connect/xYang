import { YangCircularUsesError, YangRefineTargetNotFoundError, YangSemanticError } from "../core/errors";
import {
  formatIdentifierRef,
  type YangIdentifierRef
} from "../core/identifier-ref";
import { SerializedStatement, YangModule } from "../core/model";
import { YangTokenType } from "../parser/parser-context";

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

/** Scope for resolving `uses` names (local module or defining module of an imported grouping). */
type GroupingScope = {
  groupings: Record<string, SerializedStatement>;
  import_prefixes: Record<string, Record<string, unknown>>;
};

function asGroupingMap(value: unknown): Record<string, SerializedStatement> {
  if (!value || typeof value !== "object") {
    return {};
  }
  return value as Record<string, SerializedStatement>;
}

function asImportMap(value: unknown): Record<string, Record<string, unknown>> {
  if (!value || typeof value !== "object") {
    return {};
  }
  return value as Record<string, Record<string, unknown>>;
}

/**
 * Read the identifier-ref written by the parser onto a serialized ``uses`` node.
 * Values are already normalized at parse time (no trim / no string splitting here).
 */
function usesGroupingRef(usesStmt: SerializedStatement): YangIdentifierRef | undefined {
  if (typeof usesStmt.grouping_name !== "string" || !usesStmt.grouping_name) {
    return undefined;
  }
  const name = usesStmt.grouping_name;
  const prefix =
    typeof usesStmt.grouping_prefix === "string" && usesStmt.grouping_prefix
      ? usesStmt.grouping_prefix
      : undefined;
  return prefix ? { prefix, name } : { name };
}

/**
 * Resolve a grouping from a parse-time identifier-ref (Python ``_resolve_uses_grouping``).
 * Nested ``uses`` inside an imported grouping resolve against that module's scope.
 */
function resolveGrouping(
  ref: YangIdentifierRef,
  scope: GroupingScope
): { key: string; grouping: SerializedStatement; nestedScope: GroupingScope } {
  const key = formatIdentifierRef(ref);
  if (!ref.name) {
    throw new YangSemanticError("Empty grouping name in uses");
  }
  if (ref.prefix) {
    const imp = scope.import_prefixes[ref.prefix];
    if (!imp) {
      throw new YangSemanticError(`Unknown import prefix '${ref.prefix}' in uses '${key}'`);
    }
    const groupings = asGroupingMap(imp.groupings);
    const grouping = groupings[ref.name];
    if (!grouping) {
      throw new YangSemanticError(`Unknown grouping '${key}'`);
    }
    return {
      key,
      grouping,
      nestedScope: {
        groupings,
        import_prefixes: asImportMap(imp.import_prefixes)
      }
    };
  }
  const grouping = scope.groupings[ref.name];
  if (!grouping) {
    throw new YangSemanticError(`Unknown grouping '${key}'`);
  }
  return { key, grouping, nestedScope: scope };
}

/** RFC 7950: `if-feature` on `uses` applies to expanded nodes (conjunction with any existing if-features). */
function mergeIfFeaturesFromParentUses(usesStmt: SerializedStatement, child: SerializedStatement): void {
  const ufs = usesStmt.if_features;
  if (!Array.isArray(ufs) || ufs.length === 0) {
    return;
  }
  const existing = Array.isArray(child.if_features) ? child.if_features : [];
  child.if_features = [...ufs, ...existing];
}

/** RFC 7950: `when` on `uses` applies to all schema nodes expanded from that `uses`. */
function mergeWhenFromParentUses(usesStmt: SerializedStatement, child: SerializedStatement): void {
  const uw = usesStmt.when as Record<string, unknown> | undefined;
  if (!uw || typeof uw.expression !== "string" || uw.expression.trim() === "") {
    return;
  }
  const usesWhen: Record<string, unknown> = {
    ...deepClone(uw),
    evaluate_with_parent_context: true
  };
  const existing = child.when as Record<string, unknown> | undefined;
  if (!existing?.expression) {
    child.when = usesWhen as SerializedStatement["when"];
    return;
  }
  child.when = {
    ...existing,
    expression: `(${existing.expression}) and (${uw.expression})`,
    description: String(existing.description ?? ""),
    evaluate_with_parent_context: true
  };
}

/** Depth-first match for schema node name (refine targets may sit under choice/case). */
function findNodeByNameDepthFirst(nodes: SerializedStatement[], name: string): SerializedStatement | undefined {
  for (const n of nodes) {
    if (n.name === name) {
      return n;
    }
  }
  for (const n of nodes) {
    const hit = findNodeByNameDepthFirst(n.statements ?? [], name);
    if (hit) {
      return hit;
    }
  }
  return undefined;
}

function findRefineTarget(nodes: SerializedStatement[], segments: string[]): SerializedStatement | undefined {
  if (segments.length === 0) {
    return undefined;
  }
  const [head, ...rest] = segments;
  const found = findNodeByNameDepthFirst(nodes, head);
  if (!found) {
    return undefined;
  }
  if (rest.length === 0) {
    return found;
  }
  return findRefineTarget(found.statements ?? [], rest);
}

function applyRefinesFromUses(usesStmt: SerializedStatement, expanded: SerializedStatement[]): void {
  const refines = usesStmt.refines as SerializedStatement[] | undefined;
  if (!Array.isArray(refines) || refines.length === 0) {
    return;
  }
  for (const rf of refines) {
    const pathRaw = (rf.refine_target_path ?? rf.argument ?? "") as string;
    const segments = pathRaw.split("/").map((s) => s.trim()).filter(Boolean);
    if (segments.length === 0) {
      continue;
    }
    const target = findRefineTarget(expanded, segments);
    if (!target) {
      throw new YangRefineTargetNotFoundError(pathRaw);
    }
    if (typeof rf.min_elements === "number") {
      target.min_elements = rf.min_elements;
    }
    if (typeof rf.max_elements === "number") {
      target.max_elements = rf.max_elements;
    }
    if (typeof rf.refined_mandatory === "boolean") {
      target.mandatory = rf.refined_mandatory;
    }
    if (typeof rf.refined_config === "boolean") {
      target.config = rf.refined_config;
    }
    const refinedDefaults = rf.refined_defaults;
    if (Array.isArray(refinedDefaults) && refinedDefaults.length > 0) {
      if (target.keyword === YangTokenType.LEAF) {
        target.default = refinedDefaults[0];
      } else if (target.keyword === YangTokenType.LEAF_LIST) {
        target.defaults = [...refinedDefaults];
      }
    }
    const rif = rf.if_features;
    if (Array.isArray(rif) && rif.length > 0) {
      const cur = Array.isArray(target.if_features) ? target.if_features : [];
      target.if_features = [...rif, ...cur];
    }
    const refinedDesc = typeof rf.description === "string" ? rf.description.trim() : "";
    if (refinedDesc) {
      target.description = refinedDesc;
    }
    const extra = rf.statements ?? [];
    if (extra.length > 0) {
      target.statements = [...(target.statements ?? []), ...deepClone(extra)];
    }
  }
}

/** Register a typedef statement onto the importing module (RFC 7950 scoping). */
function registerOneTypedef(hostTypedefs: Record<string, unknown>, child: SerializedStatement): void {
  const name =
    (typeof child.argument === "string" && child.argument) ||
    (typeof child.name === "string" && child.name) ||
    "";
  if (!name || name in hostTypedefs) {
    return;
  }
  const typeStmt = child.statements?.find((c) => c.keyword === "type");
  hostTypedefs[name] = {
    name,
    description: typeof child.description === "string" ? child.description : "",
    reference: typeof child.reference === "string" ? child.reference : "",
    default: child.default,
    type: child.type ?? typeStmt?.type,
    statements: child.statements ?? []
  };
}

/** Register typedefs from an expanded grouping onto the importing module; omit them from the body. */
function registerGroupingTypedefs(
  hostTypedefs: Record<string, unknown>,
  body: SerializedStatement[]
): SerializedStatement[] {
  const dataNodes: SerializedStatement[] = [];
  for (const child of body) {
    if (child.keyword === "typedef") {
      registerOneTypedef(hostTypedefs, child);
      continue;
    }
    dataNodes.push(child);
  }
  return dataNodes;
}

function expandGroupingBody(
  ref: YangIdentifierRef,
  scope: GroupingScope,
  stack: string[],
  hostTypedefs: Record<string, unknown>
): SerializedStatement[] {
  const resolved = resolveGrouping(ref, scope);
  if (stack.includes(resolved.key)) {
    throw new YangCircularUsesError(stack, resolved.key);
  }
  const nextStack = [...stack, resolved.key];
  const rawChildren = (resolved.grouping.statements ?? []) as SerializedStatement[];
  const flattened: SerializedStatement[] = [];
  for (const child of rawChildren) {
    if (child.keyword === "uses") {
      const childRef = usesGroupingRef(child);
      if (!childRef) {
        continue;
      }
      const body = expandGroupingBody(childRef, resolved.nestedScope, nextStack, hostTypedefs);
      applyRefinesFromUses(child, body);
      for (const stmt of body) {
        mergeIfFeaturesFromParentUses(child, stmt);
        mergeWhenFromParentUses(child, stmt);
        flattened.push(deepClone(stmt));
      }
    } else if (child.keyword === "typedef") {
      // Handled via registerGroupingTypedefs on the collected body.
      flattened.push(deepClone(child));
    } else {
      flattened.push(deepClone(child));
    }
  }
  const withoutTypedefs = registerGroupingTypedefs(hostTypedefs, flattened);
  return withoutTypedefs.map((stmt) => expandUsesUnderStatement(stmt, resolved.nestedScope, nextStack, hostTypedefs));
}

function expandUsesUnderStatement(
  stmt: SerializedStatement,
  scope: GroupingScope,
  stack: string[],
  hostTypedefs: Record<string, unknown>
): SerializedStatement {
  if (stmt.statements?.length) {
    stmt.statements = expandStatementList(stmt.statements, scope, stack, hostTypedefs);
  }
  return stmt;
}

function expandStatementList(
  statements: SerializedStatement[],
  scope: GroupingScope,
  stack: string[],
  hostTypedefs: Record<string, unknown>
): SerializedStatement[] {
  const out: SerializedStatement[] = [];
  for (const stmt of statements) {
    if (stmt.keyword === "uses") {
      const ref = usesGroupingRef(stmt);
      if (!ref) {
        continue;
      }
      const expanded = expandGroupingBody(ref, scope, stack, hostTypedefs);
      applyRefinesFromUses(stmt, expanded);
      for (const e of expanded) {
        mergeIfFeaturesFromParentUses(stmt, e);
        mergeWhenFromParentUses(stmt, e);
        out.push(expandUsesUnderStatement(e, scope, stack, hostTypedefs));
      }
    } else {
      out.push(expandUsesUnderStatement(deepClone(stmt), scope, stack, hostTypedefs));
    }
  }
  return out;
}

/**
 * Expand all `uses` statements by inlining grouping definitions (RFC 7950 compile-time view).
 * Resolves local and ``prefix:name`` groupings via ``import_prefixes`` (Python parity).
 * Detects circular `uses` chains between groupings and throws {@link YangCircularUsesError}.
 *
 * Groupings are retained on the module so importers can still ``uses prefix:grouping``.
 */
export function expandUses(module: YangModule): YangModule {
  const data = module.data as Record<string, unknown>;

  // Preserve shared import module data references so cross-module ``augment``
  // can mutate the same objects held in the parser cache.
  const sharedImports = data.import_prefixes;
  const cloned = deepClone(data) as Record<string, unknown>;
  if (sharedImports && typeof sharedImports === "object") {
    cloned.import_prefixes = sharedImports;
  }
  if (data.features instanceof Set) {
    cloned.features = new Set(data.features as Set<string>);
  }
  if (data.feature_if_features && typeof data.feature_if_features === "object") {
    cloned.feature_if_features = { ...(data.feature_if_features as Record<string, string[]>) };
  }

  // Keep a live view of imported modules' groupings (shared, not deep-cloned away).
  const expandScope: GroupingScope = {
    groupings: asGroupingMap(cloned.groupings),
    import_prefixes: asImportMap(cloned.import_prefixes)
  };

  const hostTypedefs =
    cloned.typedefs && typeof cloned.typedefs === "object"
      ? (cloned.typedefs as Record<string, unknown>)
      : {};
  cloned.typedefs = hostTypedefs;

  const top = (cloned.statements as SerializedStatement[]) ?? [];
  cloned.statements = expandStatementList(top, expandScope, [], hostTypedefs);

  // Expand nested uses inside grouping bodies (Python expand_all_uses_in_module).
  for (const g of Object.values(expandScope.groupings)) {
    if (!g.statements?.length) continue;
    g.statements = expandStatementList(g.statements, expandScope, [], hostTypedefs);
  }

  return new YangModule(cloned, module.source);
}
