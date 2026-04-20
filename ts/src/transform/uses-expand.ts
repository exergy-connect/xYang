import { YangCircularUsesError, YangRefineTargetNotFoundError, YangSemanticError } from "../core/errors";
import { SerializedStatement, YangModule } from "../core/model";
import { YangTokenType } from "../parser/parser-context";

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
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
    const extra = rf.statements ?? [];
    if (extra.length > 0) {
      target.statements = [...(target.statements ?? []), ...deepClone(extra)];
    }
  }
}

function expandGroupingBody(
  groupingName: string,
  groupings: Record<string, SerializedStatement>,
  stack: string[]
): SerializedStatement[] {
  if (stack.includes(groupingName)) {
    throw new YangCircularUsesError(stack, groupingName);
  }
  const g = groupings[groupingName];
  if (!g) {
    throw new YangSemanticError(`Unknown grouping '${groupingName}'`);
  }
  const nextStack = [...stack, groupingName];
  const rawChildren = (g.statements ?? []) as SerializedStatement[];
  const flattened: SerializedStatement[] = [];
  for (const child of rawChildren) {
    if (child.keyword === "uses") {
      const gn = String(child.grouping_name ?? child.argument ?? "").trim();
      if (!gn) {
        continue;
      }
      const body = expandGroupingBody(gn, groupings, nextStack);
      applyRefinesFromUses(child, body);
      for (const stmt of body) {
        mergeIfFeaturesFromParentUses(child, stmt);
        mergeWhenFromParentUses(child, stmt);
        flattened.push(deepClone(stmt));
      }
    } else {
      flattened.push(deepClone(child));
    }
  }
  return flattened.map((stmt) => expandUsesUnderStatement(stmt, groupings, nextStack));
}

function expandUsesUnderStatement(
  stmt: SerializedStatement,
  groupings: Record<string, SerializedStatement>,
  stack: string[]
): SerializedStatement {
  if (stmt.statements?.length) {
    stmt.statements = expandStatementList(stmt.statements, groupings, stack);
  }
  return stmt;
}

function expandStatementList(
  statements: SerializedStatement[],
  groupings: Record<string, SerializedStatement>,
  stack: string[]
): SerializedStatement[] {
  const out: SerializedStatement[] = [];
  for (const stmt of statements) {
    if (stmt.keyword === "uses") {
      const gn = String(stmt.grouping_name ?? stmt.argument ?? "").trim();
      if (!gn) {
        continue;
      }
      const expanded = expandGroupingBody(gn, groupings, stack);
      applyRefinesFromUses(stmt, expanded);
      for (const e of expanded) {
        mergeIfFeaturesFromParentUses(stmt, e);
        mergeWhenFromParentUses(stmt, e);
        out.push(expandUsesUnderStatement(e, groupings, stack));
      }
    } else {
      out.push(expandUsesUnderStatement(deepClone(stmt), groupings, stack));
    }
  }
  return out;
}

/**
 * Expand all `uses` statements by inlining grouping definitions (RFC 7950 compile-time view).
 * Detects circular `uses` chains between groupings and throws {@link YangCircularUsesError}.
 */
export function expandUses(module: YangModule): YangModule {
  const data = module.data as Record<string, unknown>;
  const groupings = data.groupings as Record<string, SerializedStatement> | undefined;
  if (!groupings || Object.keys(groupings).length === 0) {
    return module;
  }

  const cloned = deepClone(data) as Record<string, unknown>;
  if (data.features instanceof Set) {
    cloned.features = new Set(data.features as Set<string>);
  }
  if (data.feature_if_features && typeof data.feature_if_features === "object") {
    cloned.feature_if_features = { ...(data.feature_if_features as Record<string, string[]>) };
  }
  const g = cloned.groupings as Record<string, SerializedStatement>;
  const top = (cloned.statements as SerializedStatement[]) ?? [];
  cloned.statements = expandStatementList(top, g, []);
  delete cloned.groupings;
  return new YangModule(cloned, module.source);
}
