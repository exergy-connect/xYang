import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { YangSemanticError, YangSyntaxError } from "../core/errors";
import { coerceIdentifierRef, type YangIdentifierRef } from "../core/identifier-ref";
import { ModuleSource, SerializedStatement, YangModule } from "../core/model";
import { ParserContext, TokenStream } from "./parser-context";
import { StatementParsers } from "./statement-parsers";
import { YangTokenizer } from "./tokenizer";
import { warnDeprecatedOnce } from "../core/deprecation";
import { applyBuiltinExtensionInvocations } from "../ext";
import { applyAugments, applyDeviations } from "../transform/augment-expand";
import { expandUses } from "../transform/uses-expand";
import { validateSemantics } from "../validator/semantic-validation";

type ParserOptions = {
  expandUses?: boolean;
  includePath?: string[];
  /** @deprecated use expandUses */
  expand_uses?: boolean;
  /** @deprecated use includePath */
  include_path?: string[];
};

function serializeIdentities(
  raw: Record<string, { bases?: unknown }> | undefined
): Record<string, { bases: YangIdentifierRef[] }> {
  const out: Record<string, { bases: YangIdentifierRef[] }> = {};
  if (!raw) {
    return out;
  }
  for (const [name, stmt] of Object.entries(raw)) {
    const bases = Array.isArray(stmt.bases)
      ? stmt.bases
          .map((b) => coerceIdentifierRef(b))
          .filter((b): b is YangIdentifierRef => Boolean(b))
      : [];
    out[name] = { bases };
  }
  return out;
}

function buildModuleData(root: SerializedStatement, moduleState: Record<string, unknown>): Record<string, unknown> {
  if (root.keyword !== "module") {
    throw new YangSemanticError("Only 'module' roots are currently supported by TS parser");
  }

  const statements = root.statements ?? [];
  const typedefs: Record<string, unknown> = {};

  for (const stmt of statements) {
    if (stmt.keyword === "typedef" && stmt.argument) {
      const typeStmt = stmt.statements?.find((child) => child.keyword === "type");
      typedefs[stmt.argument] = {
        name: stmt.argument,
        description: typeof stmt.description === "string" ? stmt.description : "",
        reference: typeof stmt.reference === "string" ? stmt.reference : "",
        default: stmt.default,
        type: stmt.type ?? typeStmt?.type,
        statements: stmt.statements ?? []
      };
    }
  }

  const features = moduleState.features;
  const featureIfFeatures = moduleState.feature_if_features;

  const moduleDescriptionStmt = statements.find((stmt) => stmt.keyword === "description");
  const moduleDescription =
    typeof moduleDescriptionStmt?.argument === "string" ? moduleDescriptionStmt.argument : "";

  return {
    __class__: "YangModule",
    name: root.argument,
    yang_version: statements.find((stmt) => stmt.keyword === "yang-version")?.argument ?? "1.1",
    namespace: statements.find((stmt) => stmt.keyword === "namespace")?.argument ?? "",
    prefix: statements.find((stmt) => stmt.keyword === "prefix")?.argument ?? "",
    organization: String(moduleState.organization ?? ""),
    contact: String(moduleState.contact ?? ""),
    description: moduleDescription,
    typedefs,
    identities: serializeIdentities(moduleState.identities as Record<string, { bases?: string[] }> | undefined),
    import_prefixes: (moduleState.import_prefixes as Record<string, unknown>) ?? {},
    extensions: (moduleState.extensions as Record<string, unknown>) ?? {},
    extension_runtime: (moduleState.extension_runtime as Record<string, unknown>) ?? {},
    features: features instanceof Set ? new Set(features as Set<string>) : new Set<string>(),
    feature_if_features:
      featureIfFeatures && typeof featureIfFeatures === "object"
        ? { ...(featureIfFeatures as Record<string, string[]>) }
        : {},
    statements
  };
}

export class YangParser {
  readonly expandUses: boolean;
  readonly includePath: string[];
  private readonly moduleCache = new Map<string, YangModule>();

  private readonly tokenizer = new YangTokenizer();

  private readonly includeStack: string[] = [];

  private readonly parsers = new StatementParsers({
    importResolver: (moduleName, _localPrefix, revisionDate, context, tokens) =>
      this.resolveImport(moduleName, revisionDate, context, tokens),
    includeResolver: (submoduleName, revisionDate, context, tokens) =>
      this.resolveInclude(submoduleName, revisionDate, context, tokens)
  });

