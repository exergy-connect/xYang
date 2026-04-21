import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { YangSemanticError } from "../core/errors";
import { ModuleSource, SerializedStatement, YangModule } from "../core/model";
import { ParserContext, TokenStream } from "./parser-context";
import { StatementParsers } from "./statement-parsers";
import { YangTokenizer } from "./tokenizer";
import { applyBuiltinExtensionInvocations } from "../ext";
import { expandUses } from "../transform/uses-expand";

type ParserOptions = {
  expand_uses?: boolean;
};

function serializeIdentities(
  raw: Record<string, { bases?: string[] }> | undefined
): Record<string, { bases: string[] }> {
  const out: Record<string, { bases: string[] }> = {};
  if (!raw) {
    return out;
  }
  for (const [name, stmt] of Object.entries(raw)) {
    out[name] = { bases: Array.isArray(stmt.bases) ? [...stmt.bases] : [] };
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
  private readonly moduleCache = new Map<string, YangModule>();

  private readonly tokenizer = new YangTokenizer();

  private readonly parsers = new StatementParsers({
    importResolver: (moduleName, _localPrefix, revisionDate, context, tokens) =>
      this.resolveImport(moduleName, revisionDate, context, tokens)
  });

  constructor(options: ParserOptions = {}) {
    this.expandUses = options.expand_uses ?? true;
  }

  /** Resolve `import` like Python `YangParser._resolve_submodule_path` (revision file, then basename, then last `name@*.yang`). */
  private resolveImportedModulePath(moduleBasename: string, revisionDate: string | undefined, sourceDir: string): string {
    const trimmedRev = revisionDate?.trim();
    const candidates: string[] = [];
    if (trimmedRev) {
      candidates.push(`${moduleBasename}@${trimmedRev}.yang`);
    }
    candidates.push(`${moduleBasename}.yang`);
    for (const c of candidates) {
      const p = resolve(sourceDir, c);
      if (existsSync(p)) {
        return p;
      }
    }
    let matches: string[] = [];
    try {
      matches = readdirSync(sourceDir).filter((f) => f.startsWith(`${moduleBasename}@`) && f.endsWith(".yang"));
    } catch {
      matches = [];
    }
    if (matches.length > 0) {
      matches.sort();
      return resolve(sourceDir, matches[matches.length - 1]!);
    }
    throw new YangSemanticError(
      `Could not find imported module '${moduleBasename}' (tried ${candidates.join(", ")}) under ${sourceDir}`
    );
  }

  private resolveImport(
    moduleName: string,
    revisionDate: string | undefined,
    context: ParserContext,
    _tokens: TokenStream
  ): Record<string, unknown> {
    const sourcePath = (context.module as Record<string, unknown>).__source_path as string | undefined;
    if (!sourcePath) {
      throw new YangSemanticError(
        "import requires a filesystem location: use parseYangFile(), or parseYangString(... from a file-backed source)"
      );
    }
    const filePath = this.resolveImportedModulePath(moduleName, revisionDate, dirname(sourcePath));
    const imported = this.parseFile(filePath);
    return imported.data;
  }

  private parseTokenStream(stream: TokenStream, source: ModuleSource): YangModule {
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
      __source_path: source.kind === "file" ? source.value : undefined,
      statements: []
    };
    const context = new ParserContext({ module: moduleState, current_parent: {} });
    const root = this.parsers.parseModule(stream, context);
    const data = buildModuleData(root, moduleState);
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
    applyBuiltinExtensionInvocations(data);
    let mod = new YangModule(data, source);
    if (this.expandUses) {
      mod = expandUses(mod);
    }
    return mod;
  }

  parseString(content: string, sourceName = "<memory>"): YangModule {
    const stream = this.tokenizer.tokenize(content, sourceName);
    const source: ModuleSource = { kind: "string", value: content, name: sourceName };
    return this.parseTokenStream(stream, source);
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
    const module = this.parseTokenStream(stream, source);
    this.moduleCache.set(absolute, module);
    return module;
  }
}
