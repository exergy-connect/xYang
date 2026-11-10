/**
 * Resolve RFC 7950 ``augment`` targets and merge augmented schema into the target module.
 *
 * Called from the parser only when ``expandUses`` is True, so ``expandUses=false`` keeps
 * ``augment`` as explicit statements in the AST—matching the reversibility goal of
 * preserving ``uses``/grouping structure for round-trip convert paths.
 */

import { YangSemanticError, YangSyntaxError } from "../core/errors";
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

function walkAbsoluteSchemaPath(options: {
  ctxModule: ModuleData;
  path: string;
  segments?: YangIdentifierRef[];
  kind: string;
  findToplevel: (module: ModuleData, name: string) => SerializedStatement | undefined;
}): { parent: ModuleData | SerializedStatement; node: SerializedStatement } {
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
  let parent: ModuleData | SerializedStatement = mod0;
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
    parent = cur;
    cur = nxt;
  }
  return { parent, node: cur };
}

export function resolveAbsoluteSchemaPath(options: {
  ctxModule: ModuleData;
  path: string;
  segments?: YangIdentifierRef[];
  kind: string;
  findToplevel: (module: ModuleData, name: string) => SerializedStatement | undefined;
}): SerializedStatement {
  const cur = walkAbsoluteSchemaPath(options).node;
  if (!Array.isArray(cur.statements) && cur.statements !== undefined) {
    throw new YangSyntaxError(
      `${options.kind}: target node '${String(cur.name ?? "?")}' cannot contain ` +
        `schema substatements (path '${options.path}')`
    );
  }
  if (cur.statements === undefined) {
    cur.statements = [];
  }
  return cur;
}

function removeSchemaChild(parent: ModuleData | SerializedStatement, node: SerializedStatement): void {
  const stmts = asStatements((parent as { statements?: unknown }).statements);
  const idx = stmts.indexOf(node);
  if (idx < 0) {
    throw new YangSemanticError(
      `deviation: target node '${String(node.name ?? "?")}' is not a child of its parent`
    );
  }
  stmts.splice(idx, 1);
  (parent as { statements: SerializedStatement[] }).statements = stmts;
}

function cowStatement(stmt: SerializedStatement): SerializedStatement {
  return {
    ...stmt,
    statements: asStatements(stmt.statements).slice()
  };
}

function cowModuleData(data: ModuleData): ModuleData {
  const imports = (data.import_prefixes as Record<string, ModuleData> | undefined) ?? {};
  return {
    ...data,
    statements: asStatements(data.statements).slice(),
    import_prefixes: { ...imports }
  };
}

function schemaChildIndex(parent: ModuleData | SerializedStatement, name: string): number {
  return asStatements((parent as { statements?: unknown }).statements).findIndex(
    (stmt) => stmt.name === name && isSchemaNode(stmt)
  );
}

function detachCopiedPath(moduleData: ModuleData, segments: YangIdentifierRef[]): void {
  const pathText = `/${segments.map((seg) => `${seg.prefix}:${seg.name}`).join("/")}`;
  const top = asStatements(moduleData.statements);
  const topIdx = schemaChildIndex(moduleData, segments[0]!.name);
  if (topIdx < 0) {
    throw new YangSemanticError(`deviation: no schema node for path '${pathText}'`);
  }
  if (segments.length === 1) {
    top.splice(topIdx, 1);
    moduleData.statements = top;
    return;
  }
  let current = cowStatement(top[topIdx]!);
  top[topIdx] = current;
  moduleData.statements = top;
  for (const seg of segments.slice(1, -1)) {
    const children = asStatements(current.statements);
    const idx = schemaChildIndex(current, seg.name);
    if (idx < 0) {
      throw new YangSemanticError(`deviation: no child '${seg.name}' under '${String(current.name ?? "?")}'`);
    }
    const next = cowStatement(children[idx]!);
    children[idx] = next;
    current.statements = children;
    current = next;
  }
  const last = segments[segments.length - 1]!.name;
  const children = asStatements(current.statements);
  const idx = schemaChildIndex(current, last);
  if (idx < 0) {
    throw new YangSemanticError(`deviation: no child '${last}' under '${String(current.name ?? "?")}'`);
  }
  children.splice(idx, 1);
  current.statements = children;
}

function privateTargetModule(
  root: ModuleData,
  owner: ModuleData,
  copies: Map<ModuleData, ModuleData>
): ModuleData {
  if (owner === root) {
    return root;
  }
  for (const cloned of copies.values()) {
    if (cloned === owner) {
      return owner;
    }
  }
  const existing = copies.get(owner);
  if (existing) {
    return existing;
  }
  const cloned = cowModuleData(owner);
  copies.set(owner, cloned);
  const imports = (root.import_prefixes as Record<string, ModuleData> | undefined) ?? {};
  root.import_prefixes = imports;
  for (const [prefix, mod] of Object.entries(imports)) {
    if (mod === owner) {
      imports[prefix] = cloned;
    }
  }
  return cloned;
}

function applyNotSupported(
  ctxModule: ModuleData,
  dev: SerializedStatement,
  copies: Map<ModuleData, ModuleData>
): void {
  const path = String(dev.deviation_path ?? dev.argument ?? "");
  const stored = dev.deviation_path_segments;
  const segments =
    Array.isArray(stored) && stored.length > 0 ? (stored as YangIdentifierRef[]) : parseAbsoluteSchemaPath(path);
  let located: { parent: ModuleData | SerializedStatement; node: SerializedStatement };
  try {
    located = walkAbsoluteSchemaPath({
      ctxModule,
      path,
      segments,
      kind: "deviation",
      findToplevel: findToplevelSchemaChild
    });
  } catch (err) {
    if (err instanceof YangSyntaxError) {
      throw new YangSemanticError(err.message);
    }
    throw err;
  }
  const owner = resolvePrefixedModule(ctxModule, segments[0]!.prefix!);
  if (!owner) {
    throw new YangSemanticError(`deviation: unknown prefix '${segments[0]!.prefix}' in path '${path}'`);
  }
  if (owner === ctxModule) {
    removeSchemaChild(located.parent, located.node);
    return;
  }
  const privateModule = privateTargetModule(ctxModule, owner, copies);
  detachCopiedPath(privateModule, segments);
}

/**
 * Remove each ``deviate not-supported`` target, then drop ``deviation`` statements.
 * Same absolute-path resolution as ``augment``. A missing target is a {@link YangSemanticError}.
 * A target in another module is removed on a copy owned by this build; the cached module is unchanged.
 */
export function applyDeviations(module: YangModule): YangModule {
  const data = module.data;
  const statements = asStatements(data.statements);
  const deviations = statements.filter((s) => s.keyword === "deviation");
  const copies = new Map<ModuleData, ModuleData>();
  for (const dev of deviations) {
    if (dev.not_supported === true) {
      applyNotSupported(data, dev, copies);
    }
  }
  if (deviations.length > 0) {
    data.statements = statements.filter((s) => s.keyword !== "deviation");
  }
  return module;
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
  const seenDev = new Set<ModuleData>();
  for (const mod of list) {
    if (seenDev.has(mod.data)) {
      continue;
    }
    seenDev.add(mod.data);
    applyDeviations(mod);
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
