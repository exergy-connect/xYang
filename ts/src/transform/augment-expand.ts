/**
 * Resolve RFC 7950 ``augment`` targets and merge augmented schema into the target module.
 *
 * Called from the parser only when ``expandUses`` is True, so ``expandUses=false`` keeps
 * ``augment`` as explicit statements in the AST—matching the reversibility goal of
 * preserving ``uses``/grouping structure for round-trip convert paths.
 */

import { YangSyntaxError } from "../core/errors";
import { parseAbsoluteSchemaPath, type YangIdentifierRef } from "../core/identifier-ref";
import { SerializedStatement, YangModule } from "../core/model";

type ModuleData = Record<string, unknown>;

const SCHEMA_NODE_KEYWORDS = new Set([
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

function deepCloneStatement(stmt: SerializedStatement): SerializedStatement {
  return JSON.parse(JSON.stringify(stmt)) as SerializedStatement;
}

function asStatements(value: unknown): SerializedStatement[] {
  return Array.isArray(value) ? (value as SerializedStatement[]) : [];
}

function ownPrefix(module: ModuleData): string {
  return String(module.prefix ?? "").replace(/^['"]|['"]$/g, "");
}

function resolvePrefixedModule(ctxModule: ModuleData, prefix: string): ModuleData | undefined {
  if (prefix === ownPrefix(ctxModule)) {
    return ctxModule;
  }
  const imports = ctxModule.import_prefixes as Record<string, ModuleData> | undefined;
  const resolved = imports?.[prefix];
  return resolved && typeof resolved === "object" ? resolved : undefined;
}

function pathSegmentsFromAugment(aug: SerializedStatement, path: string): YangIdentifierRef[] {
  const stored = aug.augment_path_segments;
  if (Array.isArray(stored) && stored.length > 0) {
    return stored as YangIdentifierRef[];
  }
  try {
    return parseAbsoluteSchemaPath(path);
  } catch (err) {
    throw new YangSyntaxError(err instanceof Error ? err.message : String(err));
  }
}

function isSchemaNode(stmt: SerializedStatement): boolean {
  const kw = typeof stmt.keyword === "string" ? stmt.keyword : "";
  return Boolean(stmt.name) && SCHEMA_NODE_KEYWORDS.has(kw);
}

function findNamedSchemaChild(parent: SerializedStatement, name: string): SerializedStatement | undefined {
  for (const child of asStatements(parent.statements)) {
    if (child.name === name && isSchemaNode(child)) {
      return child;
    }
  }
  return undefined;
}

function findToplevelSchemaChild(module: ModuleData, name: string): SerializedStatement | undefined {
  for (const child of asStatements(module.statements)) {
    if (child.name === name && isSchemaNode(child)) {
      return child;
    }
  }
  return undefined;
}

/**
 * Resolve an absolute augment path to the target schema node that receives new children.
 * Prefers parse-time ``augment_path_segments``; falls back to parsing ``path`` once.
 */
export function resolveAugmentTarget(
  ctxModule: ModuleData,
  path: string,
  aug?: SerializedStatement
): SerializedStatement {
  return resolveAbsoluteSchemaPath({
    ctxModule,
    path,
    segments: aug ? pathSegmentsFromAugment(aug, path) : undefined,
    kind: "augment",
    findToplevel: findToplevelSchemaChild
  });
}

export function resolveAbsoluteSchemaPath(options: {
  ctxModule: ModuleData;
  path: string;
  segments?: YangIdentifierRef[];
  kind: string;
  findToplevel: (module: ModuleData, name: string) => SerializedStatement | undefined;
}): SerializedStatement {
  const { ctxModule, path, kind, findToplevel } = options;
  let segments = options.segments;
  if (!segments || segments.length === 0) {
    try {
      segments = parseAbsoluteSchemaPath(path);
    } catch (err) {
      throw new YangSyntaxError(err instanceof Error ? err.message : String(err));
    }
  }
  const first = segments[0]!;
  const pref0 = first.prefix!;
  const name0 = first.name;
  const mod0 = resolvePrefixedModule(ctxModule, pref0);
  if (!mod0) {
    throw new YangSyntaxError(
      `${kind}: unknown prefix '${pref0}' in path '${path}' ` +
        `(module '${String(ctxModule.name ?? "")}')`
    );
  }
  let cur = findToplevel(mod0, name0);
  if (!cur) {
    throw new YangSyntaxError(
      `${kind}: no top-level schema node '${name0}' in module '${String(mod0.name ?? "")}' ` +
        `(path '${path}')`
    );
  }
  for (const seg of segments.slice(1)) {
    const pref = seg.prefix!;
    const nm = seg.name;
    if (!resolvePrefixedModule(ctxModule, pref)) {
      throw new YangSyntaxError(`${kind}: unknown prefix '${pref}' in path '${path}'`);
    }
    const nxt = findNamedSchemaChild(cur, nm);
    if (!nxt) {
      throw new YangSyntaxError(
        `${kind}: no child '${nm}' under node in path '${path}' ` + `(after '${String(cur.name ?? "")}')`
      );
    }
    cur = nxt;
  }
  if (!Array.isArray(cur.statements) && cur.statements !== undefined) {
    throw new YangSyntaxError(
      `${kind}: target node '${String(cur.name ?? "?")}' cannot contain ` +
        `schema substatements (path '${path}')`
    );
  }
  if (cur.statements === undefined) {
    cur.statements = [];
  }
  return cur;
}

function stampDefiningModule(stmt: SerializedStatement, moduleName: string): void {
  stmt.defining_module = moduleName;
  for (const child of asStatements(stmt.statements)) {
    stampDefiningModule(child, moduleName);
  }
}

function mergeIfFeaturesFromAugment(aug: SerializedStatement, child: SerializedStatement): void {
  const ufs = aug.if_features;
  if (!Array.isArray(ufs) || ufs.length === 0) {
    return;
  }
  const existing = Array.isArray(child.if_features) ? (child.if_features as string[]) : [];
  child.if_features = [...ufs, ...existing];
}

function mergeWhenFromAugment(aug: SerializedStatement, child: SerializedStatement): void {
  const uw = aug.when as Record<string, unknown> | undefined;
  if (!uw || typeof uw.expression !== "string" || uw.expression.trim() === "") {
    return;
  }
  const usesWhen: Record<string, unknown> = {
    ...deepCloneStatement(uw as SerializedStatement),
    evaluate_with_parent_context: true
  };
  const existing = child.when as Record<string, unknown> | undefined;
  if (!existing?.expression) {
    child.when = usesWhen;
    return;
  }
  child.when = {
    ...existing,
    expression: `(${String(existing.expression)}) and (${uw.expression})`,
    description: String(existing.description ?? ""),
    evaluate_with_parent_context: true
  };
}

function mergeAugmentIntoTarget(
  aug: SerializedStatement,
  target: SerializedStatement,
  sourceModuleName: string
): void {
  const copies = asStatements(aug.statements).map((x) => deepCloneStatement(x));
  for (const c of copies) {
    stampDefiningModule(c, sourceModuleName);
    mergeIfFeaturesFromAugment(aug, c);
    mergeWhenFromAugment(aug, c);
  }
  const targetChildren = asStatements(target.statements);
  for (const c of copies) {
    targetChildren.push(c);
  }
  target.statements = targetChildren;
}

/**
 * Register *mod* and every module reachable via ``import`` (RFC 7950 import closure).
 * ``import_prefixes`` values are module *data* records (shared with the parser cache).
 */
export function registerModuleClosure(modules: Map<string, YangModule>, mod: YangModule): void {
  const name = mod.name;
  if (!name) {
    return;
  }
  modules.set(name, mod);
  const imports = (mod.data.import_prefixes as Record<string, ModuleData> | undefined) ?? {};
  for (const importedData of Object.values(imports)) {
    if (!importedData || typeof importedData !== "object") {
      continue;
    }
    const importedName = typeof importedData.name === "string" ? importedData.name : "";
    if (!importedName || modules.has(importedName)) {
      continue;
    }
    // Wrap shared data so later merges mutate the same object the parser cached.
    registerModuleClosure(modules, new YangModule(importedData, { kind: "string", value: importedName }));
  }
}

/**
 * Apply every top-level ``augment`` still present in any module in *modules*.
 *
 * Use after loading a set of related modules so augments defined in one file merge into
 * targets in another module that shares the same module data instances (one
 * {@link YangParser} cache per load batch).
 */
export function applyAugmentationsAcrossModuleMap(modules: Map<string, YangModule> | Record<string, YangModule>): void {
  const list = modules instanceof Map ? [...modules.values()] : Object.values(modules);
  const pending: Array<{ mod: YangModule; aug: SerializedStatement }> = [];
  const seen = new Set<ModuleData>();
  for (const mod of list) {
    if (seen.has(mod.data)) {
      continue;
    }
    seen.add(mod.data);
    for (const stmt of asStatements(mod.data.statements)) {
      if (stmt.keyword === "augment") {
        pending.push({ mod, aug: stmt });
      }
    }
  }
  for (const { mod, aug } of pending) {
    const path = String(aug.augment_path ?? aug.argument ?? "");
    const target = resolveAugmentTarget(mod.data, path, aug);
    mergeAugmentIntoTarget(aug, target, String(mod.name ?? ""));
  }
  for (const mod of list) {
    const stmts = asStatements(mod.data.statements);
    mod.data.statements = stmts.filter((s) => s.keyword !== "augment");
  }
}

/**
 * For each top-level ``augment``, copy its (already ``uses``-expanded) children onto the
 * target node, merge ``if-feature`` / ``when`` like ``uses``, then remove the
 * ``augment`` statement from *module*.
 */
export function applyAugments(module: YangModule): YangModule {
  const data = module.data;
  const statements = asStatements(data.statements);
  const augments = statements.filter((s) => s.keyword === "augment");
  if (augments.length === 0) {
    return module;
  }
  const sourceName = String(data.name ?? "");
  for (const aug of augments) {
    const path = String(aug.augment_path ?? aug.argument ?? "");
    const target = resolveAugmentTarget(data, path, aug);
    mergeAugmentIntoTarget(aug, target, sourceName);
  }
  data.statements = statements.filter((s) => s.keyword !== "augment");
  return module;
}
