import { typeStatementKind } from "../types/registry";
import { YangSemanticError } from "./errors";
import type { YangIdentifierRef } from "./identifier-ref";
import { bindXPathPrefixes, parseXPath, xpathPrefixes } from "../xpath/parser";
import type { XPathAstNode } from "../xpath/ast";
import { warnDeprecatedOnce } from "./deprecation";
import { translateXsdRegex } from "../xsd-regex";

/**
 * Module object an extension invocation resolves against.
 * This is the slice `ast.ts` uses; the runtime model lives in `./model`.
 */
export interface YangModule {
  name?: string;
}

export type ASTNode = XPathAstNode;
export type PathNode = XPathAstNode;

export class YangStatementList {
  statements: YangStatement[];

  constructor(statements: YangStatement[] = []) {
    this.statements = statements;
  }

  /** @deprecated use findStatement */
  find_statement(name: string): YangStatement | undefined {
    warnDeprecatedOnce("find_statement", "findStatement");
    return this.findStatement(name);
  }

  findStatement(name: string): YangStatement | undefined {
    return this.statements.find((stmt) => stmt.name === name);
  }

  /** @deprecated use getAllLeaves */
  get_all_leaves(): YangLeafStmt[] {
    warnDeprecatedOnce("get_all_leaves", "getAllLeaves");
    return this.getAllLeaves();
  }

  getAllLeaves(): YangLeafStmt[] {
    const leaves: YangLeafStmt[] = [];
    for (const stmt of this.statements) {
      leaves.push(...this.collectLeaves(stmt));
    }
    return leaves;
  }

  private collectLeaves(stmt: YangStatement): YangLeafStmt[] {
    if (stmt instanceof YangLeafStmt) {
      return [stmt];
    }
    if (stmt instanceof YangContainerStmt || stmt instanceof YangListStmt) {
      const leaves: YangLeafStmt[] = [];
      for (const child of stmt.statements) {
        leaves.push(...this.collectLeaves(child));
      }
      return leaves;
    }
    return [];
  }
}

export class YangStatement extends YangStatementList {
  keyword: string;
  name: string;
  description: string;
  reference: string;
  units: string;

  constructor(init: Partial<YangStatement> = {}) {
    super(init.statements ?? []);
    this.keyword = init.keyword ?? "";
    this.name = init.name ?? "";
    this.description = init.description ?? "";
    this.reference = init.reference ?? "";
    this.units = init.units ?? "";
  }

  get_schema_node(): string | undefined {
    return undefined;
  }

  getSchemaNode(): string | undefined {
    return this.get_schema_node();
  }

  child_names(_data: Record<string, unknown>): Set<string> {
    return this.name ? new Set([this.name]) : new Set();
  }

  childNames(data: Record<string, unknown>): Set<string> {
    return this.child_names(data);
  }
}

export class YangStatementWithMust extends YangStatement {
  must_statements: YangMustStmt[];

  constructor(init: Partial<YangStatementWithMust> = {}) {
    super(init);
    this.must_statements = init.must_statements ?? [];
  }
}

export class YangStatementWithWhen extends YangStatement {
  when?: YangWhenStmt;
  if_features: string[];
  /** RFC 7950 §7.21.1; undefined means inherit from parent. */
  config?: boolean;

  constructor(init: Partial<YangStatementWithWhen> = {}) {
    super(init);
    this.when = init.when;
    this.if_features = init.if_features ?? [];
    this.config = init.config;
  }

  override get_schema_node(): string | undefined {
    return this.name || undefined;
  }
}

export class YangTypedefStmt extends YangStatement {
  scope?: string;
  type?: YangTypeStmt;
  default?: string;

  constructor(init: Partial<YangTypedefStmt> = {}) {
    super(init);
    this.keyword = "typedef";
    this.scope = init.scope;
    this.type = init.type;
    this.default = init.default;
  }

  override get_schema_node(): string | undefined {
    return this.name || undefined;
  }
}

export class YangIdentityStmt extends YangStatement {
  bases: YangIdentifierRef[];
  if_features: string[];

  constructor(init: Partial<YangIdentityStmt> = {}) {
    super(init);
    this.keyword = "identity";
    this.bases = init.bases ?? [];
    this.if_features = init.if_features ?? [];
  }

