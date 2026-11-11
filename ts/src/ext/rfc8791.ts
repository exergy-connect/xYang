import { YangSemanticError } from "../core/errors";
import { parseAbsoluteSchemaPath, type YangIdentifierRef } from "../core/identifier-ref";
import { YangStatement, type YangModule } from "../core/model";

type ModuleShape = YangModule;

const STRUCTURE_INDEX_KEY = "ietf-yang-structure-ext:structure-index";
const FOREIGN_AUGMENTS = "ietf-yang-structure-ext:foreign-augment-structure";
const FOREIGN_SLOTS = "ietf-yang-structure-ext:foreign-augment-structure-slots";

/** JSON export applies on a copy and must not merge a foreign augment into the import. */
let exportView = false;

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function asStatements(value: unknown): YangStatement[] {
  return Array.isArray(value) ? (value as YangStatement[]) : [];
}

function deepCloneStatement(stmt: YangStatement): YangStatement {
  return new YangStatement(JSON.parse(JSON.stringify(stmt)) as YangStatement);
}

function mergeRootIfFeatures(stmt: YangStatement, inherited: string[]): void {
  if (inherited.length === 0) {
    return;
  }
  const current = Array.isArray(stmt.if_features) ? (stmt.if_features as string[]) : [];
  stmt.if_features = [...inherited, ...current];
}

function mergeRootWhen(stmt: YangStatement, inheritedWhen?: Record<string, unknown>): void {
  if (!inheritedWhen || typeof inheritedWhen.expression !== "string") {
    return;
  }
  const inheritedExpr = inheritedWhen.expression;
  const existing = isObject(stmt.when) ? stmt.when : undefined;
  const existingExpr = typeof existing?.expression === "string" ? existing.expression : undefined;
  if (existingExpr) {
    const existingDescription = typeof existing?.description === "string" ? existing.description : "";
    stmt.when = {
      expression: `(${inheritedExpr}) and (${existingExpr})`,
      description: existingDescription,
      evaluate_with_parent_context: true
    };
    return;
  }
  stmt.when = {
    expression: inheritedExpr,
    description: typeof inheritedWhen.description === "string" ? inheritedWhen.description : "",
    evaluate_with_parent_context: true
  };
}

function parsePrefixedPath(path: string, kind: string): YangIdentifierRef[] {
  try {
    return parseAbsoluteSchemaPath(path);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new YangSemanticError(`${kind}: ${msg}`);
  }
}

