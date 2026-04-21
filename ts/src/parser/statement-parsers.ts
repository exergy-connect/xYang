import {
  YangExtensionInvocationStmt,
  YangExtensionStmt,
  YangLeafListStmt,
  YangMustStmt,
  YangRefineStmt,
  YangTypeStmt,
  YangUsesStmt
} from "../core/ast";
import { YangSemanticError, YangSyntaxError } from "../core/errors";
import { SerializedStatement } from "../core/model";
import { ParserContext, TokenStream, YangTokenType } from "./parser-context";
import {
  AnydataStatementParser,
  AnyxmlStatementParser,
  AugmentStatementParser,
  BitsStatementParser,
  ChoiceStatementParser,
  ContainerStatementParser,
  ExtensionStatementParser,
  FeatureStatementParser,
  GroupingStatementParser,
  IdentityStatementParser,
  LeafListStatementParser,
  LeafStatementParser,
  ListStatementParser,
  ModuleStatementParser,
  MustStatementParser,
  RefineStatementParser,
  RevisionStatementParser,
  SubmoduleStatementParser,
  TypeStatementParser,
  TypedefStatementParser,
  UsesStatementParser,
  WhenStatementParser
} from "./statements";
import { is_unsupported_construct_start, skip_unsupported_construct } from "./unsupported-skip";

/** Options for {@link StatementParsers.parseStatement} to restrict valid statement starts in nested contexts (e.g. RFC 7950 `case-stmt`). */
export type ParseStatementOptions = {
  /**
   * If set, the next statement must begin with one of these token types, or with a prefixed
   * extension invocation (`identifier:keyword`).
   */
  allowedStatementStarts?: ReadonlySet<YangTokenType> | readonly YangTokenType[];
  /** Included in errors, e.g. `under 'case'`. */
  restrictionContext?: string;
};

function serializedKeywordFromAstStatement(stmt: { keyword?: unknown }): string {
  if (typeof stmt.keyword === "string" && stmt.keyword.trim().length > 0) {
    return stmt.keyword;
  }
  throw new YangSemanticError("Internal error: cannot serialize AST statement without a keyword");
}

type TypeShape = {
  name: string;
  pattern?: string;
  pattern_error_message?: string;
  pattern_error_app_tag?: string;
  length?: string;
  range?: string;
  fraction_digits?: number;
  path?: unknown;
  require_instance?: boolean;
  identityref_bases?: string[];
  enums?: string[];
  bits?: Array<{ name: string; position: number }>;
  types?: TypeShape[];
};

export class StatementParsers {
  private readonly importResolver?: (
    moduleName: string,
    localPrefix: string,
    revisionDate: string | undefined,
    context: ParserContext,
    tokens: TokenStream
  ) => Record<string, unknown>;

  private readonly anydata_parser = new AnydataStatementParser(this);
  private readonly anyxml_parser = new AnyxmlStatementParser(this);
  private readonly augment_parser = new AugmentStatementParser(this);
  readonly bits_parser = new BitsStatementParser(this);
  private readonly choice_parser = new ChoiceStatementParser(this);
  private readonly container_parser = new ContainerStatementParser(this);
  private readonly extension_parser = new ExtensionStatementParser(this);
  private readonly feature_parser = new FeatureStatementParser(this);
  private readonly grouping_parser = new GroupingStatementParser(this);
  private readonly identity_parser = new IdentityStatementParser(this);
  private readonly leaf_parser = new LeafStatementParser(this);
  private readonly leaf_list_parser = new LeafListStatementParser(this);
  private readonly list_parser = new ListStatementParser(this);
  private readonly module_parser = new ModuleStatementParser(this);
  private readonly must_parser = new MustStatementParser(this);
  private readonly refine_parser = new RefineStatementParser(this);
  readonly revision_parser = new RevisionStatementParser(this);
  private readonly submodule_parser = new SubmoduleStatementParser(this, this.module_parser);
  private readonly type_parser = new TypeStatementParser(this);
  private readonly typedef_parser = new TypedefStatementParser(this);
  private readonly uses_parser = new UsesStatementParser(this);
  private readonly when_parser = new WhenStatementParser(this);

