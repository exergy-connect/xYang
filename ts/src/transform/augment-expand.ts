/**
 * Resolve RFC 7950 ``augment`` targets and merge augmented schema into the target module.
 *
 * Called from the parser only when ``expandUses`` is True, so ``expandUses=false`` keeps
 * ``augment`` as explicit statements in the AST—matching the reversibility goal of
 * preserving ``uses``/grouping structure for round-trip convert paths.
 */

import { YangSemanticError, YangSyntaxError } from "../core/errors";
import { parseAbsoluteSchemaPath, type YangIdentifierRef } from "../core/identifier-ref";
import { YangStatement, YangModule, type DeviateRecord } from "../core/model";

type ModuleData = YangModule;

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

function deepCloneStatement(stmt: YangStatement): YangStatement {
  return new YangStatement(JSON.parse(JSON.stringify(stmt)) as YangStatement);
}

function asStatements(value: unknown): YangStatement[] {
  return Array.isArray(value) ? (value as YangStatement[]) : [];
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

function pathSegmentsFromAugment(aug: YangStatement, path: string): YangIdentifierRef[] {
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

function isSchemaNode(stmt: YangStatement): boolean {
  const kw = typeof stmt.keyword === "string" ? stmt.keyword : "";
  return Boolean(stmt.name) && SCHEMA_NODE_KEYWORDS.has(kw);
}

/**
 * RFC 7950 §7.14.2 / §7.14.3: every rpc and action has ``input`` and ``output`` schema
 * nodes, written or not. Add the empty node a schema node identifier names.
 */
function materializeOperationIo(parent: YangStatement | ModuleData, name: string): YangStatement | undefined {
  const keyword = (parent as { keyword?: unknown }).keyword;
  if ((keyword !== "rpc" && keyword !== "action") || (name !== "input" && name !== "output")) {
    return undefined;
  }
  const node = new YangStatement({ keyword: name, name, statements: [] });
  const children = asStatements(parent.statements);
  const outputIdx = children.findIndex((child) => child.keyword === "output");
  if (name === "input" && outputIdx >= 0) {
    children.splice(outputIdx, 0, node);
  } else {
    children.push(node);
  }
  parent.statements = children;
  return node;
}

function findNamedSchemaChild(parent: YangStatement, name: string): YangStatement | undefined {
  for (const child of asStatements(parent.statements)) {
    if (child.name === name && isSchemaNode(child)) {
      return child;
    }
  }
  return materializeOperationIo(parent, name);
}

function findToplevelSchemaChild(module: ModuleData, name: string): YangStatement | undefined {
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
  aug?: YangStatement
): YangStatement {
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
  findToplevel: (module: ModuleData, name: string) => YangStatement | undefined;
}): { parent: ModuleData | YangStatement; node: YangStatement } {
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
  let parent: ModuleData | YangStatement = mod0;
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
  findToplevel: (module: ModuleData, name: string) => YangStatement | undefined;
}): YangStatement {
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

function removeSchemaChild(parent: ModuleData | YangStatement, node: YangStatement): void {
  const stmts = asStatements((parent as { statements?: unknown }).statements);
  const idx = stmts.indexOf(node);
  if (idx < 0) {
    throw new YangSemanticError(
      `deviation: target node '${String(node.name ?? "?")}' is not a child of its parent`
    );
  }
  stmts.splice(idx, 1);
  (parent as { statements: YangStatement[] }).statements = stmts;
}

function cowStatement(stmt: YangStatement): YangStatement {
  const copy = new YangStatement(stmt);
  copy.statements = stmt.statements.slice();
  return copy;
}

function cowModuleData(data: ModuleData): ModuleData {
  return new YangModule(
    {
      name: data.name,
      yang_version: data.yang_version,
      namespace: data.namespace,
      prefix: data.prefix,
      organization: data.organization,
      contact: data.contact,
      description: data.description,
      typedefs: data.typedefs,
      identities: data.identities,
      import_prefixes: { ...data.import_prefixes },
      extensions: data.extensions,
      extension_runtime: data.extension_runtime,
      features: data.features,
      feature_if_features: data.feature_if_features,
      groupings: data.groupings,
      statements: data.statements.slice()
    },
    data.source
  );
}

function schemaChildIndex(parent: ModuleData | YangStatement, name: string): number {
  const idx = asStatements((parent as { statements?: unknown }).statements).findIndex(
    (stmt) => stmt.name === name && isSchemaNode(stmt)
  );
  if (idx >= 0) {
    return idx;
  }
  const node = materializeOperationIo(parent, name);
  return node ? parent.statements.indexOf(node) : -1;
}

/** Copy the ancestors of the node *segments* name; return the copied parent and the target index. */
function copiedPathToTarget(
  moduleData: ModuleData,
  segments: YangIdentifierRef[]
): { parent: ModuleData | YangStatement; index: number } {
  const pathText = `/${segments.map((seg) => `${seg.prefix}:${seg.name}`).join("/")}`;
  const missing = (name: string, under: string) =>
    new YangSemanticError(`deviation: no child '${name}' under '${under}' (path '${pathText}')`);
  let parent: ModuleData | YangStatement = moduleData;
  parent.statements = asStatements(parent.statements).slice();
  let index = schemaChildIndex(parent, segments[0]!.name);
  if (index < 0) {
    throw missing(segments[0]!.name, String(moduleData.name ?? "?"));
  }
  for (const seg of segments.slice(1)) {
    const current = cowStatement(parent.statements[index]!);
    parent.statements[index] = current;
    parent = current;
    index = schemaChildIndex(current, seg.name);
    if (index < 0) {
      throw missing(seg.name, String(current.name ?? "?"));
    }
  }
  return { parent, index };
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

class DeviateError extends YangSemanticError {}

function single(node: YangStatement, deviate: DeviateRecord, prop: string, present: boolean, alwaysPresent = false): void {
  if (deviate.kind === "add" && present) {
    throw new DeviateError(
      `cannot 'deviate add' ${prop}: target ${String(node.keyword)} '${String(node.name)}' already has it (use 'deviate replace')`
    );
  }
  if (deviate.kind === "replace" && !present && !alwaysPresent) {
    throw new DeviateError(
      `cannot 'deviate replace' ${prop}: target ${String(node.keyword)} '${String(node.name)}' has no ${prop} (use 'deviate add')`
    );
  }
}

function requireKind(node: YangStatement, prop: string, keywords: readonly string[]): void {
  if (!keywords.includes(String(node.keyword))) {
    throw new DeviateError(`${prop} does not apply to target ${String(node.keyword)} '${String(node.name)}'`);
  }
}

const CONFIG_NODES = ["container", "leaf", "leaf-list", "list", "choice", "case", "anydata", "anyxml"];
const MUST_NODES = ["container", "leaf", "leaf-list", "list", "anydata", "anyxml", "input", "output", "notification"];

function applyDeviateDefaults(node: YangStatement, deviate: DeviateRecord): void {
  const values = deviate.defaults;
  if (node.keyword === "leaf-list") {
    const current = Array.isArray(node.defaults) ? [...(node.defaults as string[])] : [];
    if (deviate.kind === "add") {
      node.defaults = [...current, ...values];
    } else if (deviate.kind === "replace") {
      if (current.length === 0) {
        throw new DeviateError(`cannot 'deviate replace' default: target leaf-list '${String(node.name)}' has no default`);
      }
      node.defaults = [...values];
    } else {
      for (const value of values) {
        const idx = current.indexOf(value);
        if (idx < 0) {
          throw new DeviateError(
            `cannot 'deviate delete' default '${value}': target leaf-list '${String(node.name)}' has no such default`
          );
        }
        current.splice(idx, 1);
      }
      node.defaults = current;
    }
    return;
  }
  requireKind(node, "default", ["leaf", "choice"]);
  if (values.length !== 1) {
    throw new DeviateError(`target ${String(node.keyword)} '${String(node.name)}' takes one default, got ${values.length}`);
  }
  const present = node.default !== undefined && node.default !== null;
  if (deviate.kind === "delete") {
    if (!present || String(node.default) !== values[0]) {
      throw new DeviateError(
        `cannot 'deviate delete' default '${values[0]}': target ${String(node.keyword)} '${String(node.name)}' has default ${present ? `'${String(node.default)}'` : "None"}`
      );
    }
    delete node.default;
    return;
  }
  single(node, deviate, "default", present);
  node.default = values[0];
}

function applyDeviateMusts(node: YangStatement, deviate: DeviateRecord): void {
  requireKind(node, "must", MUST_NODES);
  const children = [...node.statements];
  if (deviate.kind === "add") {
    node.statements = [...children, ...deviate.must.map((m) => new YangStatement(m))];
    return;
  }
  for (const must of deviate.must) {
    const idx = children.findIndex((c) => c.keyword === "must" && c.argument === must.argument);
    if (idx < 0) {
      throw new DeviateError(
        `cannot 'deviate delete' must '${String(must.argument)}': target ${String(node.keyword)} '${String(node.name)}' has no such must`
      );
    }
    children.splice(idx, 1);
  }
  node.statements = children;
}

function applyDeviateUnique(node: YangStatement, deviate: DeviateRecord): void {
  requireKind(node, "unique", ["list"]);
  const current = Array.isArray(node.unique) ? (node.unique as string[][]).map((u) => [...u]) : [];
  if (deviate.kind === "add") {
    node.unique = [...current, ...deviate.unique.map((u) => [...u])];
    return;
  }
  for (const paths of deviate.unique) {
    const idx = current.findIndex((u) => u.length === paths.length && u.every((p, i) => p === paths[i]));
    if (idx < 0) {
      throw new DeviateError(
        `cannot 'deviate delete' unique '${paths.join(" ")}': target list '${String(node.name)}' has no such unique`
      );
    }
    current.splice(idx, 1);
  }
  node.unique = current;
}

/** Apply one ``deviate add|replace|delete`` to *node* (RFC 7950 §7.20.3.2). */
function applyDeviate(node: YangStatement, deviate: DeviateRecord): void {
  if (deviate.config !== undefined) {
    requireKind(node, "config", CONFIG_NODES);
    single(node, deviate, "config", typeof node.config === "boolean", true);
    node.config = deviate.config;
  }
  if (deviate.mandatory !== undefined) {
    requireKind(node, "mandatory", ["leaf", "choice", "anydata", "anyxml"]);
    single(node, deviate, "mandatory", node.mandatory === true, true);
    node.mandatory = deviate.mandatory;
  }
  if (deviate.min_elements !== undefined) {
    requireKind(node, "min-elements", ["list", "leaf-list"]);
    single(node, deviate, "min-elements", typeof node.min_elements === "number", true);
    node.min_elements = deviate.min_elements;
  }
  if (deviate.max_elements_set) {
    requireKind(node, "max-elements", ["list", "leaf-list"]);
    single(node, deviate, "max-elements", typeof node.max_elements === "number", true);
    if (deviate.max_elements === undefined) {
      delete node.max_elements;
    } else {
      node.max_elements = deviate.max_elements;
    }
  }
  if (deviate.type !== undefined) {
    requireKind(node, "type", ["leaf", "leaf-list"]);
    node.type = deviate.type;
  }
  if (deviate.units !== undefined) {
    requireKind(node, "units", ["leaf", "leaf-list"]);
    const units = typeof node.units === "string" ? node.units : "";
    if (deviate.kind === "delete") {
      if (units !== deviate.units) {
        throw new DeviateError(
          `cannot 'deviate delete' units '${deviate.units}': target ${String(node.keyword)} '${String(node.name)}' has units '${units}'`
        );
      }
      delete node.units;
    } else {
      single(node, deviate, "units", units !== "");
      node.units = deviate.units;
    }
  }
  if (deviate.defaults.length > 0) {
    applyDeviateDefaults(node, deviate);
  }
  if (deviate.must.length > 0) {
    applyDeviateMusts(node, deviate);
  }
  if (deviate.unique.length > 0) {
    applyDeviateUnique(node, deviate);
  }
}

function applyDeviation(ctxModule: ModuleData, dev: YangStatement, copies: Map<ModuleData, ModuleData>): void {
  const path = String(dev.deviation_path ?? dev.argument ?? "");
  const stored = dev.deviation_path_segments;
  const segments =
    Array.isArray(stored) && stored.length > 0 ? (stored as YangIdentifierRef[]) : parseAbsoluteSchemaPath(path);
  let located: { parent: ModuleData | YangStatement; node: YangStatement };
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
  let node = located.node;
  if (owner === ctxModule) {
    if (dev.not_supported === true) {
      removeSchemaChild(located.parent, node);
      return;
    }
  } else {
    const { parent, index } = copiedPathToTarget(privateTargetModule(ctxModule, owner, copies), segments);
    if (dev.not_supported === true) {
      parent.statements.splice(index, 1);
      return;
    }
    node = cowStatement(parent.statements[index]!);
    parent.statements[index] = node;
  }
  const deviates = dev.deviates ?? [];
  for (const deviate of deviates) {
    try {
      applyDeviate(node, deviate);
    } catch (err) {
      if (err instanceof DeviateError) {
        throw new YangSemanticError(`deviation '${path}': ${err.message}`);
      }
      throw err;
    }
  }
}

/**
 * Apply each ``deviation`` in order, then drop ``deviation`` statements.
 * Same absolute-path resolution as ``augment``. A missing target, or a ``deviate`` the target
 * cannot take (RFC 7950 §7.20.3.2), is a {@link YangSemanticError}.
 * A target in another module is changed on a copy owned by this build; the cached module is unchanged.
 */
export function applyDeviations(module: YangModule): YangModule {
  const data = module;
  const statements = asStatements(data.statements);
  const deviations = statements.filter((s) => s.keyword === "deviation");
  const copies = new Map<ModuleData, ModuleData>();
  for (const dev of deviations) {
    applyDeviation(data, dev, copies);
  }
  if (deviations.length > 0) {
    data.statements = statements.filter((s) => s.keyword !== "deviation");
  }
  return module;
}

function stampDefiningModule(stmt: YangStatement, moduleName: string): void {
  stmt.defining_module = moduleName;
  for (const child of asStatements(stmt.statements)) {
    stampDefiningModule(child, moduleName);
  }
}

function mergeIfFeaturesFromAugment(aug: YangStatement, child: YangStatement): void {
  const ufs = aug.if_features;
  if (!Array.isArray(ufs) || ufs.length === 0) {
    return;
  }
  const existing = Array.isArray(child.if_features) ? (child.if_features as string[]) : [];
  child.if_features = [...ufs, ...existing];
}

function mergeWhenFromAugment(aug: YangStatement, child: YangStatement): void {
  const uw = aug.when as Record<string, unknown> | undefined;
  if (!uw || typeof uw.expression !== "string" || uw.expression.trim() === "") {
    return;
  }
  const usesWhen: Record<string, unknown> = {
    ...(JSON.parse(JSON.stringify(uw)) as Record<string, unknown>),
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
  aug: YangStatement,
  target: YangStatement,
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
 * ``import_prefixes`` values are the cached {@link YangModule} objects.
 */
export function registerModuleClosure(modules: Map<string, YangModule>, mod: YangModule): void {
  const name = mod.name;
  if (!name) {
    return;
  }
  modules.set(name, mod);
  for (const imported of Object.values(mod.import_prefixes)) {
    const importedName = imported?.name ?? "";
    if (!importedName || modules.has(importedName)) {
      continue;
    }
    registerModuleClosure(modules, imported);
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
  const pending: Array<{ mod: YangModule; aug: YangStatement }> = [];
  const seen = new Set<ModuleData>();
  for (const mod of list) {
    if (seen.has(mod)) {
      continue;
    }
    seen.add(mod);
    for (const stmt of asStatements(mod.statements)) {
      if (stmt.keyword === "augment") {
        pending.push({ mod, aug: stmt });
      }
    }
  }
  for (const { mod, aug } of pending) {
    const path = String(aug.augment_path ?? aug.argument ?? "");
    const target = resolveAugmentTarget(mod, path, aug);
    mergeAugmentIntoTarget(aug, target, String(mod.name ?? ""));
  }
  const seenDev = new Set<ModuleData>();
  for (const mod of list) {
    if (seenDev.has(mod)) {
      continue;
    }
    seenDev.add(mod);
    applyDeviations(mod);
  }
  for (const mod of list) {
    const stmts = asStatements(mod.statements);
    mod.statements = stmts.filter((s) => s.keyword !== "augment");
  }
}

/**
 * For each top-level ``augment``, copy its (already ``uses``-expanded) children onto the
 * target node, merge ``if-feature`` / ``when`` like ``uses``, then remove the
 * ``augment`` statement from *module*.
 */
export function applyAugments(module: YangModule): YangModule {
  const statements = asStatements(module.statements);
  const augments = statements.filter((s) => s.keyword === "augment");
  if (augments.length === 0) {
    return module;
  }
  const sourceName = String(module.name ?? "");
  for (const aug of augments) {
    const path = String(aug.augment_path ?? aug.argument ?? "");
    const target = resolveAugmentTarget(module, path, aug);
    mergeAugmentIntoTarget(aug, target, sourceName);
  }
  module.statements = statements.filter((s) => s.keyword !== "augment");
  return module;
}