  override get_schema_node(): string | undefined {
    return undefined;
  }
}

export class YangBitStmt {
  name: string;
  position?: number;

  constructor(init: Partial<YangBitStmt> = {}) {
    this.name = init.name ?? "";
    this.position = init.position;
  }
}

export class YangPatternSpec {
  pattern: string;
  invert_match: boolean;
  error_message?: string;
  error_app_tag?: string;

  /** Compiles the XSD regex, so an unsupported pattern fails when the module loads. */
  constructor(init: Partial<YangPatternSpec> = {}) {
    this.pattern = init.pattern ?? "";
    if (this.pattern) {
      translateXsdRegex(this.pattern);
    }
    this.invert_match = init.invert_match ?? false;
    this.error_message = init.error_message;
    this.error_app_tag = init.error_app_tag;
  }
}

/** Common declaration identity; specialized attributes live only on their family. */
export class YangTypeStmt {
  name: string;
  declare prefix?: string;
  declare scope_module?: string;
  declare context?: string;
  declare units?: string;

  constructor(init: Partial<YangTypeStmt> = {}) {
    this.name = init.name ?? "";
    if (init.prefix !== undefined) this.prefix = init.prefix;
    if (init.scope_module !== undefined) this.scope_module = init.scope_module;
    if (init.context !== undefined) this.context = init.context;
    if (init.units !== undefined) this.units = init.units;
  }
}

export class YangRestriction {
  expression: string;
  declare error_message?: string;
  declare error_app_tag?: string;
  declare description?: string;
  declare reference?: string;

  constructor(expression: string, metadata: Omit<Partial<YangRestriction>, "expression"> = {}) {
    this.expression = expression;
    for (const key of ["error_message", "error_app_tag", "description", "reference"] as const) {
      if (metadata[key] !== undefined && metadata[key] !== "") this[key] = metadata[key];
    }
  }
}

export class YangNumericTypeStmt extends YangTypeStmt {
  declare range_restriction?: YangRestriction;
}
export class YangDecimalTypeStmt extends YangNumericTypeStmt {
  declare fraction_digits?: number;
}
export class YangBinaryTypeStmt extends YangTypeStmt {
  declare length_restriction?: YangRestriction;
}
export class YangStringTypeStmt extends YangBinaryTypeStmt {
  declare patterns?: YangPatternSpec[];
}
export class YangEnumerationTypeStmt extends YangTypeStmt {
  enums: string[] = [];
}
export class YangBitsTypeStmt extends YangTypeStmt {
  bits: YangBitStmt[] = [];
}
export class YangUnionTypeStmt extends YangTypeStmt {
  types: YangTypeStmt[] = [];
}
export class YangInstanceIdentifierTypeStmt extends YangTypeStmt {
  require_instance = true;
}
export class YangLeafrefTypeStmt extends YangInstanceIdentifierTypeStmt {
  declare path?: PathNode;
  declare xpath_prefixes?: Record<string, string>;
}
export class YangIdentityrefTypeStmt extends YangTypeStmt {
  identityref_bases: YangIdentifierRef[] = [];
}
export class YangDerivedTypeStmt extends YangTypeStmt {
  declare range_restriction?: YangRestriction;
  declare length_restriction?: YangRestriction;
  declare patterns?: YangPatternSpec[];
  declare enums?: string[];
  declare bits?: YangBitStmt[];
  declare require_instance?: boolean;
}

const TYPE_STATEMENT_CLASSES = {
  plain: YangTypeStmt, numeric: YangNumericTypeStmt, decimal: YangDecimalTypeStmt,
  binary: YangBinaryTypeStmt, string: YangStringTypeStmt, enumeration: YangEnumerationTypeStmt,
  bits: YangBitsTypeStmt, union: YangUnionTypeStmt, leafref: YangLeafrefTypeStmt,
  identityref: YangIdentityrefTypeStmt, "instance-identifier": YangInstanceIdentifierTypeStmt,
  derived: YangDerivedTypeStmt
};

export function createTypeStmt(init: Partial<YangTypeStmt> & { name: string }): YangTypeStmt {
  const Constructor = TYPE_STATEMENT_CLASSES[typeStatementKind(init.name, init.prefix)];
  return new Constructor(init);
}