  constructor(options: ParserOptions = {}) {
    if ("expand_uses" in options) {
      warnDeprecatedOnce("expand_uses", "expandUses");
    }
    if ("include_path" in options) {
      warnDeprecatedOnce("include_path", "includePath");
    }
    this.expandUses = options.expandUses ?? options.expand_uses ?? true;
    this.includePath = (options.includePath ?? options.include_path ?? []).map((p) => resolve(p));
  }

  /** Resolve `import` / `include` like Python `YangParser._resolve_module_file`. */
  private resolveImportedModulePath(
    moduleBasename: string,
    revisionDate: string | undefined,
    sourceDir: string | undefined,
    kind: "module" | "submodule" = "module"
  ): string {
    const trimmedRev = revisionDate?.trim();
    const candidates: string[] = [];
    if (trimmedRev) {
      candidates.push(`${moduleBasename}@${trimmedRev}.yang`);
    }
    candidates.push(`${moduleBasename}.yang`);
    const dirs = sourceDir ? [sourceDir, ...this.includePath] : [...this.includePath];
    let found: string | undefined;
    for (const dir of dirs) {
      for (const c of candidates) {
        const p = resolve(dir, c);
        if (existsSync(p)) {
          found = p;
          break;
        }
      }
      if (found) {
        break;
      }
    }
    if (!found) {
      for (const dir of dirs) {
        let matches: string[] = [];
        try {
          matches = readdirSync(dir).filter((f) => f.startsWith(`${moduleBasename}@`) && f.endsWith(".yang"));
        } catch {
          matches = [];
        }
        if (matches.length > 0) {
          matches.sort();
          found = resolve(dir, matches[matches.length - 1]!);
          break;
        }
      }
    }
    if (!found) {
      const tried = `[${candidates.map((c) => `'${c}'`).join(", ")}]`;
      throw new YangSemanticError(
        `Could not find ${kind} '${moduleBasename}' (tried filenames ${tried}) under [${dirs.join(", ")}]`
      );
    }
    const expected = trimmedRev ? `${moduleBasename}@${trimmedRev}.yang` : undefined;
    const foundName = found.slice(Math.max(found.lastIndexOf("/"), found.lastIndexOf("\\")) + 1);
    if (expected && foundName !== expected) {
      const statement = kind === "module" ? "import" : "include";
      console.warn(
        `${statement} '${moduleBasename}' revision-date ${trimmedRev} not found; using ${foundName}`
      );
    }
    return found;
  }

  private sourceDirFromContext(context: ParserContext): string | undefined {
    const sourcePath = (context.module as Record<string, unknown>).__source_path as string | undefined;
    return sourcePath ? dirname(sourcePath) : undefined;
  }

  private resolveImport(
    moduleName: string,
    revisionDate: string | undefined,
    context: ParserContext,
    _tokens: TokenStream
  ): Record<string, unknown> {
    const sourceDir = this.sourceDirFromContext(context);
    if (!sourceDir && this.includePath.length === 0) {
      throw new YangSemanticError(
        "import requires a filesystem location: use parseYangFile(), or parseYangString(... from a file-backed source)"
      );
    }
    const filePath = this.resolveImportedModulePath(moduleName, revisionDate, sourceDir, "module");
    const imported = this.parseFile(filePath);
    return imported.data;
  }

