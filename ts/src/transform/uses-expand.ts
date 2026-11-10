import { YangCircularUsesError, YangRefineTargetNotFoundError, YangSemanticError, YangSyntaxError } from "../core/errors";
import {
  formatIdentifierRef,
  type YangIdentifierRef
} from "../core/identifier-ref";
import { SerializedStatement, YangModule } from "../core/model";
import { YangTokenType } from "../parser/parser-context";

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

/**
 * Same result as `deepClone(stmt)` for a statement whose `statements` list the caller replaces
 * right away. Copies every other field through JSON in key order and leaves the children for the
 * caller, so a subtree is not cloned again at each level of `expandStatementList`.
 */
function cloneStatementShell(stmt: SerializedStatement): SerializedStatement {
  const copy: Record<string, unknown> = {};
  for (const key of Object.keys(stmt)) {
    const value = (stmt as Record<string, unknown>)[key];
    if (key === "statements" && Array.isArray(value) && value.length > 0) {
      copy[key] = value;
      continue;
    }
    const text = JSON.stringify(value);
    if (text !== undefined) {
      copy[key] = JSON.parse(text);
    }
  }
  return copy as SerializedStatement;
}

/** Scope for resolving `uses` names (local module or defining module of an imported grouping). */
type GroupingScope = {
  groupings: Record<string, SerializedStatement>;
  import_prefixes: Record<string, Record<string, unknown>>;
  /** This module's own prefix. ``uses own:grouping`` resolves locally (RFC 7950). */
  prefix?: string;
};