export class YangContainerStmt extends YangStatementWithWhen {
  must_statements: YangMustStmt[];
  presence?: string;
  /** Groupings declared in this container. Visible here and in descendants only. */
  groupings: Record<string, YangGroupingStmt>;

  constructor(init: Partial<YangContainerStmt> = {}) {
    super(init);
    this.keyword = "container";
    this.must_statements = init.must_statements ?? [];
    this.presence = init.presence;
    this.groupings = init.groupings ?? {};
  }
}

/** Notification statement (RFC 7950 §7.16); body parsed like a container subtree. */
export class YangNotificationStmt extends YangContainerStmt {
  constructor(init: Partial<YangNotificationStmt> = {}) {
    super(init);
    this.keyword = "notification";
  }
}

/** RPC/action ``input`` block (RFC 7950 §7.14.2); no statement argument. */
export class YangInputStmt extends YangContainerStmt {
  constructor(init: Partial<YangInputStmt> = {}) {
    super({ name: "input", ...init });
    this.keyword = "input";
  }
}

/** RPC/action ``output`` block (RFC 7950 §7.14.3); no statement argument. */
export class YangOutputStmt extends YangContainerStmt {
  constructor(init: Partial<YangOutputStmt> = {}) {
    super({ name: "output", ...init });
    this.keyword = "output";
  }
}

/** RPC statement (RFC 7950 §7.14). Data nodes appear only under ``input`` / ``output``. */
export class YangRpcStmt extends YangStatementWithWhen {
  must_statements: YangMustStmt[];

  constructor(init: Partial<YangRpcStmt> = {}) {
    super(init);
    this.keyword = "rpc";
    this.must_statements = init.must_statements ?? [];
  }
}

/** Action statement (RFC 7950 §7.15): an operation on a container or list instance. */
export class YangActionStmt extends YangRpcStmt {
  constructor(init: Partial<YangActionStmt> = {}) {
    super(init);
    this.keyword = "action";
  }
}

export class YangListStmt extends YangStatementWithWhen {
  must_statements: YangMustStmt[];
  key?: string;
  min_elements?: number;
  max_elements?: number;
  /** One entry per `unique` statement: descendant paths with prefixes stripped (`a/b`). */
  unique: string[][];

  constructor(init: Partial<YangListStmt> = {}) {
    super(init);
    this.keyword = "list";
    this.must_statements = init.must_statements ?? [];
    this.key = init.key;
    this.unique = init.unique ?? [];
    this.min_elements = init.min_elements;
    this.max_elements = init.max_elements;
  }
}

export class YangLeafStmt extends YangStatementWithWhen {
  must_statements: YangMustStmt[];
  type?: YangTypeStmt;
  mandatory: boolean;
  default?: unknown;

  constructor(init: Partial<YangLeafStmt> = {}) {
    super(init);
    this.keyword = "leaf";
    this.must_statements = init.must_statements ?? [];
    this.type = init.type;
    this.mandatory = init.mandatory ?? false;
    this.default = init.default;
  }
}

export class YangLeafListStmt extends YangStatementWithWhen {
  must_statements: YangMustStmt[];
  type?: YangTypeStmt;
  min_elements?: number;
  max_elements?: number;
  defaults: unknown[];

  constructor(init: Partial<YangLeafListStmt> = {}) {
    super(init);
    this.keyword = "leaf-list";
    this.must_statements = init.must_statements ?? [];
    this.type = init.type;
    this.min_elements = init.min_elements;
    this.max_elements = init.max_elements;
    this.defaults = init.defaults ?? [];
  }
}

export class YangAnydataStmt extends YangStatementWithWhen {
  must_statements: YangMustStmt[];
  mandatory: boolean;

  constructor(init: Partial<YangAnydataStmt> = {}) {
    super(init);
    this.keyword = "anydata";
    this.must_statements = init.must_statements ?? [];
    this.mandatory = init.mandatory ?? false;
  }
}

export class YangAnyxmlStmt extends YangStatementWithWhen {
  must_statements: YangMustStmt[];
  mandatory: boolean;

  constructor(init: Partial<YangAnyxmlStmt> = {}) {
    super(init);
    this.keyword = "anyxml";
    this.must_statements = init.must_statements ?? [];
    this.mandatory = init.mandatory ?? false;
  }
}

export type ExtensionApplyCallback = (
  invocation: YangExtensionInvocationStmt,
  contextModule: YangModule
) => YangStatement | undefined;