  /**
   * Load an included submodule into the parent's parser context (Python
   * ``merge_included_submodule``). Definitions land on the parent; ``belongs-to``,
   * duplicate names, and circular includes use Python's messages.
   */
  private resolveInclude(
    submoduleName: string,
    revisionDate: string | undefined,
    context: ParserContext,
    _tokens: TokenStream
  ): void {
    const module = context.module as Record<string, unknown>;
    const sourceDir = this.sourceDirFromContext(context);
    if (!sourceDir && this.includePath.length === 0) {
      throw new YangSemanticError(
        "include requires a filesystem location for the submodule: " +
          "use parseYangFile(), or parseYangString(... from a file-backed source)"
      );
    }
    const path = this.resolveImportedModulePath(submoduleName, revisionDate, sourceDir, "submodule");
    if (this.includeStack.includes(path)) {
      throw new YangSyntaxError(`Circular submodule include: ${path}`, { filename: path });
    }
    this.includeStack.push(path);
    const saved = snapshotModuleHeader(module);
    const releaseGuards = guardIncludeDefinitions(module, submoduleName);
    const previousInclude = this.parsers.includingSubmoduleName;
    this.parsers.includingSubmoduleName = submoduleName;
    const savedSource = module.__source_path;
    module.__source_path = path;
    let subName = "";
    let belongs = "";
    try {
      const content = readFileSync(path, "utf-8");
      const stream = this.tokenizer.tokenize(content, path);
      if (!stream.has_more() || stream.peek() !== "submodule") {
        const got = stream.has_more() ? stream.peek() : "";
        throw new YangSemanticError(
          `submodule file defines name '${got}', include expects '${submoduleName}'`
        );
      }
      this.parsers.parseSubmodule(stream, context);
      subName = String(module.name ?? "");
      belongs = String(module.belongs_to_module ?? "");
    } finally {
      module.__source_path = savedSource;
      this.parsers.includingSubmoduleName = previousInclude;
      releaseGuards();
      restoreModuleHeader(module, saved);
      this.includeStack.pop();
    }
    if (subName !== submoduleName) {
      throw new YangSemanticError(
        `submodule file defines name '${subName}', include expects '${submoduleName}'`
      );
    }
    const parentName = String(saved.name ?? "");
    if (belongs && belongs !== parentName) {
      throw new YangSemanticError(
        `submodule belongs-to '${belongs}' does not match module '${parentName}'`
      );
    }
  }

  private parseTokenStream(stream: TokenStream, source: ModuleSource, sourceDir?: string): YangModule {
    const moduleState: Record<string, unknown> = {
      name: "",
      yang_version: "1.1",
      namespace: "",
      prefix: "",
      organization: "",
      contact: "",
      revisions: [],
      belongs_to_module: "",
      typedefs: {},
      identities: {},
      groupings: {},
      features: new Set<string>(),
      feature_if_features: {},
      import_prefixes: {},
      extensions: {},
      extension_runtime: {},
      __source_path:
        source.kind === "file"
          ? source.value
          : sourceDir
            ? resolve(sourceDir, "memory.yang")
            : undefined,
      statements: []
    };
    const context = new ParserContext({ module: moduleState, current_parent: {} });
    const root = this.parsers.parseModule(stream, context);
    const data = buildModuleData(root, moduleState);
    mergeNestedTypedefs(data, moduleState, (stmt) => this.parsers.serializeAstStatement(stmt));
    const rawGroupings = (moduleState.groupings as Record<string, unknown>) ?? {};
    const serializedGroupings: Record<string, SerializedStatement> = {};
    for (const [key, val] of Object.entries(rawGroupings)) {
      if (!val || typeof val !== "object") {
        continue;
      }
      const g = val as { name?: string; statements?: unknown[] };
      const gname = g.name ?? key;
      serializedGroupings[key] = {
        __class__: "YangStatement",
        keyword: "grouping",
        name: gname,
        argument: gname,
        statements: (g.statements ?? []).map((ch) => this.parsers.serializeAstStatement(ch))
      };
    }
    if (Object.keys(serializedGroupings).length > 0) {
      data.groupings = serializedGroupings;
    }
    // Python order, gated on expandUses: uses, then augment, then extensions.
    let mod = new YangModule(data, source);
    if (this.expandUses) {
      mod = expandUses(mod);
      mod = applyAugments(mod);
      mod = applyDeviations(mod);
      applyBuiltinExtensionInvocations(mod.data);
      validateSemantics(mod);
    }
    return mod;
  }

  /**
   * @param sourceDir Directory searched before `includePath` for `import` / `include`.
   *   `parseYangString` passes `dirname(sourcePath)`.
   */
  parseString(content: string, sourceName = "<memory>", sourceDir?: string): YangModule {
    const stream = this.tokenizer.tokenize(content, sourceName);
    const source: ModuleSource = { kind: "string", value: content, name: sourceName };
    return this.parseTokenStream(stream, source, sourceDir);
  }

  parseFile(path: string): YangModule {
    const absolute = resolve(path);
    const cached = this.moduleCache.get(absolute);
    if (cached) {
      return cached;
    }
    const content = readFileSync(absolute, "utf-8");
    const stream = this.tokenizer.tokenize(content, absolute);
    const source: ModuleSource = { kind: "file", value: absolute, name: absolute };
    const tracked = this.includeStack.length === 0;
    if (tracked) {
      this.includeStack.push(absolute);
    }
    try {
      const module = this.parseTokenStream(stream, source);
      this.moduleCache.set(absolute, module);
      return module;
    } finally {
      if (tracked) {
        this.includeStack.pop();
      }
    }
  }
}