function resolvePrefixedModule(ctxModule: ModuleShape, prefix: string, fullPath: string, kind: string): ModuleShape {
  const ownPrefix = String(ctxModule.prefix ?? "").replace(/^['"]|['"]$/g, "");
  if (prefix === ownPrefix) {
    return ctxModule;
  }
  const imports = isObject(ctxModule.import_prefixes) ? ctxModule.import_prefixes : undefined;
  const resolved = imports && isObject(imports[prefix]) ? (imports[prefix] as ModuleShape) : undefined;
  if (!resolved) {
    throw new YangSemanticError(`${kind}: unknown prefix '${prefix}' in path '${fullPath}'`);
  }
  return resolved;
}

function findNamedChild(owner: YangStatement, name: string): YangStatement | undefined {
  const children = asStatements(owner.statements);
  return children.find((child) => child.name === name);
}

function findTopLevelStructure(moduleData: ModuleShape, name: string): YangStatement | undefined {
  const runtime = isObject(moduleData.extension_runtime) ? moduleData.extension_runtime : undefined;
  const structureIndex = runtime && isObject(runtime[STRUCTURE_INDEX_KEY]) ? (runtime[STRUCTURE_INDEX_KEY] as Record<string, unknown>) : undefined;
  const indexed = structureIndex?.[name];
  if (isObject(indexed)) {
    return indexed as unknown as YangStatement;
  }

  const statements = asStatements(moduleData.statements);
  return statements.find((stmt) => {
    const extName = typeof stmt.resolved_extension_name === "string" ? stmt.resolved_extension_name : "";
    return extName === "structure" && String(stmt.argument ?? "").trim() === name;
  });
}

function resolveAugmentStructureTarget(ctxModule: ModuleShape, path: string): YangStatement {
  const segments = parsePrefixedPath(path, "augment-structure");
  const first = segments[0]!;
  const pref0 = first.prefix!;
  const firstModule = resolvePrefixedModule(ctxModule, pref0, path, "augment-structure");
  let current = findTopLevelStructure(firstModule, first.name);
  if (!current) {
    throw new YangSemanticError(`augment-structure: no top-level structure '${first.name}' in path '${path}'`);
  }
  for (const segment of segments.slice(1)) {
    resolvePrefixedModule(ctxModule, segment.prefix!, path, "augment-structure");
    const next = findNamedChild(current, segment.name);
    if (!next) {
      throw new YangSemanticError(`augment-structure: no child '${segment.name}' in path '${path}'`);
    }
    current = next;
  }
  return current;
}

function targetModule(ctxModule: ModuleShape, path: string): ModuleShape {
  const segments = parsePrefixedPath(path, "augment-structure");
  return resolvePrefixedModule(ctxModule, segments[0]!.prefix!, path, "augment-structure");
}

function applyRFC8791Invocation(stmt: YangStatement, contextModule: ModuleShape): YangStatement | undefined {
  const moduleName = String(stmt.resolved_module_name ?? "");
  const extName = String(stmt.resolved_extension_name ?? "");
  if (moduleName !== "ietf-yang-structure-ext") {
    return stmt;
  }
  const applied = (stmt as { _rfc8791_applied?: boolean })._rfc8791_applied === true;

  if (extName === "structure") {
    if (applied) {
      return stmt;
    }
    const runtime = (isObject(contextModule.extension_runtime)
      ? contextModule.extension_runtime
      : (contextModule.extension_runtime = {})) as Record<string, unknown>;
    const idx = (isObject(runtime[STRUCTURE_INDEX_KEY])
      ? runtime[STRUCTURE_INDEX_KEY]
      : (runtime[STRUCTURE_INDEX_KEY] = {})) as Record<string, unknown>;
    const structureName = String(stmt.argument ?? "").trim();
    if (structureName.length > 0) {
      idx[structureName] = stmt;
      stmt.name = structureName;
    }
    // Only a top-level structure is a data node. A nested one is addressed through the index,
    // the same way Python resolves a single-member structure document.
    if ((stmt as { _rfc8791_root?: boolean })._rfc8791_root === true) {
      stmt.data_node_kind = "container";
    }
    (stmt as { _rfc8791_applied?: boolean })._rfc8791_applied = true;
    return stmt;
  }

  if (extName === "augment-structure") {
    if (applied) {
      return undefined;
    }
    const targetPath = String(stmt.argument ?? "");
    const foreign = targetModule(contextModule, targetPath) !== contextModule;
    // Resolve even when the invocation is exported verbatim, so a bad path fails here.
    const target = resolveAugmentStructureTarget(contextModule, targetPath);
    if (foreign && exportView) {
      return stmt;
    }
    const copies = asStatements(stmt.statements).map((child) => deepCloneStatement(child));
    const inheritedIfFeatures = Array.isArray(stmt.if_features) ? (stmt.if_features as string[]) : [];
    // Copy the when so the invocation itself stays verbatim for export.
    const inheritedWhen = isObject(stmt.when) ? { ...stmt.when } : undefined;
    for (const copy of copies) {
      mergeRootIfFeatures(copy, inheritedIfFeatures);
      mergeRootWhen(copy, inheritedWhen);
      (copy as { augment_structure?: string }).augment_structure = targetPath;
      (copy as { augment_structure_module?: string }).augment_structure_module = contextModule.name;
      const targetChildren = asStatements(target.statements);
      targetChildren.push(copy);
      target.statements = targetChildren;
    }
    (stmt as { _rfc8791_applied?: boolean })._rfc8791_applied = true;
    if (foreign && (stmt as { _rfc8791_root?: boolean })._rfc8791_root === true) {
      (stmt as { _rfc8791_foreign?: boolean })._rfc8791_foreign = true;
    }
    return undefined;
  }

  return stmt;
}

function walkAndApply(owner: ModuleShape | YangStatement, contextModule: ModuleShape, atRoot: boolean): void {
  const statements = asStatements(owner.statements);
  const out: YangStatement[] = [];
  let keptExtensions = 0;
  for (const statement of statements) {
    let current: YangStatement | undefined = statement;
    const invocation = typeof statement.resolved_module_name === "string" && typeof statement.resolved_extension_name === "string";
    if (invocation) {
      if (atRoot) {
        (statement as { _rfc8791_root?: boolean })._rfc8791_root = true;
      }
      current = applyRFC8791Invocation(statement, contextModule);
      if (
        !current
        && atRoot
        && (statement as { _rfc8791_foreign?: boolean })._rfc8791_foreign === true
        && !exportView
      ) {
        const runtime = (isObject(contextModule.extension_runtime)
          ? contextModule.extension_runtime
          : (contextModule.extension_runtime = {})) as Record<string, unknown>;
        const saved = Array.isArray(runtime[FOREIGN_AUGMENTS]) ? (runtime[FOREIGN_AUGMENTS] as YangStatement[]) : [];
        if (!saved.includes(statement)) {
          saved.push(statement);
          const slots = Array.isArray(runtime[FOREIGN_SLOTS]) ? (runtime[FOREIGN_SLOTS] as number[]) : [];
          slots.push(keptExtensions);
          runtime[FOREIGN_AUGMENTS] = saved;
          runtime[FOREIGN_SLOTS] = slots;
        }
      }
    }
    if (!current) {
      continue;
    }
    walkAndApply(current, contextModule, false);
    if (atRoot && invocation) {
      keptExtensions += 1;
    }
    out.push(current);
  }
  owner.statements = out;
}

export function applyBuiltinExtensionInvocations(moduleData: ModuleShape, options?: { exportView?: boolean }): void {
  const previous = exportView;
  exportView = options?.exportView === true;
  try {
    walkAndApply(moduleData, moduleData, true);
  } finally {
    exportView = previous;
  }
}