export class YangExtensionStmt extends YangStatement {
  argument_name: string;
  argument_yin_element?: boolean;
  apply_callback?: ExtensionApplyCallback;

  constructor(init: Partial<YangExtensionStmt> = {}) {
    super(init);
    this.keyword = "extension";
    this.argument_name = init.argument_name ?? "";
    this.argument_yin_element = init.argument_yin_element;
    this.apply_callback = init.apply_callback;
  }

  apply(invocation: YangExtensionInvocationStmt, options: { context_module: YangModule }): YangStatement | undefined {
    if (!this.apply_callback) {
      return invocation;
    }
    return this.apply_callback(invocation, options.context_module);
  }

  override get_schema_node(): string | undefined {
    return undefined;
  }
}

export class YangExtensionInvocationStmt extends YangStatementWithWhen {
  must_statements: YangMustStmt[];
  prefix: string;
  resolved_module: YangModule;
  resolved_extension: YangExtensionStmt;
  argument?: string;

  constructor(init: {
    prefix: string;
    resolved_module: YangModule;
    resolved_extension: YangExtensionStmt;
    argument?: string;
  } & Partial<YangExtensionInvocationStmt>) {
    super(init);
    this.keyword = "extension-invocation";
    this.must_statements = init.must_statements ?? [];
    this.prefix = init.prefix;
    this.resolved_module = init.resolved_module;
    this.resolved_extension = init.resolved_extension;
    this.argument = init.argument;

    if (!this.prefix) {
      throw new Error("extension invocation requires a non-empty prefix");
    }
    if (!this.resolved_module) {
      throw new Error("extension invocation requires resolved_module");
    }
    if (!this.resolved_extension) {
      throw new Error("extension invocation requires resolved_extension");
    }
  }

  override get_schema_node(): string | undefined {
    return undefined;
  }
}

type PrefixScope = {
  name?: string;
  prefix?: string;
  belongs_to_module?: string;
  import_prefixes?: Record<string, PrefixScope>;
};

