import { YangSemanticError } from "./errors";
import { parseXPath } from "../xpath/parser";
import type { XPathAstNode } from "../xpath/ast";
import type { YangModule } from "./module";

export type ASTNode = XPathAstNode;
export type PathNode = XPathAstNode;

export class YangStatementList {
  statements: YangStatement[];

  constructor(statements: YangStatement[] = []) {
    this.statements = statements;
  }

  find_statement(name: string): YangStatement | undefined {
    return this.statements.find((stmt) => stmt.name === name);
  }

  findStatement(name: string): YangStatement | undefined {
    return this.find_statement(name);
  }

  get_all_leaves(): YangLeafStmt[] {
    const leaves: YangLeafStmt[] = [];
    for (const stmt of this.statements) {
      leaves.push(...this.collectLeaves(stmt));
    }
    return leaves;
  }

  getAllLeaves(): YangLeafStmt[] {
    return this.get_all_leaves();
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

  constructor(init: Partial<YangStatement> = {}) {
    super(init.statements ?? []);
    this.keyword = init.keyword ?? "";
    this.name = init.name ?? "";
    this.description = init.description ?? "";
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

  constructor(init: Partial<YangStatementWithWhen> = {}) {
    super(init);
    this.when = init.when;
    this.if_features = init.if_features ?? [];
  }

  override get_schema_node(): string | undefined {
    return this.name || undefined;
  }
}

export class YangTypedefStmt extends YangStatement {
  type?: YangTypeStmt;

  constructor(init: Partial<YangTypedefStmt> = {}) {
    super(init);
    this.keyword = "typedef";
    this.type = init.type;
  }

  override get_schema_node(): string | undefined {
    return this.name || undefined;
  }
}

export class YangIdentityStmt extends YangStatement {
  bases: string[];
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

export class YangTypeStmt {
  name: string;
  pattern?: string;
  pattern_error_message?: string;
  pattern_error_app_tag?: string;
  length?: string;
  range?: string;
  fraction_digits?: number;
  enums: string[];
  bits: YangBitStmt[];
  types: YangTypeStmt[];
  path?: PathNode;
  require_instance: boolean;
  identityref_bases: string[];

  constructor(init: Partial<YangTypeStmt> = {}) {
    this.name = init.name ?? "";
    this.pattern = init.pattern;
    this.pattern_error_message = init.pattern_error_message;
    this.pattern_error_app_tag = init.pattern_error_app_tag;
    this.length = init.length;
    this.range = init.range;
    this.fraction_digits = init.fraction_digits;
    this.enums = init.enums ?? [];
    this.bits = init.bits ?? [];
    this.types = init.types ?? [];
    this.path = init.path;
    this.require_instance = init.require_instance ?? true;
    this.identityref_bases = init.identityref_bases ?? [];
  }
}

export class YangContainerStmt extends YangStatementWithWhen {
  must_statements: YangMustStmt[];
  presence?: string;

  constructor(init: Partial<YangContainerStmt> = {}) {
    super(init);
    this.keyword = "container";
    this.must_statements = init.must_statements ?? [];
    this.presence = init.presence;
  }
}

export class YangListStmt extends YangStatementWithWhen {
  must_statements: YangMustStmt[];
  key?: string;
  min_elements?: number;
  max_elements?: number;

  constructor(init: Partial<YangListStmt> = {}) {
    super(init);
    this.keyword = "list";
    this.must_statements = init.must_statements ?? [];
    this.key = init.key;
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

export class YangParsedXPathBase {
  expression: string;
  description: string;
  ast?: ASTNode;

  constructor(init: { expression: string; description?: string }) {
    this.expression = init.expression;
    this.description = init.description ?? "";
    if (this.expression) {
      this.ast = parseXPath(this.expression);
    }
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
  grouping_name: string;
  refines: YangRefineStmt[];

  constructor(init: Partial<YangUsesStmt> = {}) {
    super(init);
    this.keyword = "uses";
    this.grouping_name = init.grouping_name ?? "";
    this.refines = init.refines ?? [];
  }

  override get_schema_node(): string | undefined {
    return undefined;
  }
}

export class YangAugmentStmt extends YangStatementWithWhen {
  augment_path: string;

  constructor(init: Partial<YangAugmentStmt> = {}) {
    super(init);
    this.keyword = "augment";
    this.augment_path = init.augment_path ?? "";
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
    this.if_features = init.if_features ?? [];
  }
}

export class YangChoiceStmt extends YangStatementWithWhen {
  mandatory: boolean;
  cases: YangCaseStmt[];

  constructor(init: Partial<YangChoiceStmt> = {}) {
    super(init);
    this.keyword = "choice";
    this.mandatory = init.mandatory ?? false;
    this.cases = init.cases ?? [];
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