type HeaderSnap = {
  name: unknown;
  yang_version: unknown;
  namespace: unknown;
  prefix: unknown;
  organization: unknown;
  contact: unknown;
  belongs_to_module: unknown;
  revisionLen: number;
};

function snapshotModuleHeader(module: Record<string, unknown>): HeaderSnap {
  const revisions = Array.isArray(module.revisions) ? module.revisions : undefined;
  return {
    name: module.name,
    yang_version: module.yang_version,
    namespace: module.namespace,
    prefix: module.prefix,
    organization: module.organization,
    contact: module.contact,
    belongs_to_module: module.belongs_to_module,
    revisionLen: revisions?.length ?? 0
  };
}

function restoreModuleHeader(module: Record<string, unknown>, saved: HeaderSnap): void {
  module.name = saved.name;
  module.yang_version = saved.yang_version;
  module.namespace = saved.namespace;
  module.prefix = saved.prefix;
  module.organization = saved.organization;
  module.contact = saved.contact;
  module.belongs_to_module = saved.belongs_to_module;
  if (Array.isArray(module.revisions)) {
    module.revisions.length = saved.revisionLen;
  }
}

/** Keep typedefs parsed under container/list/grouping; buildModuleData only sees top-level ones. */
function mergeNestedTypedefs(
  data: Record<string, unknown>,
  moduleState: Record<string, unknown>,
  serialize: (stmt: unknown) => SerializedStatement
): void {
  const typedefs =
    data.typedefs && typeof data.typedefs === "object"
      ? (data.typedefs as Record<string, unknown>)
      : {};
  data.typedefs = typedefs;
  const parsed = moduleState.typedefs;
  if (!parsed || typeof parsed !== "object") {
    return;
  }
  for (const [name, td] of Object.entries(parsed as Record<string, unknown>)) {
    if (typedefs[name]) {
      continue;
    }
    const serialized = serialize(td);
    typedefs[name] = {
      name,
      description: typeof serialized.description === "string" ? serialized.description : "",
      reference: typeof serialized.reference === "string" ? serialized.reference : "",
      default: serialized.default,
      type: serialized.type,
      statements: serialized.statements ?? []
    };
  }
}

function duplicateFromInclude(kind: string, name: string, subName: string): YangSemanticError {
  return new YangSemanticError(`Duplicate ${kind} '${name}' from include of '${subName}'`);
}

/** Reject names the parent already defined, with Python's include messages. */
function guardIncludeDefinitions(module: Record<string, unknown>, subName: string): () => void {
  const typedefs = (module.typedefs ?? {}) as Record<string, unknown>;
  const identities = (module.identities ?? {}) as Record<string, unknown>;
  const groupings = (module.groupings ?? {}) as Record<string, unknown>;
  const featureIfFeatures = (module.feature_if_features ?? {}) as Record<string, string[]>;
  module.typedefs = guardRecord(typedefs, (name) => duplicateFromInclude("typedef", name, subName));
  module.identities = guardRecord(identities, (name) => duplicateFromInclude("identity", name, subName));
  module.groupings = guardRecord(groupings, (name) => duplicateFromInclude("grouping", name, subName));
  module.feature_if_features = guardRecord(
    featureIfFeatures,
    (name) => duplicateFromInclude("feature if-feature for", name, subName)
  );

  const features = module.features instanceof Set ? (module.features as Set<string>) : new Set<string>();
  module.features = features;
  const originalAdd = features.add;
  features.add = ((value: string) => {
    if (features.has(value)) {
      throw duplicateFromInclude("feature", value, subName);
    }
    return originalAdd.call(features, value);
  }) as Set<string>["add"];

  return () => {
    module.typedefs = typedefs;
    module.identities = identities;
    module.groupings = groupings;
    module.feature_if_features = featureIfFeatures;
    features.add = originalAdd;
  };
}

function guardRecord<T extends Record<string, unknown>>(
  record: T,
  duplicate: (name: string) => YangSemanticError
): T {
  return new Proxy(record, {
    set(target, prop, value) {
      if (typeof prop === "string" && Object.hasOwn(target, prop)) {
        throw duplicate(prop);
      }
      target[prop as keyof T] = value as T[keyof T];
      return true;
    }
  });
}