function modulePrefix(moduleData: Record<string, unknown> | undefined): string | undefined {
  if (!moduleData) {
    return undefined;
  }
  const prefix = String(moduleData.prefix ?? "").replace(/^['"]|['"]$/g, "");
  return prefix.length > 0 ? prefix : undefined;
}

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
    if (scope.prefix && ref.prefix === scope.prefix) {
      const grouping = scope.groupings[ref.name];
      if (!grouping) {
        throw new YangSemanticError(`Unknown grouping '${key}'`);
      }
      return { key, grouping, nestedScope: scope };
    }
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
        import_prefixes: asImportMap(imp.import_prefixes),
        prefix: modulePrefix(imp)
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

const SCHEMA_WALK = new Set([
  "container",
  "list",
  "leaf",
  "leaf-list",
  "choice",
  "case",
  "anydata",
  "anyxml",
  "notification",
  "rpc",
  "action",
  "input",
  "output"
]);

function isWalkable(stmt: SerializedStatement): boolean {
  return typeof stmt.keyword === "string" && SCHEMA_WALK.has(stmt.keyword);
}

/** Direct schema children. Choice branches flatten to case bodies (Python ``statement_children``). */
function statementChildren(stmt: SerializedStatement): SerializedStatement[] {
  const kids = stmt.statements ?? [];
  if (stmt.keyword === "choice") {
    const out: SerializedStatement[] = [];
    for (const caseStmt of kids) {
      if (caseStmt.keyword !== "case") {
        continue;
      }
      for (const child of caseStmt.statements ?? []) {
        if (isWalkable(child)) {
          out.push(child);
        }
      }
    }
    return out;
  }
  return kids.filter(isWalkable);
}

function casesOf(stmt: SerializedStatement): SerializedStatement[] {
  if (stmt.keyword !== "choice") {
    return [];
  }
  return (stmt.statements ?? []).filter((child) => child.keyword === "case");
}

/** Python ``find_nodes_by_refine_path``: choice and case names are path segments. */
function findFromNode(stmt: SerializedStatement, segments: string[], idx: number): SerializedStatement[] {
  const want = segments[idx]!;
  const last = idx === segments.length - 1;
  if (stmt.name === want && isWalkable(stmt)) {
    if (last) {
      return [stmt];
    }
    if (stmt.keyword === "choice" && idx + 1 < segments.length) {
      const caseName = segments[idx + 1]!;
      const matches: SerializedStatement[] = [];
      for (const caseStmt of casesOf(stmt)) {
        if (caseStmt.name !== caseName) {
          continue;
        }
        if (idx + 1 === segments.length - 1) {
          return [caseStmt];
        }
        for (const child of statementChildren(caseStmt)) {
          matches.push(...findFromNode(child, segments, idx + 2));
        }
      }
      return matches;
    }
    const matches: SerializedStatement[] = [];
    for (const child of statementChildren(stmt)) {
      matches.push(...findFromNode(child, segments, idx + 1));
    }
    return matches;
  }
  if (stmt.keyword === "choice") {
    const matches: SerializedStatement[] = [];
    let named = false;
    for (const caseStmt of casesOf(stmt)) {
      if (caseStmt.name !== want) {
        continue;
      }
      named = true;
      if (last) {
        return [caseStmt];
      }
      for (const child of statementChildren(caseStmt)) {
        matches.push(...findFromNode(child, segments, idx + 1));
      }
    }
    if (named) {
      return matches;
    }
  }
  const matches: SerializedStatement[] = [];
  for (const child of statementChildren(stmt)) {
    matches.push(...findFromNode(child, segments, idx));
  }
  return matches;
}

function findNodesByAugmentPath(nodes: SerializedStatement[], segments: string[]): SerializedStatement[] {
  const out: SerializedStatement[] = [];
  for (const root of nodes) {
    if (!isWalkable(root)) {
      continue;
    }
    out.push(...findFromNode(root, segments, 0));
  }
  return out;
}

function augmentPathSegments(path: string): string[] {
  const raw = path.trim().replace(/^['"]|['"]$/g, "");
  if (!raw || raw.startsWith("/") || raw.includes("[") || raw.includes(" ")) {
    throw new YangSyntaxError(`invalid augment path '${raw}'`);
  }
  const parts = raw.split("/");
  if (parts.some((part) => part.trim() === "")) {
    throw new YangSyntaxError(`invalid augment path '${raw}'`);
  }
  return parts.map((part) => {
    const trimmed = part.trim();
    const colon = trimmed.indexOf(":");
    return colon >= 0 ? trimmed.slice(colon + 1) : trimmed;
  });
}

/**
 * RFC 7950 §7.13 / §7.17: merge ``augment`` substatements of ``uses`` into the expanded grouping.
 * Port of Python ``_apply_uses_augmentations``.
 */
function applyAugmentsFromUses(usesStmt: SerializedStatement, body: SerializedStatement[]): void {
  const augmentations = usesStmt.augmentations as SerializedStatement[] | undefined;
  if (!Array.isArray(augmentations) || augmentations.length === 0) {
    return;
  }
  const groupingName =
    (typeof usesStmt.argument === "string" && usesStmt.argument) ||
    (typeof usesStmt.grouping_name === "string" && usesStmt.grouping_name) ||
    "uses";
  for (const aug of augmentations) {
    const path = String(aug.path ?? aug.augment_path ?? aug.argument ?? "");
    let segments: string[];
    try {
      segments = augmentPathSegments(path);
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      throw new YangSyntaxError(`uses '${groupingName}' augment: invalid path '${path}': ${detail}`);
    }
    const targets = findNodesByAugmentPath(body, segments);
    if (targets.length === 0) {
      throw new YangSyntaxError(`uses '${groupingName}' augment: no target for path '${path}'`);
    }
    if (targets.length !== 1) {
      throw new YangSyntaxError(
        `uses '${groupingName}' augment: path '${path}' matched ${targets.length} nodes, expected one`
      );
    }
    const target = targets[0]!;
    if (!Array.isArray(target.statements)) {
      throw new YangSyntaxError(
        `uses '${groupingName}' augment: target '${target.name ?? "?"}' ` +
          `cannot contain schema substatements (path '${path}')`
      );
    }
    const copies = (aug.statements ?? []).map((stmt) => deepClone(stmt));
    for (const copy of copies) {
      mergeIfFeaturesFromParentUses(aug, copy);
      mergeWhenFromParentUses(aug, copy);
    }
    target.statements = [...target.statements, ...copies];
  }
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
      applyAugmentsFromUses(child, body);
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
      applyAugmentsFromUses(stmt, expanded);
      applyRefinesFromUses(stmt, expanded);
      for (const e of expanded) {
        mergeIfFeaturesFromParentUses(stmt, e);
        mergeWhenFromParentUses(stmt, e);
        out.push(expandUsesUnderStatement(e, scope, stack, hostTypedefs));
      }
    } else {
      out.push(expandUsesUnderStatement(cloneStatementShell(stmt), scope, stack, hostTypedefs));
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
  // Imported modules are restored by reference below, so do not clone them first.
  const cloned = (
    sharedImports && typeof sharedImports === "object" ? deepClone({ ...data, import_prefixes: {} }) : deepClone(data)
  ) as Record<string, unknown>;
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
    import_prefixes: asImportMap(cloned.import_prefixes),
    prefix: modulePrefix(cloned)
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