  private readonly statementKeywordHandlers: Partial<
    Record<YangTokenType, (tokens: TokenStream, context: ParserContext) => SerializedStatement>
  > = {
    [YangTokenType.LEAF]: (tokens, context) => this.fromAst(this.leaf_parser.parse_leaf(tokens, context)),
    [YangTokenType.LEAF_LIST]: (tokens, context) => this.fromAst(this.leaf_list_parser.parse_leaf_list(tokens, context)),
    [YangTokenType.CONTAINER]: (tokens, context) => this.fromAst(this.container_parser.parse_container(tokens, context)),
    [YangTokenType.LIST]: (tokens, context) => this.fromAst(this.list_parser.parse_list(tokens, context)),
    [YangTokenType.ANYDATA]: (tokens, context) => this.fromAst(this.anydata_parser.parse_anydata(tokens, context)),
    [YangTokenType.ANYXML]: (tokens, context) => this.fromAst(this.anyxml_parser.parse_anyxml(tokens, context)),
    [YangTokenType.CHOICE]: (tokens, context) => this.fromAst(this.choice_parser.parse_choice(tokens, context)),
    [YangTokenType.CASE]: () => {
      throw new YangSyntaxError("'case' is only valid as a substatement of 'choice' (RFC 7950)");
    },
    [YangTokenType.TYPEDEF]: (tokens, context) => this.fromAst(this.typedef_parser.parse_typedef(tokens, context)),
    [YangTokenType.TYPE]: (tokens, context) => this.fromType(this.type_parser.parse_type(tokens, context)),
    [YangTokenType.USES]: (tokens, context) => this.fromAst(this.uses_parser.parse_uses(tokens, context)),
    [YangTokenType.REFINE]: (tokens, context) => {
      this.refine_parser.parse_refine(tokens, context);
      return { __class__: "YangStatement", keyword: "refine", statements: [] };
    },
    [YangTokenType.MUST]: (tokens, context) => this.fromMust(this.must_parser.parse_must(tokens, context)),
    [YangTokenType.WHEN]: (tokens, context) => {
      this.when_parser.parse_when(tokens, context);
      return { __class__: "YangStatement", keyword: "when", statements: [] };
    },
    [YangTokenType.EXTENSION]: (tokens, context) => this.fromAst(this.extension_parser.parse_extension_stmt(tokens, context)),
    [YangTokenType.FEATURE]: (tokens, context) => {
      this.feature_parser.parse_feature_stmt(tokens, context);
      return { __class__: "YangStatement", keyword: "feature", statements: [] };
    },
    [YangTokenType.IF_FEATURE]: (tokens, context) => {
      this.feature_parser.parse_if_feature_stmt(tokens, context);
      return { __class__: "YangStatement", keyword: "if-feature", statements: [] };
    },
    [YangTokenType.IDENTITY]: (tokens, context) => {
      this.identity_parser.parse_identity(tokens, context);
      return { __class__: "YangStatement", keyword: "identity", statements: [] };
    },
    [YangTokenType.GROUPING]: (tokens, context) => {
      this.grouping_parser.parse_grouping(tokens, context);
      return { __class__: "YangStatement", keyword: "grouping", statements: [] };
    },
    [YangTokenType.AUGMENT]: (tokens, context) => this.fromAst(this.augment_parser.parse_augment(tokens, context)),
    [YangTokenType.REVISION]: (tokens, context) => {
      this.revision_parser.parse_revision(tokens, context);
      return { __class__: "YangStatement", keyword: "revision", statements: [] };
    },
    [YangTokenType.DESCRIPTION]: (tokens, context) => {
      this.parse_description(tokens, context);
      return {
        __class__: "YangStatement",
        keyword: "description",
        argument: (context.current_parent as any)?.description ?? "",
        name: "description",
        statements: []
      };
    },
    [YangTokenType.MANDATORY]: (tokens, context) => {
      this.parse_leaf_mandatory(tokens, context);
      return { __class__: "YangStatement", keyword: "mandatory", statements: [] };
    },
    [YangTokenType.DEFAULT]: (tokens, context) => {
      this.parse_leaf_default(tokens, context);
      return { __class__: "YangStatement", keyword: "default", statements: [] };
    },
    [YangTokenType.KEY]: (tokens, context) => {
      this.parse_list_key(tokens, context);
      return { __class__: "YangStatement", keyword: "key", statements: [] };
    },
    [YangTokenType.MIN_ELEMENTS]: (tokens, context) => {
      this.parse_min_elements(tokens, context);
      return { __class__: "YangStatement", keyword: "min-elements", statements: [] };
    },
    [YangTokenType.MAX_ELEMENTS]: (tokens, context) => {
      this.parse_max_elements(tokens, context);
      return { __class__: "YangStatement", keyword: "max-elements", statements: [] };
    },
    [YangTokenType.ORDERED_BY]: (tokens, context) => {
      this.parse_ordered_by(tokens);
      return { __class__: "YangStatement", keyword: "ordered-by", statements: [] };
    },
    [YangTokenType.PRESENCE]: (tokens, context) => {
      this.parse_presence(tokens, context);
      return { __class__: "YangStatement", keyword: "presence", statements: [] };
    }
  };