/** Prefix -> module name in `module`'s scope: its own prefix or an `import`; a submodule names its parent. */
export function modulePrefixResolver(module: unknown): (prefix: string) => string | undefined {
  const scope = module as PrefixScope;
  return (prefix) => {
    const own = (scope.prefix ?? "").replace(/^['"]|['"]$/g, "");
    const target = prefix === own ? scope : scope.import_prefixes?.[prefix];
    return target ? target.belongs_to_module || target.name : undefined;
  };
}

export class YangParsedXPathBase {
  expression: string;
  description: string;
  ast?: ASTNode;
  /** Module each prefixed step (`prefix:name`, `prefix:*`) is bound to, by prefix; recorded by {@link bindPrefixes}. */
  xpath_prefixes?: Record<string, string>;

  constructor(init: { expression: string; description?: string }) {
    this.expression = init.expression;
    this.description = init.description ?? "";
    if (this.expression) {
      this.ast = parseXPath(this.expression);
    }
  }

  /** Bind prefixed steps to the modules `module` maps their prefixes to; an unknown prefix throws. */
  bindPrefixes(module: unknown): void {
    const used = xpathPrefixes(this.ast);
    if (used.size === 0) return;
    const resolve = modulePrefixResolver(module);
    bindXPathPrefixes(this.ast, resolve, this.expression);
    this.xpath_prefixes = Object.fromEntries([...used].map((prefix) => [prefix, resolve(prefix) as string]));
  }
}

export class YangMustStmt extends YangParsedXPathBase {
  error_message: string;

  constructor(init: { expression: string; description?: string; error_message?: string }) {
    super(init);
    this.error_message = init.error_message ?? "";
  }
}

export class YangWhenStmt extends YangParsedXPathBase {
  evaluate_with_parent_context: boolean;

  constructor(init: { expression: string; description?: string; evaluate_with_parent_context?: boolean }) {
    super(init);
    this.evaluate_with_parent_context = init.evaluate_with_parent_context ?? false;
  }

  get condition(): string {
    return this.expression;
  }
}

export class YangLeafrefStmt {
  path: string;
  require_instance: boolean;

  constructor(init: Partial<YangLeafrefStmt> = {}) {
    this.path = init.path ?? "";
    this.require_instance = init.require_instance ?? true;
  }
}

export class YangGroupingStmt extends YangStatement {
  constructor(init: Partial<YangGroupingStmt> = {}) {
    super(init);
    this.keyword = "grouping";
  }
}

export class YangUsesStmt extends YangStatementWithWhen {
  /**
   * Local grouping identifier (never ``prefix:name``).
   * Optional import prefix is in {@link grouping_prefix}.
   */
  grouping_name: string;
  /** Import prefix when ``uses`` names a grouping from another module. */
  grouping_prefix?: string;
  refines: YangRefineStmt[];
  augmentations: YangAugmentStmt[];

  constructor(init: Partial<YangUsesStmt> = {}) {
    super(init);
    this.keyword = "uses";
    this.grouping_name = init.grouping_name ?? "";
    this.grouping_prefix = init.grouping_prefix;
    this.refines = init.refines ?? [];
    this.augmentations = init.augmentations ?? [];
  }

  /** Display / cycle-key form ``name`` or ``prefix:name``. */
  grouping_qname(): string {
    return this.grouping_prefix
      ? `${this.grouping_prefix}:${this.grouping_name}`
      : this.grouping_name;
  }

  override get_schema_node(): string | undefined {
    return undefined;
  }
}

export class YangAugmentStmt extends YangStatementWithWhen {
  /** Original path string (display / round-trip). */
  augment_path: string;
  /** Path segments parsed once from {@link augment_path}. */
  augment_path_segments: YangIdentifierRef[];

  constructor(init: Partial<YangAugmentStmt> = {}) {
    super(init);
    this.keyword = "augment";
    this.augment_path = init.augment_path ?? "";
    this.augment_path_segments = init.augment_path_segments ?? [];
  }

  override get_schema_node(): string | undefined {
    return undefined;
  }
}

export class YangRefineStmt extends YangStatementWithMust {
  target_path: string;
  type?: YangTypeStmt;
  min_elements?: number;
  max_elements?: number;
  refined_defaults: unknown[];
  refined_mandatory?: boolean;
  refined_config?: boolean;
  if_features: string[];

  constructor(init: Partial<YangRefineStmt> = {}) {
    super(init);
    this.keyword = "refine";
    this.target_path = init.target_path ?? "";
    this.type = init.type;
    this.min_elements = init.min_elements;
    this.max_elements = init.max_elements;
    this.refined_defaults = init.refined_defaults ?? [];
    this.refined_mandatory = init.refined_mandatory;
    this.refined_config = init.refined_config;
    this.if_features = init.if_features ?? [];
  }
}

export class YangChoiceStmt extends YangStatementWithWhen {
  mandatory: boolean;
  cases: YangCaseStmt[];
  /** RFC 7950 §7.9.3 case name. */
  default?: string;

  constructor(init: Partial<YangChoiceStmt> = {}) {
    super(init);
    this.keyword = "choice";
    this.mandatory = init.mandatory ?? false;
    this.cases = init.cases ?? [];
    this.default = init.default;
  }

  override child_names(data: Record<string, unknown>): Set<string> {
    for (const c of this.cases) {
      if (c.statements.some((s) => s.name && s.name in data)) {
        return new Set(c.statements.map((s) => s.name).filter((name): name is string => Boolean(name)));
      }
    }
    return new Set();
  }

  validate_case_unique_child_names(): void {
    const seen = new Map<string, string>();
    for (const c of this.cases) {
      for (const sub of c.statements) {
        const seg = sub.get_schema_node();
        if (!seg) {
          continue;
        }
        if (seen.has(seg)) {
          const prevCase = seen.get(seg);
          throw new YangSemanticError(
            `Choice '${this.name}': schema node '${seg}' appears in case '${prevCase}' and again in case '${c.name}' ` +
              "(RFC 7950: names of nodes in the cases of a choice must be unique)."
          );
        }
        seen.set(seg, c.name);
      }
    }
  }
}

export class YangCaseStmt extends YangStatementWithWhen {
  constructor(init: Partial<YangCaseStmt> = {}) {
    super(init);
    this.keyword = "case";
  }

  override child_names(_data: Record<string, unknown>): Set<string> {
    return new Set(this.statements.map((s) => s.name).filter((name): name is string => Boolean(name)));
  }
}
