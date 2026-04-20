import { YangSemanticError } from "../core/errors";
import type { SerializedStatement } from "../core/model";

type ModuleShape = Record<string, unknown>;

const STRUCTURE_INDEX_KEY = "ietf-yang-structure-ext:structure-index";

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function asStatements(value: unknown): SerializedStatement[] {
  return Array.isArray(value) ? (value as SerializedStatement[]) : [];
}

function deepCloneStatement(stmt: SerializedStatement): SerializedStatement {
  return JSON.parse(JSON.stringify(stmt)) as SerializedStatement;
}

function mergeRootIfFeatures(stmt: SerializedStatement, inherited: string[]): void {
  if (inherited.length === 0) {
    return;
  }
  const current = Array.isArray(stmt.if_features) ? (stmt.if_features as string[]) : [];
  stmt.if_features = [...inherited, ...current];
}

function mergeRootWhen(stmt: SerializedStatement, inheritedWhen?: Record<string, unknown>): void {
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

function parsePrefixedPath(path: string, kind: string): Array<{ prefix: string; name: string }> {
  const raw = String(path ?? "").trim();
  if (!raw.startsWith("/")) {
    throw new YangSemanticError(`${kind} requires an absolute path argument`);
  }
  const segments = raw
    .slice(1)
    .split("/")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
  if (segments.length === 0) {
    throw new YangSemanticError(`${kind} path cannot be empty`);
  }

  return segments.map((segment) => {
    const idx = segment.indexOf(":");
    if (idx <= 0 || idx === segment.length - 1) {
      throw new YangSemanticError(`${kind}: invalid path segment '${segment}', expected 'prefix:identifier'`);
    }
    return { prefix: segment.slice(0, idx), name: segment.slice(idx + 1) };
  });
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

function findNamedChild(owner: SerializedStatement, name: string): SerializedStatement | undefined {
  const children = asStatements(owner.statements);
  return children.find((child) => child.name === name);
}

function findTopLevelStructure(moduleData: ModuleShape, name: string): SerializedStatement | undefined {
  const runtime = isObject(moduleData.extension_runtime) ? moduleData.extension_runtime : undefined;
  const structureIndex = runtime && isObject(runtime[STRUCTURE_INDEX_KEY]) ? (runtime[STRUCTURE_INDEX_KEY] as Record<string, unknown>) : undefined;
  const indexed = structureIndex?.[name];
  if (isObject(indexed)) {
    return indexed as SerializedStatement;
  }

  const statements = asStatements(moduleData.statements);
  return statements.find((stmt) => {
    const extName = typeof stmt.resolved_extension_name === "string" ? stmt.resolved_extension_name : "";
    return extName === "structure" && String(stmt.argument ?? "").trim() === name;
  });
}

function resolveAugmentStructureTarget(ctxModule: ModuleShape, path: string): SerializedStatement {
  const segments = parsePrefixedPath(path, "augment-structure");
  const first = segments[0];
  const firstModule = resolvePrefixedModule(ctxModule, first.prefix, path, "augment-structure");
  let current = findTopLevelStructure(firstModule, first.name);
  if (!current) {
    throw new YangSemanticError(`augment-structure: no top-level structure '${first.name}' in path '${path}'`);
  }
  for (const segment of segments.slice(1)) {
    resolvePrefixedModule(ctxModule, segment.prefix, path, "augment-structure");
    const next = findNamedChild(current, segment.name);
    if (!next) {
      throw new YangSemanticError(`augment-structure: no child '${segment.name}' in path '${path}'`);
    }
    current = next;
  }
  return current;
}

function applyRFC8791Invocation(stmt: SerializedStatement, contextModule: ModuleShape): SerializedStatement | undefined {
  const moduleName = String(stmt.resolved_module_name ?? "");
  const extName = String(stmt.resolved_extension_name ?? "");
  if (moduleName !== "ietf-yang-structure-ext") {
    return stmt;
  }

  if (extName === "structure") {
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
    // Treat structure node as a container-like top-level data owner for validation walks.
    stmt.data_node_kind = "container";
    return stmt;
  }

  if (extName === "augment-structure") {
    const targetPath = String(stmt.argument ?? "");
    const target = resolveAugmentStructureTarget(contextModule, targetPath);
    const copies = asStatements(stmt.statements).map((child) => deepCloneStatement(child));
    const inheritedIfFeatures = Array.isArray(stmt.if_features) ? (stmt.if_features as string[]) : [];
    const inheritedWhen = isObject(stmt.when) ? stmt.when : undefined;
    for (const copy of copies) {
      mergeRootIfFeatures(copy, inheritedIfFeatures);
      mergeRootWhen(copy, inheritedWhen);
      const targetChildren = asStatements(target.statements);
      targetChildren.push(copy);
      target.statements = targetChildren;
    }
    return undefined;
  }

  return stmt;
}

function walkAndApply(owner: ModuleShape | SerializedStatement, contextModule: ModuleShape): void {
  const statements = asStatements(owner.statements);
  const out: SerializedStatement[] = [];
  for (const statement of statements) {
    let current: SerializedStatement | undefined = statement;
    if (typeof statement.resolved_module_name === "string" && typeof statement.resolved_extension_name === "string") {
      current = applyRFC8791Invocation(statement, contextModule);
    }
    if (!current) {
      continue;
    }
    walkAndApply(current, contextModule);
    out.push(current);
  }
  owner.statements = out;
}

export function applyBuiltinExtensionInvocations(moduleData: ModuleShape): void {
  walkAndApply(moduleData, moduleData);
}