  constructor(options: {
    importResolver?: (
      moduleName: string,
      localPrefix: string,
      revisionDate: string | undefined,
      context: ParserContext,
      tokens: TokenStream
    ) => Record<string, unknown>;
  } = {}) {
    this.importResolver = options.importResolver;
  }

  private assertStatementStartAllowed(
    tokens: TokenStream,
    allowed: ReadonlySet<YangTokenType> | readonly YangTokenType[],
    restrictionContext?: string
  ): void {
    const set = allowed instanceof Set ? allowed : new Set(allowed);
    const kw = tokens.peek_type();
    if (set.has(kw)) {
      return;
    }
    if (kw === YangTokenType.IDENTIFIER && tokens.peek_type_at(1) === YangTokenType.COLON) {
      return;
    }
    const ctx = restrictionContext ? ` ${restrictionContext}` : "";
    const got = tokens.peek() ?? "<end>";
    const allowedLabels = [...set]
      .map((t) => String(t))
      .sort()
      .join(", ");
    throw new YangSyntaxError(
      `Invalid statement starting with '${got}'${ctx}. Allowed here: ${allowedLabels}; prefixed extension statements (identifier:keyword) are also allowed.`
    );
  }

  parseModule(tokens: TokenStream, context: ParserContext): SerializedStatement {
    const root = this.parseStatement(tokens, context);
    if (root.keyword !== "module") {
      throw new YangSemanticError("Expected top-level 'module' statement");
    }
    return root;
  }

  /** Serialize an in-memory AST statement (e.g. under `grouping`) for module data / uses expansion. */
  serializeAstStatement(stmt: unknown): SerializedStatement {
    return this.fromAst(stmt as any);
  }

  parseStatement(tokens: TokenStream, context: ParserContext, options?: ParseStatementOptions): SerializedStatement {
    if (options?.allowedStatementStarts) {
      this.assertStatementStartAllowed(tokens, options.allowedStatementStarts, options.restrictionContext);
    }
    const kw = tokens.peek_type();

    if (kw === YangTokenType.IDENTIFIER && tokens.peek_type_at(1) === YangTokenType.COLON) {
      return this.parse_prefixed_extension_statement(tokens, context);
    }

    const handler = this.statementKeywordHandlers[kw];
    if (handler) {
      return handler(tokens, context);
    }

    return this.parse_statement_generic(tokens, context);
  }

  private parse_statement_generic(tokens: TokenStream, context: ParserContext): SerializedStatement {
    const tokenType = tokens.peek_type();

    if (tokenType === YangTokenType.MODULE) {
      return this.parse_top_level_module(tokens, context);
    }
    if (tokenType === YangTokenType.SUBMODULE) {
      this.submodule_parser.parse_submodule(tokens, context);
      return { __class__: "YangStatement", keyword: "submodule", statements: [] };
    }
    if (tokenType === YangTokenType.YANG_VERSION) {
      this.module_parser.parse_yang_version(tokens, context);
      return {
        __class__: "YangStatement",
        keyword: "yang-version",
        argument: (context.module as any).yang_version,
        name: "yang-version",
        statements: []
      };
    }
    if (tokenType === YangTokenType.NAMESPACE) {
      this.module_parser.parse_namespace(tokens, context);
      return {
        __class__: "YangStatement",
        keyword: "namespace",
        argument: (context.module as any).namespace,
        name: "namespace",
        statements: []
      };
    }
    if (tokenType === YangTokenType.PREFIX) {
      this.module_parser.parse_prefix(tokens, context);
      return {
        __class__: "YangStatement",
        keyword: "prefix",
        argument: (context.module as any).prefix,
        name: "prefix",
        statements: []
      };
    }
    if (tokenType === YangTokenType.ORGANIZATION) {
      this.module_parser.parse_organization(tokens, context);
      return { __class__: "YangStatement", keyword: "organization", statements: [] };
    }
    if (tokenType === YangTokenType.CONTACT) {
      this.module_parser.parse_contact(tokens, context);
      return { __class__: "YangStatement", keyword: "contact", statements: [] };
    }
    if (tokenType === YangTokenType.IMPORT) {
      this.module_parser.parse_import_stmt(tokens, context);
      return { __class__: "YangStatement", keyword: "import", statements: [] };
    }
    if (tokenType === YangTokenType.INCLUDE) {
      this.module_parser.parse_include_stmt(tokens, context);
      return { __class__: "YangStatement", keyword: "include", statements: [] };
    }

    if (this.skip_unsupported_if_present(tokens, "generic")) {
      return { __class__: "YangStatement", keyword: "unsupported", statements: [] };
    }

    const first = tokens.consume();
    let keyword = first;
    if (tokens.peek_type() === YangTokenType.COLON) {
      tokens.consume_type(YangTokenType.COLON);
      keyword = `${keyword}:${tokens.consume_type(YangTokenType.IDENTIFIER)}`;
    }

    const argument = this.parse_argument(tokens);
    const statements: SerializedStatement[] = [];
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        statements.push(this.parseStatement(tokens, context));
      }
      tokens.consume_type(YangTokenType.RBRACE);
      tokens.consume_if_type(YangTokenType.SEMICOLON);
    } else {
      tokens.consume_if_type(YangTokenType.SEMICOLON);
    }

    const out: SerializedStatement = { __class__: "YangStatement", keyword, name: argument, argument, statements };
    if (keyword === "type") {
      out.type = this.extract_type_shape(out);
    }
    return out;
  }

  parse_argument(tokens: TokenStream): string {
    const parts: string[] = [];
    while (tokens.has_more()) {
      const t = tokens.peek_type();
      if (t === YangTokenType.SEMICOLON || t === YangTokenType.LBRACE) {
        break;
      }
      if (t === YangTokenType.STRING) {
        parts.push(this.parse_string_concatenation(tokens));
      } else if (t === YangTokenType.PLUS) {
        tokens.consume_type(YangTokenType.PLUS);
      } else {
        parts.push(tokens.consume());
      }
    }
    return parts.join("").trim();
  }

  parse_string_concatenation(tokens: TokenStream): string {
    const parts = [tokens.consume_type(YangTokenType.STRING)];
    while (tokens.has_more() && tokens.peek_type() === YangTokenType.PLUS) {
      tokens.consume_type(YangTokenType.PLUS);
      parts.push(tokens.consume_type(YangTokenType.STRING));
    }
    return parts.join("");
  }

  consume_qname_from_identifier(tokens: TokenStream): string {
    const parts = [tokens.consume_type(YangTokenType.IDENTIFIER)];
    while (tokens.consume_if_type(YangTokenType.COLON)) {
      parts.push(tokens.consume_type(YangTokenType.IDENTIFIER));
    }
    return parts.join(":");
  }

  add_to_parent_or_module(context: ParserContext, stmt: unknown): void {
    const parent: any = context.current_parent as any;
    if (parent && Array.isArray(parent.statements)) {
      parent.statements.push(stmt);
      return;
    }
    const module = context.module as any;
    if (Array.isArray(module.statements)) {
      module.statements.push(stmt);
    }
  }

  skip_unsupported_if_present(tokens: TokenStream, context: string): boolean {
    if (!is_unsupported_construct_start(tokens)) {
      return false;
    }
    skip_unsupported_construct(tokens, { context });
    return true;
  }

  private parse_top_level_module(tokens: TokenStream, context: ParserContext): SerializedStatement {
    tokens.consume_type(YangTokenType.MODULE);
    const moduleName = tokens.consume_type(YangTokenType.IDENTIFIER);
    (context.module as Record<string, unknown>).name = moduleName;
    tokens.consume_type(YangTokenType.LBRACE);

    const moduleStatements: SerializedStatement[] = [];
    while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
      moduleStatements.push(this.parseStatement(tokens, context));
    }
    tokens.consume_type(YangTokenType.RBRACE);

    return {
      __class__: "YangStatement",
      keyword: "module",
      name: moduleName,
      argument: moduleName,
      statements: moduleStatements
    };
  }

  private fromAst(stmt: {
    keyword?: string;
    name?: string;
    constructor: { name: string };
    statements?: unknown[];
    type?: YangTypeStmt;
    must_statements?: YangMustStmt[];
    when?: {
      expression?: string;
      description?: string;
      evaluate_with_parent_context?: boolean;
    };
    mandatory?: boolean;
    default?: unknown;
    key?: string;
    description?: string;
    augment_path?: string;
    if_features?: string[];
    argument_name?: string;
    argument_yin_element?: boolean;
    prefix?: string;
    argument?: string;
    resolved_module?: { name?: string };
    resolved_extension?: { name?: string };
    cases?: unknown[];
  }): SerializedStatement {
    const keyword = serializedKeywordFromAstStatement(stmt as object);

    const children = [
      ...this.serializeAstChildren(stmt.statements ?? []),
      ...this.serializeAstChildren(stmt.cases ?? [])
    ];

    const out: SerializedStatement = {
      __class__: "YangStatement",
      keyword,
      name: stmt.name,
      argument: stmt.name,
      statements: children
    };

    if (stmt.type) {
      out.type = this.fromTypeShape(stmt.type);
    }
    if (stmt.mandatory !== undefined) {
      out.mandatory = stmt.mandatory;
    }
    if (stmt.default !== undefined) {
      out.default = stmt.default;
    }
    if (keyword === "leaf-list") {
      const llDefaults = (stmt as { defaults?: unknown[] }).defaults;
      if (Array.isArray(llDefaults) && llDefaults.length > 0) {
        out.defaults = [...llDefaults];
      }
    }
    if (stmt.key !== undefined) {
      out.key = stmt.key;
    }
    if (stmt.description) {
      out.description = stmt.description;
    }
    if (Array.isArray(stmt.if_features) && stmt.if_features.length > 0) {
      out.if_features = [...stmt.if_features];
    }
    if (keyword === "extension") {
      if (typeof stmt.argument_name === "string") {
        out.argument_name = stmt.argument_name;
      }
      if (typeof stmt.argument_yin_element === "boolean") {
        out.argument_yin_element = stmt.argument_yin_element;
      }
    }
    if (keyword === "augment" && typeof stmt.augment_path === "string") {
      out.argument = stmt.augment_path;
      out.augment_path = stmt.augment_path;
    }
    if (keyword === "extension-invocation") {
      out.keyword = stmt.name ?? "extension-invocation";
      out.argument = stmt.argument;
      out.prefix = stmt.prefix;
      out.resolved_module_name = stmt.resolved_module?.name;
      out.resolved_extension_name = stmt.resolved_extension?.name;
    }
    if (stmt.when && typeof stmt.when.expression === "string") {
      out.when = {
        expression: stmt.when.expression,
        description: stmt.when.description ?? "",
        evaluate_with_parent_context: stmt.when.evaluate_with_parent_context ?? false
      };
    }
    if (Array.isArray(stmt.must_statements) && stmt.must_statements.length > 0) {
      out.statements = [
        ...(out.statements ?? []),
        ...stmt.must_statements.map((mustStmt) => this.fromMust(mustStmt))
      ];
    }
    if (keyword === "uses") {
      const u = stmt as YangUsesStmt;
      if (typeof u.grouping_name === "string" && u.grouping_name.length > 0) {
        out.grouping_name = u.grouping_name;
        out.argument = u.grouping_name;
      }
      if (Array.isArray(u.refines) && u.refines.length > 0) {
        out.refines = u.refines.map((r) => this.serializeRefineStmt(r as YangRefineStmt));
      }
    }
    const presence = (stmt as { presence?: string }).presence;
    if (typeof presence === "string" && presence.length > 0) {
      out.presence = presence;
    }

    return out;
  }

  private serializeRefineStmt(r: YangRefineStmt): SerializedStatement {
    const out: SerializedStatement = {
      __class__: "YangStatement",
      keyword: "refine",
      name: "refine",
      argument: r.target_path,
      refine_target_path: r.target_path,
      statements: []
    };
    if (typeof r.min_elements === "number") {
      out.min_elements = r.min_elements;
    }
    if (typeof r.max_elements === "number") {
      out.max_elements = r.max_elements;
    }
    if (typeof r.refined_mandatory === "boolean") {
      out.refined_mandatory = r.refined_mandatory;
    }
    if (Array.isArray(r.refined_defaults) && r.refined_defaults.length > 0) {
      out.refined_defaults = [...r.refined_defaults];
    }
    if (Array.isArray(r.if_features) && r.if_features.length > 0) {
      out.if_features = [...r.if_features];
    }
    if (Array.isArray(r.must_statements) && r.must_statements.length > 0) {
      out.statements = r.must_statements.map((m) => this.fromMust(m));
    }
    return out;
  }

  private serializeAstChildren(children: unknown[]): SerializedStatement[] {
    const out: SerializedStatement[] = [];
    for (const child of children) {
      if (!child || typeof child !== "object") {
        continue;
      }
      out.push(this.fromAst(child as any));
    }
    return out;
  }

  private fromType(type_stmt: YangTypeStmt): SerializedStatement {
    return {
      __class__: "YangStatement",
      keyword: "type",
      name: type_stmt.name,
      argument: type_stmt.name,
      type: this.fromTypeShape(type_stmt),
      statements: []
    };
  }

  private fromMust(must_stmt: YangMustStmt): SerializedStatement {
    return {
      __class__: "YangStatement",
      keyword: "must",
      name: must_stmt.expression,
      argument: must_stmt.expression,
      error_message: must_stmt.error_message,
      statements: []
    };
  }

  private fromTypeShape(type_stmt: YangTypeStmt): TypeShape {
    return {
      name: type_stmt.name,
      pattern: type_stmt.pattern,
      pattern_error_message: type_stmt.pattern_error_message,
      pattern_error_app_tag: type_stmt.pattern_error_app_tag,
      length: type_stmt.length,
      range: type_stmt.range,
      fraction_digits: type_stmt.fraction_digits,
      path: type_stmt.path,
      require_instance: type_stmt.require_instance,
      identityref_bases: [...type_stmt.identityref_bases],
      enums: [...type_stmt.enums],
      bits: type_stmt.bits.map((b) => ({ name: b.name, position: b.position ?? 0 })),
      types: type_stmt.types.map((t) => this.fromTypeShape(t))
    };
  }

  private extract_type_shape(typeStmt: SerializedStatement): TypeShape {
    const name = typeStmt.argument ?? "string";
    const shape: TypeShape = { name };
    for (const child of typeStmt.statements ?? []) {
      if (child.keyword === "pattern" && child.argument) shape.pattern = child.argument;
      if (child.keyword === "length" && child.argument) shape.length = child.argument;
      if (child.keyword === "range" && child.argument) shape.range = child.argument;
      if (child.keyword === "fraction-digits" && child.argument) {
        const n = Number.parseInt(child.argument, 10);
        if (!Number.isNaN(n)) shape.fraction_digits = n;
      }
      if (child.keyword === "enum" && child.argument) shape.enums = [...(shape.enums ?? []), child.argument];
      if (child.keyword === "bit" && child.argument) {
        const bits = shape.bits ?? [];
        bits.push({ name: child.argument, position: bits.length === 0 ? 0 : Math.max(...bits.map((b) => b.position)) + 1 });
        shape.bits = bits;
      }
      if (name === "union" && child.keyword === "type") {
        shape.types = [...(shape.types ?? []), this.extract_type_shape(child)];
      }
    }
    return shape;
  }

  parse_description(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.DESCRIPTION);
    const desc = tokens.consume_type(YangTokenType.STRING);
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        tokens.consume();
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);

    const parent: any = context.current_parent;
    if (parent && "description" in parent) {
      parent.description = desc;
    }
  }

  parse_optional_description(tokens: TokenStream, context: ParserContext): void {
    if (tokens.has_more() && tokens.peek_type() === YangTokenType.DESCRIPTION) {
      this.parse_description(tokens, context);
    }
  }

  parse_reference_string_only(tokens: TokenStream): void {
    tokens.consume_type(YangTokenType.REFERENCE);
    tokens.consume_type(YangTokenType.STRING);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  register_import(
    context: ParserContext,
    moduleName: string,
    localPrefix: string,
    revisionDate: string | undefined,
    tokens: TokenStream
  ): void {
    const module = context.module as Record<string, unknown>;
    const ownPrefix = String(module.prefix ?? "").replace(/^['"]|['"]$/g, "");
    if (localPrefix === ownPrefix) {
      throw new YangSemanticError(`Import prefix '${localPrefix}' must differ from this module's prefix`);
    }

    const imports = (module.import_prefixes as Record<string, Record<string, unknown>> | undefined) ?? {};
    module.import_prefixes = imports;

    if (imports[localPrefix]) {
      throw new YangSemanticError(`Duplicate import prefix '${localPrefix}'`);
    }

    if (!this.importResolver) {
      throw new YangSemanticError("Import resolution is not configured for this parser instance");
    }
    imports[localPrefix] = this.importResolver(moduleName, localPrefix, revisionDate, context, tokens);
  }

  parse_ordered_by(tokens: TokenStream): void {
    tokens.consume_type(YangTokenType.ORDERED_BY);
    tokens.consume();
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_list_key(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.KEY);
    const [value] = tokens.consume_oneof([YangTokenType.STRING, YangTokenType.IDENTIFIER]);
    const parent: any = context.current_parent;
    if (parent && "key" in parent) parent.key = value;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_min_elements(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.MIN_ELEMENTS);
    const value = Number.parseInt(tokens.consume_type(YangTokenType.INTEGER), 10);
    const parent: any = context.current_parent;
    if (parent && "min_elements" in parent) parent.min_elements = value;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_max_elements(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.MAX_ELEMENTS);
    const value = Number.parseInt(tokens.consume_type(YangTokenType.INTEGER), 10);
    const parent: any = context.current_parent;
    if (parent && "max_elements" in parent) parent.max_elements = value;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_leaf_mandatory(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.MANDATORY);
    const [, tt] = tokens.consume_oneof([YangTokenType.TRUE, YangTokenType.FALSE]);
    const parent: unknown = context.current_parent;
    if (parent instanceof YangRefineStmt) {
      parent.refined_mandatory = tt === YangTokenType.TRUE;
      tokens.consume_if_type(YangTokenType.SEMICOLON);
      return;
    }
    if (parent && typeof parent === "object" && "mandatory" in parent) {
      (parent as { mandatory?: boolean }).mandatory = tt === YangTokenType.TRUE;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_leaf_default(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.DEFAULT);
    const value = this.parse_default_value_tokens(tokens);
    const parent: unknown = context.current_parent;
    if (parent instanceof YangRefineStmt) {
      parent.refined_defaults.push(value);
    } else if (parent instanceof YangLeafListStmt) {
      parent.defaults.push(value);
    } else if (parent && typeof parent === "object" && "default" in parent) {
      (parent as { default?: unknown }).default = value;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_presence(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.PRESENCE);
    const parent: any = context.current_parent;
    const value = tokens.consume_type(YangTokenType.STRING);
    if (parent && "presence" in parent) parent.presence = value;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_default_value_tokens(tokens: TokenStream): string {
    const tt = tokens.peek_type();
    if (tt === YangTokenType.STRING) return tokens.consume_type(YangTokenType.STRING);
    if (tt === YangTokenType.INTEGER) return tokens.consume_type(YangTokenType.INTEGER);
    if (tt === YangTokenType.IDENTIFIER) return tokens.consume_type(YangTokenType.IDENTIFIER);
    if (tt === YangTokenType.TRUE) {
      tokens.consume_type(YangTokenType.TRUE);
      return "true";
    }
    if (tt === YangTokenType.FALSE) {
      tokens.consume_type(YangTokenType.FALSE);
      return "false";
    }
    throw new YangSemanticError(`Expected default value, got ${tt}`);
  }

  private parse_prefixed_extension_statement(tokens: TokenStream, context: ParserContext): SerializedStatement {
    const prefix = tokens.consume_type(YangTokenType.IDENTIFIER);
    tokens.consume_type(YangTokenType.COLON);
    const extensionName = tokens.consume_type(YangTokenType.IDENTIFIER);

    const resolvedModule = this.resolve_prefixed_module(context, prefix);
    if (!resolvedModule) {
      throw new YangSemanticError(`Unknown extension prefix '${prefix}' in invocation ${prefix}:${extensionName}`);
    }

    const resolvedExtension = this.resolve_extension_definition(resolvedModule, extensionName);
    if (!resolvedExtension) {
      throw new YangSemanticError(
        `Unknown extension '${extensionName}' in module '${resolvedModule.name ?? ""}' for invocation ${prefix}:${extensionName}`
      );
    }

    const argument = this.consume_optional_extension_argument(tokens);
    const invocation = new YangExtensionInvocationStmt({
      name: `${prefix}:${extensionName}`,
      prefix,
      resolved_module: resolvedModule as any,
      resolved_extension: resolvedExtension,
      argument
    });

    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const childContext = context.push_parent(invocation);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parseStatement(tokens, childContext);
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);

    this.add_to_parent_or_module(context, invocation);
    return this.fromAst(invocation);
  }

  private consume_optional_extension_argument(tokens: TokenStream): string | undefined {
    if (!tokens.has_more()) {
      return undefined;
    }
    const tt = tokens.peek_type();
    if (tt === YangTokenType.LBRACE || tt === YangTokenType.SEMICOLON) {
      return undefined;
    }
    if (tt === YangTokenType.STRING) {
      return this.parse_string_concatenation(tokens);
    }
    if (
      tt === YangTokenType.IDENTIFIER ||
      tt === YangTokenType.INTEGER ||
      tt === YangTokenType.DOTTED_NUMBER ||
      tt === YangTokenType.TRUE ||
      tt === YangTokenType.FALSE
    ) {
      return tokens.consume();
    }
    return undefined;
  }

  private resolve_prefixed_module(context: ParserContext, prefix: string): Record<string, unknown> | undefined {
    const module = context.module as Record<string, unknown>;
    const ownPrefix = String(module.prefix ?? "").replace(/^['"]|['"]$/g, "");
    if (prefix === ownPrefix) {
      return module;
    }
    const imports = module.import_prefixes as Record<string, Record<string, unknown>> | undefined;
    return imports?.[prefix];
  }

  private resolve_extension_definition(
    resolvedModule: Record<string, unknown>,
    extensionName: string
  ): YangExtensionStmt | undefined {
    const direct = (resolvedModule.extensions as Record<string, YangExtensionStmt> | undefined)?.[extensionName];
    if (direct) {
      return direct;
    }

    const statements = Array.isArray(resolvedModule.statements)
      ? (resolvedModule.statements as SerializedStatement[])
      : [];
    const extStmt = statements.find((stmt) => stmt.keyword === "extension" && stmt.name === extensionName);
    if (!extStmt) {
      return undefined;
    }
    return new YangExtensionStmt({
      name: extensionName,
      argument_name: typeof extStmt.argument_name === "string" ? extStmt.argument_name : "",
      argument_yin_element: typeof extStmt.argument_yin_element === "boolean" ? extStmt.argument_yin_element : undefined
    });
  }
}
