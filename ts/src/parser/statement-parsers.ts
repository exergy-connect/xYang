import * as kw from "./keywords";
import {
  YangAugmentStmt,
  YangExtensionInvocationStmt,
  YangExtensionStmt,
  YangLeafListStmt,
  YangListStmt,
  YangMustStmt,
  YangNotificationStmt,
  YangRefineStmt,
  YangTypedefStmt,
  YangTypeStmt,
  YangUnionTypeStmt,
  YangDerivedTypeStmt,
  YangStringTypeStmt,
  YangNumericTypeStmt,
  YangBinaryTypeStmt,
  YangDecimalTypeStmt,
  YangEnumerationTypeStmt,
  YangBitsTypeStmt,
  YangLeafrefTypeStmt,
  YangIdentityrefTypeStmt,
  YangInstanceIdentifierTypeStmt,
  YangUsesStmt
} from "../core/ast";
import { formatIdentifierRef } from "../core/identifier-ref";
import { YangSemanticError, YangSyntaxError } from "../core/errors";
import { YangModule, YangStatement, normalizeTypeShape } from "../core/model";
import { DISPATCH_REGISTRY } from "./dispatch-registry";
import { ParserContext, TokenStream, YangTokenType } from "./parser-context";
import {
  AnydataStatementParser,
  AnyxmlStatementParser,
  AugmentStatementParser,
  DeviationStatementParser,
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
  NotificationStatementParser,
  RpcStatementParser,
  MustStatementParser,
  RefineStatementParser,
  RevisionStatementParser,
  SubmoduleStatementParser,
  TypeStatementParser,
  TypedefStatementParser,
  UsesStatementParser,
  WhenStatementParser
} from "./statements";
import {
  is_unsupported_construct_start,
  skip_unsupported_construct
} from "./unsupported-skip";

/** RFC 7950 identifier: ASCII letter or `_`, then letters, digits, `_`, `-`, `.`. */
function isIdentifierText(text: string): boolean {
  return /^[A-Za-z_][A-Za-z0-9_.\-]*$/.test(text);
}

type DispatchFn = (tokens: TokenStream, context: ParserContext, ...args: any[]) => void;

/** Options for {@link StatementParsers.parseStatement} to restrict valid statement starts in nested contexts (e.g. RFC 7950 `case-stmt`). */
export type ParseStatementOptions = {
  /**
   * If set, the next statement must begin with one of these token types, or with a prefixed
   * extension invocation (`identifier:keyword`).
   */
  allowedStatementStarts?: ReadonlySet<string | YangTokenType> | readonly (string | YangTokenType)[];
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
  prefix?: string;
  scope_module?: string;
  context?: string;
  xpath_prefixes?: Record<string, string>;
  patterns?: Array<{
    pattern: string;
    invert_match?: boolean;
    error_message?: string;
    error_app_tag?: string;
  }>;
  length?: string;
  range?: string;
  length_error_message?: string;
  length_error_app_tag?: string;
  range_error_message?: string;
  range_error_app_tag?: string;
  fraction_digits?: number;
  path?: unknown;
  require_instance?: boolean;
  identityref_bases?: Array<{ prefix?: string; name: string }>;
  enums?: string[];
  bits?: Array<{ name: string; position: number }>;
  types?: TypeShape[];
};

export class StatementParsers {
  /** Set while an ``include``d submodule is being merged into its parent. */
  includingSubmoduleName?: string;

  private readonly importResolver?: (
    moduleName: string,
    localPrefix: string,
    revisionDate: string | undefined,
    context: ParserContext,
    tokens: TokenStream
  ) => YangModule;

  private readonly includeResolver?: (
    submoduleName: string,
    revisionDate: string | undefined,
    context: ParserContext,
    tokens: TokenStream
  ) => void;

  readonly anydata_parser = new AnydataStatementParser(this);
  readonly anyxml_parser = new AnyxmlStatementParser(this);
  private readonly augment_parser = new AugmentStatementParser(this);
  private readonly deviation_parser = new DeviationStatementParser(this);
  readonly bits_parser = new BitsStatementParser(this);
  readonly choice_parser = new ChoiceStatementParser(this);
  readonly container_parser = new ContainerStatementParser(this);
  private readonly extension_parser = new ExtensionStatementParser(this);
  readonly feature_parser = new FeatureStatementParser(this);
  private readonly grouping_parser = new GroupingStatementParser(this);
  private readonly identity_parser = new IdentityStatementParser(this);
  readonly leaf_parser = new LeafStatementParser(this);
  readonly leaf_list_parser = new LeafListStatementParser(this);
  readonly list_parser = new ListStatementParser(this);
  private readonly module_parser = new ModuleStatementParser(this);
  readonly notification_parser = new NotificationStatementParser(this);
  readonly rpc_parser = new RpcStatementParser(this);
  readonly must_parser = new MustStatementParser(this);
  private readonly refine_parser = new RefineStatementParser(this);
  readonly revision_parser = new RevisionStatementParser(this);
  private readonly submodule_parser = new SubmoduleStatementParser(this, this.module_parser);
  readonly type_parser = new TypeStatementParser(this);
  readonly typedef_parser = new TypedefStatementParser(this);
  readonly uses_parser = new UsesStatementParser(this);
  readonly when_parser = new WhenStatementParser(this);

  /** Captures ``prefix`` / ``revision-date`` while an ``import`` body is open. */
  importAcc: { localPrefix?: string; revisionDate?: string } | undefined;
  /** ``revision-date`` captured while an ``include`` body is open. */
  includeRevisionDate: string | undefined;
  private runtimeDispatch: Record<string, Record<string, DispatchFn>> = {};

  private readonly statementKeywordHandlers: Partial<
    Record<string | YangTokenType, (tokens: TokenStream, context: ParserContext) => YangStatement>
  > = {
    [kw.LEAF]: (tokens, context) => this.fromAst(this.leaf_parser.parse_leaf(tokens, context)),
    [kw.LEAF_LIST]: (tokens, context) => this.fromAst(this.leaf_list_parser.parse_leaf_list(tokens, context)),
    [kw.CONTAINER]: (tokens, context) => this.fromAst(this.container_parser.parse_container(tokens, context)),
    [kw.LIST]: (tokens, context) => this.fromAst(this.list_parser.parse_list(tokens, context)),
    [kw.NOTIFICATION]: (tokens, context) =>
      this.fromAst(this.notification_parser.parse_notification(tokens, context)),
    [kw.RPC]: (tokens, context) => this.fromAst(this.rpc_parser.parse_rpc(tokens, context)),
    [kw.ACTION]: (tokens, context) => this.fromAst(this.rpc_parser.parse_action(tokens, context)),
    [kw.ANYDATA]: (tokens, context) => this.fromAst(this.anydata_parser.parse_anydata(tokens, context)),
    [kw.ANYXML]: (tokens, context) => this.fromAst(this.anyxml_parser.parse_anyxml(tokens, context)),
    [kw.CHOICE]: (tokens, context) => this.fromAst(this.choice_parser.parse_choice(tokens, context)),
    [kw.CASE]: () => {
      throw new YangSyntaxError("'case' is only valid as a substatement of 'choice' (RFC 7950)");
    },
    [kw.INPUT]: () => {
      throw new YangSyntaxError("'input' is only valid as a substatement of 'rpc' or 'action' (RFC 7950)");
    },
    [kw.OUTPUT]: () => {
      throw new YangSyntaxError("'output' is only valid as a substatement of 'rpc' or 'action' (RFC 7950)");
    },
    [kw.TYPEDEF]: (tokens, context) => this.fromAst(this.typedef_parser.parse_typedef(tokens, context)),
    [kw.TYPE]: (tokens, context) => this.fromType(this.type_parser.parse_type(tokens, context)),
    [kw.USES]: (tokens, context) => this.fromAst(this.uses_parser.parse_uses(tokens, context)),
    [kw.REFINE]: (tokens, context) => {
      this.refine_parser.parse_refine(tokens, context);
      return new YangStatement({ keyword: "refine", statements: [] });
    },
    [kw.MUST]: (tokens, context) => this.fromMust(this.must_parser.parse_must(tokens, context)),
    [kw.WHEN]: (tokens, context) => {
      this.when_parser.parse_when(tokens, context);
      return new YangStatement({ keyword: "when", statements: [] });
    },
    [kw.EXTENSION]: (tokens, context) => this.fromAst(this.extension_parser.parse_extension_stmt(tokens, context)),
    [kw.FEATURE]: (tokens, context) => {
      this.feature_parser.parse_feature_stmt(tokens, context);
      return new YangStatement({ keyword: "feature", statements: [] });
    },
    [kw.IF_FEATURE]: (tokens, context) => {
      this.feature_parser.parse_if_feature_stmt(tokens, context);
      return new YangStatement({ keyword: "if-feature", statements: [] });
    },
    [kw.IDENTITY]: (tokens, context) => {
      this.identity_parser.parse_identity(tokens, context);
      return new YangStatement({ keyword: "identity", statements: [] });
    },
    [kw.GROUPING]: (tokens, context) => {
      this.grouping_parser.parse_grouping(tokens, context);
      return new YangStatement({ keyword: "grouping", statements: [] });
    },
    [kw.AUGMENT]: (tokens, context) => this.fromAst(this.augment_parser.parse_augment(tokens, context)),
    [kw.DEVIATION]: (tokens, context) => this.deviation_parser.parse_deviation(tokens, context),
    [kw.REVISION]: (tokens, context) => {
      this.revision_parser.parse_revision(tokens, context);
      return new YangStatement({ keyword: "revision", statements: [] });
    },
    [kw.DESCRIPTION]: (tokens, context) => {
      const desc = this.parse_description(tokens, context);
      return new YangStatement({        keyword: "description",
        argument: desc,
        name: "description",
        statements: []
});
    },
    [kw.MANDATORY]: (tokens, context) => {
      this.parse_leaf_mandatory(tokens, context);
      return new YangStatement({ keyword: "mandatory", statements: [] });
    },
    [kw.DEFAULT]: (tokens, context) => {
      this.parse_leaf_default(tokens, context);
      return new YangStatement({ keyword: "default", statements: [] });
    },
    [kw.KEY]: (tokens, context) => {
      this.parse_list_key(tokens, context);
      return new YangStatement({ keyword: "key", statements: [] });
    },
    [kw.UNIQUE]: (tokens, context) => {
      this.parse_list_unique(tokens, context);
      return new YangStatement({ keyword: "unique", statements: [] });
    },
    [kw.MIN_ELEMENTS]: (tokens, context) => {
      this.parse_min_elements(tokens, context);
      return new YangStatement({ keyword: "min-elements", statements: [] });
    },
    [kw.MAX_ELEMENTS]: (tokens, context) => {
      this.parse_max_elements(tokens, context);
      return new YangStatement({ keyword: "max-elements", statements: [] });
    },
    [kw.ORDERED_BY]: (tokens, context) => {
      this.parse_ordered_by(tokens);
      return new YangStatement({ keyword: "ordered-by", statements: [] });
    },
    [kw.PRESENCE]: (tokens, context) => {
      this.parse_presence(tokens, context);
      return new YangStatement({ keyword: "presence", statements: [] });
    },
    [kw.REFERENCE]: (tokens, context) => {
      this.parse_reference(tokens, context);
      return new YangStatement({ keyword: "reference", statements: [] });
    },
    [kw.CONFIG]: (tokens, context) => {
      this.parse_config(tokens, context);
      return new YangStatement({ keyword: "config", statements: [] });
    }
  };

  constructor(options: {
    importResolver?: (
      moduleName: string,
      localPrefix: string,
      revisionDate: string | undefined,
      context: ParserContext,
      tokens: TokenStream
    ) => YangModule;
    includeResolver?: (
      submoduleName: string,
      revisionDate: string | undefined,
      context: ParserContext,
      tokens: TokenStream
    ) => void;
  } = {}) {
    this.importResolver = options.importResolver;
    this.includeResolver = options.includeResolver;
    this.runtimeDispatch = this.buildRuntimeDispatch();
  }

  /** Parse a ``submodule`` file into *context* (the including module). */
  parseSubmodule(tokens: TokenStream, context: ParserContext): void {
    this.submodule_parser.parse_submodule(tokens, context);
  }

  pushIncludedStatement(context: ParserContext, stmt: YangStatement): void {
    const mod = context.module as { __included_statements?: YangStatement[] };
    (mod.__included_statements ??= []).push(stmt);
  }

  drainIncludedStatements(context: ParserContext): YangStatement[] {
    const mod = context.module as { __included_statements?: YangStatement[] };
    const pending = mod.__included_statements ?? [];
    mod.__included_statements = [];
    return pending;
  }

  resolveInclude(
    context: ParserContext,
    submoduleName: string,
    revisionDate: string | undefined,
    tokens: TokenStream
  ): void {
    if (!this.includeResolver) {
      throw new YangSemanticError("Include resolution is not configured for this parser instance");
    }
    this.includeResolver(submoduleName, revisionDate, context, tokens);
  }

  dispatch_key(tokens: TokenStream): string | YangTokenType {
    return tokens.peek_type() === YangTokenType.IDENTIFIER ? (tokens.peek() ?? "") : tokens.peek_type();
  }

  private assertStatementStartAllowed(
    tokens: TokenStream,
    allowed: ReadonlySet<string | YangTokenType> | readonly (string | YangTokenType)[],
    restrictionContext?: string
  ): void {
    const set = allowed instanceof Set ? allowed : new Set(allowed);
    const kw = this.dispatch_key(tokens);
    if (set.has(kw)) {
      return;
    }
    if (tokens.peek_type() === YangTokenType.IDENTIFIER && tokens.peek_type_at(1) === YangTokenType.COLON) {
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

  parseModule(tokens: TokenStream, context: ParserContext): YangStatement {
    const root = this.parseStatement(tokens, context);
    if (root.keyword !== "module") {
      throw new YangSemanticError("Expected top-level 'module' statement");
    }
    return root;
  }

  /** Serialize an in-memory AST statement (e.g. under `grouping`) for module data / uses expansion. */
  serializeAstStatement(stmt: unknown): YangStatement {
    return this.fromAst(stmt as any);
  }

  parseStatement(tokens: TokenStream, context: ParserContext, options?: ParseStatementOptions): YangStatement {
    if (options?.allowedStatementStarts) {
      this.assertStatementStartAllowed(tokens, options.allowedStatementStarts, options.restrictionContext);
    }
    const parent = context.dispatch_parent;
    if (parent) {
      const key = this.dispatch_key(tokens);
      const allowed = DISPATCH_REGISTRY[parent]?.keywords;
      if (typeof key === "string" && allowed?.has(key)) {
        const allowedHandler = this.statementKeywordHandlers[key];
        if (allowedHandler) {
          return allowedHandler(tokens, context);
        }
        return this.parse_statement_generic(tokens, context);
      }
      if (this.is_prefixed_extension_start(tokens)) {
        return this.parse_prefixed_extension_statement(tokens, context);
      }
      this.skip_unsupported_or_raise_unknown(tokens, context.dispatch_error ?? parent);
    }

    if (this.is_prefixed_extension_start(tokens)) {
      return this.parse_prefixed_extension_statement(tokens, context);
    }

    const key = this.dispatch_key(tokens);
    const handler = this.statementKeywordHandlers[key];
    if (handler) {
      return handler(tokens, context);
    }

    return this.parse_statement_generic(tokens, context);
  }

  private parse_statement_generic(tokens: TokenStream, context: ParserContext): YangStatement {
    const tokenType = this.dispatch_key(tokens);

    if (tokenType === kw.MODULE) {
      return this.parse_top_level_module(tokens, context);
    }
    if (tokenType === kw.SUBMODULE) {
      this.submodule_parser.parse_submodule(tokens, context);
      return new YangStatement({ keyword: "submodule", statements: [] });
    }
    if (tokenType === kw.YANG_VERSION) {
      this.module_parser.parse_yang_version(tokens, context);
      return new YangStatement({        keyword: "yang-version",
        argument: (context.module as any).yang_version,
        name: "yang-version",
        statements: []
});
    }
    if (tokenType === kw.NAMESPACE) {
      this.module_parser.parse_namespace(tokens, context);
      return new YangStatement({        keyword: "namespace",
        argument: (context.module as any).namespace,
        name: "namespace",
        statements: []
});
    }
    if (tokenType === kw.PREFIX) {
      this.module_parser.parse_prefix(tokens, context);
      return new YangStatement({        keyword: "prefix",
        argument: (context.module as any).prefix,
        name: "prefix",
        statements: []
});
    }
    if (tokenType === kw.ORGANIZATION) {
      this.module_parser.parse_organization(tokens, context);
      return new YangStatement({ keyword: "organization", statements: [] });
    }
    if (tokenType === kw.CONTACT) {
      this.module_parser.parse_contact(tokens, context);
      return new YangStatement({ keyword: "contact", statements: [] });
    }
    if (tokenType === kw.IMPORT) {
      this.module_parser.parse_import_stmt(tokens, context);
      return new YangStatement({ keyword: "import", statements: [] });
    }
    if (tokenType === kw.INCLUDE) {
      this.module_parser.parse_include_stmt(tokens, context);
      return new YangStatement({ keyword: "include", statements: [] });
    }

    if (this.skip_unsupported_if_present(tokens, "generic")) {
      return new YangStatement({ keyword: "unsupported", statements: [] });
    }

    const peek = tokens.peek();
    if (peek === kw.INPUT || peek === kw.OUTPUT) {
      tokens.syntaxError(
        `'${peek}' is only valid as a substatement of 'rpc' or 'action' (RFC 7950)`
      );
    }

    if (context.dispatch_parent) {
      this.skip_unsupported_or_raise_unknown(tokens, context.dispatch_error ?? context.dispatch_parent);
    }

    const first = tokens.consume();
    let keyword = first;
    if (tokens.peek_type() === YangTokenType.COLON) {
      tokens.consume_type(YangTokenType.COLON);
      keyword = `${keyword}:${tokens.consume_type(YangTokenType.IDENTIFIER)}`;
    }

    const argument = this.parse_argument(tokens);
    const statements: YangStatement[] = [];
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        statements.push(this.parseStatement(tokens, context));
      }
      tokens.consume_type(YangTokenType.RBRACE);
      tokens.consume_if_type(YangTokenType.SEMICOLON);
    } else {
      tokens.consume_if_type(YangTokenType.SEMICOLON);
    }

    const out: YangStatement = new YangStatement({ keyword, name: argument, argument, statements });
    if (keyword === "type") {
      out.type = normalizeTypeShape(this.extract_type_shape(out));
    }
    return out;
  }

  parse_argument(tokens: TokenStream): string {
    if (!tokens.has_more()) {
      return "";
    }
    const t = tokens.peek_type();
    if (t === YangTokenType.SEMICOLON || t === YangTokenType.LBRACE || t === YangTokenType.RBRACE) {
      return "";
    }
    return this.parse_string_argument(tokens);
  }

  parse_string_concatenation(tokens: TokenStream): string {
    if (!tokens.has_more() || tokens.peek_type() !== YangTokenType.STRING) {
      return this.parse_string_argument(tokens);
    }
    const parts = [tokens.consume_type(YangTokenType.STRING)];
    while (tokens.has_more() && tokens.peek_type() === YangTokenType.PLUS) {
      tokens.consume_type(YangTokenType.PLUS);
      if (!tokens.has_more() || tokens.peek_type() !== YangTokenType.STRING) {
        tokens.syntaxError("Expected quoted string after '+'");
      }
      parts.push(tokens.consume_type(YangTokenType.STRING));
    }
    return parts.join("");
  }

  parse_string_argument(tokens: TokenStream): string {
    if (!tokens.has_more()) {
      tokens.syntaxError("Expected statement argument, got 'end'");
    }
    if (tokens.peek_type() === YangTokenType.STRING) {
      return this.parse_string_concatenation(tokens);
    }
    return this.read_unquoted_argument(tokens);
  }

  /** Exact lexical `true` or `false`, quoted or unquoted. */
  parse_boolean_argument(tokens: TokenStream, statement: string): boolean {
    const tt = tokens.peek_type();
    if (
      !tokens.has_more() ||
      tt === YangTokenType.SEMICOLON ||
      tt === YangTokenType.LBRACE ||
      tt === YangTokenType.RBRACE
    ) {
      tokens.syntaxError(`${statement} argument must be 'true' or 'false', got ''`);
    }
    const raw = this.parse_string_argument(tokens);
    if (raw === kw.TRUE) {
      return true;
    }
    if (raw === kw.FALSE) {
      return false;
    }
    tokens.syntaxError(`${statement} argument must be 'true' or 'false', got '${raw}'`);
  }

  /** Adjacent lexemes up to whitespace, `;`, or `{` (RFC 7950 §6.1.3). */
  read_unquoted_argument(tokens: TokenStream): string {
    const stop = new Set<YangTokenType>([
      YangTokenType.SEMICOLON,
      YangTokenType.LBRACE,
      YangTokenType.RBRACE,
      YangTokenType.STRING
    ]);
    const parts: string[] = [];
    let prevLine: number | undefined;
    let prevEnd: number | undefined;
    while (tokens.has_more()) {
      const tok = tokens.peek_token();
      if (!tok || stop.has(tok.type)) {
        break;
      }
      if (prevEnd !== undefined && (tok.line_num !== prevLine || tok.char_pos !== prevEnd)) {
        break;
      }
      parts.push(tok.value);
      prevLine = tok.line_num;
      prevEnd = tok.char_pos + tok.value.length;
      tokens.consume();
    }
    if (parts.length === 0) {
      const got = tokens.has_more() ? tokens.peek() : "end";
      tokens.syntaxError(`Expected statement argument, got '${got}'`);
    }
    return parts.join("");
  }

  /** One argument, then reject text that is not an identifier. */
  parse_identifier_argument(tokens: TokenStream, statement: string): string {
    const raw = this.parse_string_argument(tokens);
    if (!isIdentifierText(raw)) {
      tokens.syntaxError(`${statement} argument must be an identifier, got '${raw}'`);
    }
    return raw;
  }

  /** One argument, then reject text outside the statement's keyword grammar. */
  parse_keyword_argument(tokens: TokenStream, statement: string, allowed: readonly string[]): string {
    const raw = this.parse_string_argument(tokens);
    if (!allowed.includes(raw)) {
      tokens.syntaxError(`${statement} argument must be ${allowed.map((item) => `'${item}'`).join(" or ")}, got '${raw}'`);
    }
    return raw;
  }

  /** One argument that is a signed decimal integer. */
  parse_integer_argument(tokens: TokenStream, statement: string): number {
    const raw = this.parse_string_argument(tokens);
    if (!/^[+-]?\d+$/.test(raw)) {
      tokens.syntaxError(`${statement} argument must be an integer, got '${raw}'`);
    }
    return Number.parseInt(raw, 10);
  }

  /** ``status current|deprecated|obsolete``, quoted or unquoted. */
  parse_status_argument(tokens: TokenStream): string {
    tokens.consume(kw.STATUS);
    const value = this.parse_keyword_argument(tokens, "status", ["current", "deprecated", "obsolete"]);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return value;
  }

  /** `min-elements` / `max-elements`: an integer, or `unbounded` (no bound). */
  parse_integer_or_unbounded(tokens: TokenStream, statement: string): number | undefined {
    const raw = this.parse_string_argument(tokens);
    if (raw === "unbounded") {
      return undefined;
    }
    if (!/^[+-]?\d+$/.test(raw)) {
      tokens.syntaxError(`${statement} argument must be an integer or 'unbounded', got '${raw}'`);
    }
    return Number.parseInt(raw, 10);
  }

  substatement_handler(
    tokens: TokenStream,
    dispatch: Record<string, (tokens: TokenStream, context: ParserContext) => void>
  ): ((tokens: TokenStream, context: ParserContext) => void) | undefined {
    const key = this.dispatch_key(tokens);
    if (typeof key === "string") {
      return dispatch[key];
    }
    return undefined;
  }

  is_prefixed_extension_start(tokens: TokenStream): boolean {
    return (
      tokens.peek_type_at(0) === YangTokenType.IDENTIFIER &&
      tokens.peek_type_at(1) === YangTokenType.COLON &&
      tokens.peek_type_at(2) === YangTokenType.IDENTIFIER
    );
  }

  handlerFor(parent: string, keyword: string): DispatchFn | undefined {
    return this.runtimeDispatch[parent]?.[keyword];
  }

  dispatchSubstatement(
    tokens: TokenStream,
    context: ParserContext,
    parent: string,
    errorContext: string,
    ...handlerArgs: unknown[]
  ): void {
    const key = this.dispatch_key(tokens);
    const handler = typeof key === "string" ? this.runtimeDispatch[parent]?.[key] : undefined;
    if (handler) {
      handler(tokens, context, ...handlerArgs);
      return;
    }
    if (this.is_prefixed_extension_start(tokens)) {
      this.parse_prefixed_extension_statement(tokens, context);
      return;
    }
    this.skip_unsupported_or_raise_unknown(tokens, errorContext);
  }

  parseBody(
    tokens: TokenStream,
    context: ParserContext,
    parent: string,
    errorContext: string,
    ...handlerArgs: unknown[]
  ): void {
    while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
      this.dispatchSubstatement(tokens, context, parent, errorContext, ...handlerArgs);
    }
  }

  private parseDiscardedDescription(tokens: TokenStream, context: ParserContext): void {
    this.parse_optional_description(tokens, context.push_parent({}));
  }

  private buildRuntimeDispatch(): Record<string, Record<string, DispatchFn>> {
    const drop = (fn: (tokens: TokenStream, context: ParserContext) => void): DispatchFn =>
      (tokens, context) => {
        fn(tokens, context);
      };
    const mod = this.module_parser;
    const typ = this.type_parser;
    const bits = this.bits_parser;
    const choice = this.choice_parser;
    const defaults: Record<string, DispatchFn> = {
      [kw.LEAF]: (t, c) => {
        this.leaf_parser.parse_leaf(t, c);
      },
      [kw.LIST]: (t, c) => {
        this.list_parser.parse_list(t, c);
      },
      [kw.LEAF_LIST]: (t, c) => {
        this.leaf_list_parser.parse_leaf_list(t, c);
      },
      [kw.CONTAINER]: (t, c) => {
        this.container_parser.parse_container(t, c);
      },
      [kw.NOTIFICATION]: (t, c) => {
        this.notification_parser.parse_notification(t, c);
      },
      [kw.RPC]: (t, c) => {
        this.rpc_parser.parse_rpc(t, c);
      },
      [kw.ACTION]: (t, c) => {
        this.rpc_parser.parse_action(t, c);
      },
      [kw.ANYDATA]: (t, c) => {
        this.anydata_parser.parse_anydata(t, c);
      },
      [kw.ANYXML]: (t, c) => {
        this.anyxml_parser.parse_anyxml(t, c);
      },
      [kw.TYPEDEF]: (t, c) => {
        this.typedef_parser.parse_typedef(t, c);
      },
      [kw.GROUPING]: (t, c) => {
        this.grouping_parser.parse_grouping(t, c);
      },
      [kw.IMPORT]: (t, c) => {
        mod.parse_import_stmt(t, c);
      },
      [kw.INCLUDE]: (t, c) => {
        mod.parse_include_stmt(t, c);
      },
      [kw.REVISION]: (t, c) => {
        this.revision_parser.parse_revision(t, c);
      },
      [kw.DESCRIPTION]: (t, c) => {
        this.parse_description(t, c);
      },
      [kw.REFERENCE]: (t, c) => {
        this.parse_reference(t, c);
      },
      [kw.FEATURE]: (t, c) => {
        this.feature_parser.parse_feature_stmt(t, c);
      },
      [kw.IDENTITY]: (t, c) => {
        this.identity_parser.parse_identity(t, c);
      },
      [kw.EXTENSION]: (t, c) => {
        this.extension_parser.parse_extension_stmt(t, c);
      },
      [kw.AUGMENT]: (t, c) => {
        this.augment_parser.parse_augment(t, c);
      },
      [kw.DEVIATION]: (t, c) => {
        this.deviation_parser.parse_deviation(t, c);
      },
      [kw.YANG_VERSION]: (t, c) => {
        mod.parse_yang_version(t, c);
      },
      [kw.NAMESPACE]: (t, c) => {
        mod.parse_namespace(t, c);
      },
      [kw.PREFIX]: (t, c) => {
        mod.parse_prefix(t, c);
      },
      [kw.ORGANIZATION]: (t, c) => {
        mod.parse_organization(t, c);
      },
      [kw.CONTACT]: (t, c) => {
        mod.parse_contact(t, c);
      },
      [kw.TYPE]: (t, c) => {
        this.type_parser.parse_type(t, c);
      },
      [kw.UNITS]: (t, c) => {
        this.parse_units(t, c);
      },
      [kw.DEFAULT]: (t, c) => {
        this.parse_leaf_default(t, c);
      },
      [kw.STATUS]: (t, c) => {
        this.parse_status_ignored(t, c);
      },
      [kw.CONFIG]: (t, c) => {
        this.parse_config(t, c);
      },
      [kw.WHEN]: (t, c) => {
        this.when_parser.parse_when(t, c);
      },
      [kw.MUST]: (t, c) => {
        this.must_parser.parse_must(t, c);
      },
      [kw.IF_FEATURE]: (t, c) => {
        this.feature_parser.parse_if_feature_stmt(t, c);
      },
      [kw.PRESENCE]: (t, c) => {
        this.parse_presence(t, c);
      },
      [kw.USES]: (t, c) => {
        this.uses_parser.parse_uses(t, c);
      },
      [kw.REFINE]: (t, c) => {
        this.refine_parser.parse_refine(t, c);
      },
      [kw.CHOICE]: (t, c) => {
        this.choice_parser.parse_choice(t, c);
      },
      [kw.CASE]: (t, c) => {
        this.choice_parser.parse_case(t, c);
      },
      [kw.KEY]: (t, c) => {
        this.parse_list_key(t, c);
      },
      [kw.UNIQUE]: (t, c) => {
        this.parse_list_unique(t, c);
      },
      [kw.MIN_ELEMENTS]: (t, c) => {
        this.parse_min_elements(t, c);
      },
      [kw.MAX_ELEMENTS]: (t, c) => {
        this.parse_max_elements(t, c);
      },
      [kw.ORDERED_BY]: (t) => {
        this.parse_ordered_by(t);
      },
      [kw.MANDATORY]: (t, c) => {
        this.parse_leaf_mandatory(t, c);
      },
      [kw.INPUT]: (t, c) => {
        this.rpc_parser.parse_input(t, c);
      },
      [kw.OUTPUT]: (t, c) => {
        this.rpc_parser.parse_output(t, c);
      }
    };
    const importPrefix: DispatchFn = (tokens) => {
      tokens.consume(kw.PREFIX);
      const acc = this.importAcc;
      if (!acc) {
        tokens.syntaxError("internal: import prefix outside import block");
        return;
      }
      acc.localPrefix = this.parse_identifier_argument(tokens, "prefix");
      tokens.consume_if_type(YangTokenType.SEMICOLON);
    };
    const importRevision: DispatchFn = (tokens) => {
      const acc = this.importAcc;
      if (!acc) {
        tokens.syntaxError("internal: revision-date outside import block");
        return;
      }
      acc.revisionDate = this.revision_parser.parse_revision_date_statement(tokens);
    };
    const overrides: Record<string, Record<string, DispatchFn>> = {
      import: {
        [kw.PREFIX]: importPrefix,
        [kw.DESCRIPTION]: (t, c) => {
          this.parseDiscardedDescription(t, c);
        },
        [kw.REVISION_DATE]: importRevision
      },
      include: {
        [kw.PREFIX]: (t) => {
          mod.parse_prefix_value_stmt(t);
        },
        [kw.DESCRIPTION]: (t, c) => {
          this.parseDiscardedDescription(t, c);
        },
        [kw.REVISION_DATE]: (t) => {
          this.includeRevisionDate = this.revision_parser.parse_revision_date_statement(t);
        }
      },
      "belongs-to": {
        [kw.PREFIX]: (t) => {
          mod.parse_prefix_value_stmt(t);
        }
      },
      typedef: {
        [kw.DEFAULT]: (t, c) => {
          this.parse_typedef_default(t, c);
        }
      },
      choice: {
        [kw.MANDATORY]: (t, c) => {
          choice.parse_choice_mandatory(t, c);
        },
        [kw.DEFAULT]: (t, c) => {
          choice.parse_choice_default(t, c);
        }
      },
      refine: {
        [kw.MANDATORY]: (t, c) => {
          this.parse_leaf_mandatory(t, c);
        },
        [kw.DEFAULT]: (t, c) => {
          this.parse_leaf_default(t, c);
        }
      },
      identity: {
        [kw.BASE]: (t, c) => {
          this.identity_parser.parse_identity_base(t, c);
        }
      },
      "if-feature": {
        [kw.DESCRIPTION]: (t, c) => {
          this.parseDiscardedDescription(t, c);
        }
      },
      must: {
        [kw.ERROR_MESSAGE]: (t, c) => {
          this.must_parser.parse_must_error_message(t, c);
        },
        [kw.ERROR_APP_TAG]: (t, c) => {
          this.must_parser.parse_must_error_app_tag(t, c);
        }
      },
      extension: {
        [kw.ARGUMENT]: (t, c) => {
          this.extension_parser.parse_extension_argument_stmt(t, c);
        }
      },
      argument: {
        [kw.YIN_ELEMENT]: (t, c) => {
          this.extension_parser.parse_yin_element(t, c);
        }
      },
      deviation: {
        [kw.DEVIATE]: (t, c) => {
          this.deviation_parser.parse_deviate_substatement(t, c);
        }
      },
      pattern: {
        [kw.ERROR_MESSAGE]: (t, c) => {
          typ.parse_pattern_error_message(t, c);
        },
        [kw.ERROR_APP_TAG]: (t, c) => {
          typ.parse_pattern_error_app_tag(t, c);
        },
        [kw.MODIFIER]: (t, c) => {
          typ.parse_pattern_modifier(t, c);
        }
      },
      enum: {
        [kw.VALUE]: (t, c) => {
          typ.parse_enum_value(t, c);
        },
        [kw.STATUS]: (t, c) => {
          typ.parse_enum_status(t, c);
        }
      },
      bit: {
        [kw.POSITION]: (t, c) => {
          bits.parse_bit_position(t, c);
        }
      },
      length: {
        [kw.ERROR_MESSAGE]: (t, c) => {
          typ.parse_restriction_error_message(t, c);
        },
        [kw.ERROR_APP_TAG]: (t, c) => {
          typ.parse_restriction_error_app_tag(t, c);
        }
      },
      range: {
        [kw.ERROR_MESSAGE]: (t, c) => {
          typ.parse_restriction_error_message(t, c);
        },
        [kw.ERROR_APP_TAG]: (t, c) => {
          typ.parse_restriction_error_app_tag(t, c);
        }
      },
      type: {
        [kw.TYPE]: (t, c, typeStmt: YangTypeStmt) => {
          const nested = typ.parse_type(t, c);
          if (!(typeStmt instanceof YangUnionTypeStmt)) throw new YangSemanticError("nested type requires union");
          typeStmt.types.push(nested);
        },
        [kw.PATTERN]: (t, c, typeStmt: YangTypeStmt) => {
          typ.parse_type_pattern(t, c, typeStmt);
        },
        [kw.LENGTH]: (t, c, typeStmt: YangTypeStmt) => {
          typ.parse_type_length(t, c, typeStmt);
        },
        [kw.RANGE]: (t, c, typeStmt: YangTypeStmt) => {
          typ.parse_type_range(t, c, typeStmt);
        },
        [kw.FRACTION_DIGITS]: (t, c, typeStmt: YangTypeStmt) => {
          typ.parse_type_fraction_digits(t, c, typeStmt);
        },
        [kw.ENUM]: (t, c, typeStmt: YangTypeStmt) => {
          typ.parse_type_enum(t, c, typeStmt);
        },
        [kw.BIT]: (t, c, typeStmt: YangTypeStmt) => {
          bits.parse_type_bit(t, c, typeStmt);
        },
        [kw.PATH]: (t, c, typeStmt: YangTypeStmt) => {
          typ.parse_type_path(t, c, typeStmt);
        },
        [kw.REQUIRE_INSTANCE]: (t, c, typeStmt: YangTypeStmt) => {
          typ.parse_type_require_instance(t, c, typeStmt);
        },
        [kw.BASE]: (t, c, typeStmt: YangTypeStmt) => {
          typ.parse_type_base(t, c, typeStmt);
        },
        [kw.UNITS]: drop((t, c) => {
          this.parse_units(t, c);
        }),
        [kw.DESCRIPTION]: drop((t, c) => {
          this.parse_description(t, c);
        }),
        [kw.REFERENCE]: drop((t, c) => {
          this.parse_reference(t, c);
        })
      }
    };
    const runtime: Record<string, Record<string, DispatchFn>> = {};
    for (const [parent, spec] of Object.entries(DISPATCH_REGISTRY)) {
      const over = overrides[parent] ?? {};
      const table: Record<string, DispatchFn> = {};
      const missing: string[] = [];
      for (const keyword of spec.keywords) {
        const handler = over[keyword] ?? defaults[keyword];
        if (!handler) {
          missing.push(keyword);
        } else {
          table[keyword] = handler;
        }
      }
      const extra = Object.keys(over).filter((keyword) => !spec.keywords.has(keyword));
      if (extra.length > 0) {
        throw new Error(`handler override for keywords not allowed under ${parent}: ${extra.sort().join(", ")}`);
      }
      if (missing.length > 0) {
        throw new Error(`no handler for ${parent}: ${missing.sort().join(", ")}`);
      }
      runtime[parent] = table;
    }
    return runtime;
  }

  skip_unsupported_or_raise_unknown(tokens: TokenStream, context: string): boolean {
    const peek = tokens.peek();
    if (peek === kw.INPUT || peek === kw.OUTPUT) {
      tokens.syntaxError(
        `'${peek}' is only valid as a substatement of 'rpc' or 'action' (RFC 7950)`
      );
    }
    if (this.skip_unsupported_if_present(tokens, context)) {
      return true;
    }
    const bad = tokens.peek() ?? "";
    tokens.syntaxError(`Invalid or unknown statement in ${context}: '${bad}'`);
  }

  parse_prefixed_extension_statement_public(tokens: TokenStream, context: ParserContext): void {
    this.parse_prefixed_extension_statement(tokens, context);
  }

  /**
   * ``name`` or ``prefix:name``, quoted or unquoted (RFC 7950 identifier-ref-arg-str).
   * The argument is read by {@link parse_string_argument}, then checked.
   */
  consume_identifier_ref(tokens: TokenStream): { prefix?: string; name: string } {
    const raw = this.parse_string_argument(tokens);
    const colon = raw.indexOf(":");
    if (colon < 0) {
      if (!isIdentifierText(raw)) {
        tokens.syntaxError(`Expected an identifier, got '${raw}'`);
      }
      return { name: raw };
    }
    const prefix = raw.slice(0, colon);
    const name = raw.slice(colon + 1);
    if (prefix && name && !name.includes(":") && isIdentifierText(prefix) && isIdentifierText(name)) {
      return { prefix, name };
    }
    tokens.syntaxError(`Expected an identifier or prefix:identifier, got '${raw}'`);
  }

  /** Joined ``prefix:name`` form; prefer {@link consume_identifier_ref} for new code. */
  consume_qname_from_identifier(tokens: TokenStream): string {
    const ref = this.consume_identifier_ref(tokens);
    return ref.prefix ? `${ref.prefix}:${ref.name}` : ref.name;
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

  private parse_top_level_module(tokens: TokenStream, context: ParserContext): YangStatement {
    tokens.consume(kw.MODULE);
    const moduleName = this.parse_identifier_argument(tokens, "module");
    (context.module as Record<string, unknown>).name = moduleName;
    tokens.consume_type(YangTokenType.LBRACE);

    const moduleStatements: YangStatement[] = [];
    const scoped = context.with_dispatch("module", "module body");
    while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
      const stmt = this.parseStatement(tokens, scoped);
      if (stmt.keyword !== "include") {
        moduleStatements.push(stmt);
      }
      const included = this.drainIncludedStatements(context);
      if (included.length > 0) {
        moduleStatements.push(...included);
      }
    }
    tokens.consume_type(YangTokenType.RBRACE);

    return new YangStatement({      keyword: "module",
      name: moduleName,
      argument: moduleName,
      statements: moduleStatements
});
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
      xpath_prefixes?: Record<string, string>;
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
  }): YangStatement {
    const keyword = serializedKeywordFromAstStatement(stmt as object);

    const children = [
      ...this.serializeAstChildren(stmt.statements ?? []),
      ...this.serializeAstChildren(stmt.cases ?? [])
    ];

    const out: YangStatement = new YangStatement({      keyword,
      name: stmt.name,
      argument: stmt.name,
      statements: children
});

    if (keyword === "typedef" && (stmt as { scope?: string }).scope) {
      (out as unknown as { scope: string }).scope = (stmt as unknown as { scope: string }).scope;
    }
    if (stmt.type) {
      out.type = normalizeTypeShape(this.fromTypeShape(stmt.type));
    }
    if (stmt.mandatory !== undefined) {
      out.mandatory = stmt.mandatory;
    }
    if (stmt.default !== undefined) {
      out.default = stmt.default;
    }
    const config = (stmt as { config?: boolean }).config;
    if (typeof config === "boolean") {
      out.config = config;
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
    const unique = (stmt as { unique?: string[][] }).unique;
    if (Array.isArray(unique) && unique.length > 0) {
      out.unique = unique.map((paths) => [...paths]);
    }
    const minElements = (stmt as { min_elements?: number }).min_elements;
    if (typeof minElements === "number") {
      out.min_elements = minElements;
    }
    const maxElements = (stmt as { max_elements?: number }).max_elements;
    if (typeof maxElements === "number") {
      out.max_elements = maxElements;
    }
    if (stmt.description) {
      out.description = stmt.description;
    }
    const units = (stmt as { units?: string }).units;
    if (units) {
      out.units = units;
    }
    if (keyword === "container") {
      const groupings = (stmt as { groupings?: Record<string, { name?: string }> }).groupings;
      if (groupings && Object.keys(groupings).length > 0) {
        const local: Record<string, YangStatement> = {};
        for (const [gname, grouping] of Object.entries(groupings)) {
          local[gname] = this.fromAst(grouping as never);
        }
        out.local_groupings = local;
      }
    }
    const reference = (stmt as { reference?: string }).reference;
    if (reference) {
      out.reference = reference;
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
      const segs = (stmt as YangAugmentStmt).augment_path_segments;
      if (Array.isArray(segs) && segs.length > 0) {
        out.augment_path_segments = segs.map((s) =>
          s.prefix ? { prefix: s.prefix, name: s.name } : { name: s.name }
        );
      }
    }
    if (keyword === "extension-invocation") {
      out.keyword = stmt.name ?? "extension-invocation";
      out.argument = stmt.argument;
      out.prefix = stmt.prefix;
      out.resolved_module_name = stmt.resolved_module?.name;
      out.resolved_extension_name = stmt.resolved_extension?.name;
      if ((stmt.resolved_extension as { apply_callback?: unknown } | undefined)?.apply_callback) {
        (out as { has_apply_callback?: boolean }).has_apply_callback = true;
      }
    }
    if (stmt.when && typeof stmt.when.expression === "string") {
      out.when = {
        expression: stmt.when.expression,
        description: stmt.when.description ?? "",
        evaluate_with_parent_context: stmt.when.evaluate_with_parent_context ?? false,
        ...(stmt.when.xpath_prefixes ? { xpath_prefixes: stmt.when.xpath_prefixes } : {})
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
        if (typeof u.grouping_prefix === "string" && u.grouping_prefix.length > 0) {
          out.grouping_prefix = u.grouping_prefix;
        }
        out.argument = u.grouping_qname();
      }
      if (Array.isArray(u.refines) && u.refines.length > 0) {
        out.refines = u.refines.map((r) => this.serializeRefineStmt(r as YangRefineStmt));
      }
      if (Array.isArray(u.augmentations) && u.augmentations.length > 0) {
        out.augmentations = u.augmentations.map((aug) => {
          const serialized = this.fromAst(aug);
          serialized.path = aug.augment_path;
          return serialized;
        });
      }
    }
    const presence = (stmt as { presence?: string }).presence;
    if (typeof presence === "string" && presence.length > 0) {
      out.presence = presence;
    }

    return out;
  }

  private serializeRefineStmt(r: YangRefineStmt): YangStatement {
    const out: YangStatement = new YangStatement({      keyword: "refine",
      name: "refine",
      argument: r.target_path,
      refine_target_path: r.target_path,
      statements: []
});
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
    if (typeof r.refined_config === "boolean") {
      out.refined_config = r.refined_config;
    }
    if (Array.isArray(r.if_features) && r.if_features.length > 0) {
      out.if_features = [...r.if_features];
    }
    if (typeof r.description === "string" && r.description.length > 0) {
      out.description = r.description;
    }
    if (Array.isArray(r.must_statements) && r.must_statements.length > 0) {
      out.statements = r.must_statements.map((m) => this.fromMust(m));
    }
    return out;
  }

  private serializeAstChildren(children: unknown[]): YangStatement[] {
    const out: YangStatement[] = [];
    for (const child of children) {
      if (!child || typeof child !== "object") {
        continue;
      }
      out.push(this.fromAst(child as any));
    }
    return out;
  }

  private fromType(type_stmt: YangTypeStmt): YangStatement {
    const qname = formatIdentifierRef({ name: type_stmt.name, prefix: type_stmt.prefix });
    return new YangStatement({      keyword: "type",
      name: type_stmt.name,
      argument: qname,
      type: this.fromTypeShape(type_stmt),
      statements: []
});
  }

  private fromMust(must_stmt: YangMustStmt): YangStatement {
    return new YangStatement({      keyword: "must",
      name: must_stmt.expression,
      argument: must_stmt.expression,
      error_message: must_stmt.error_message,
      ...(must_stmt.error_app_tag ? { error_app_tag: must_stmt.error_app_tag } : {}),
      description: must_stmt.description,
      xpath_prefixes: must_stmt.xpath_prefixes,
      statements: []
});
  }

  private fromTypeShape(type_stmt: YangTypeStmt): TypeShape {
    const shape: TypeShape = { name: type_stmt.name };
    if (type_stmt.prefix !== undefined) shape.prefix = type_stmt.prefix;
    if (type_stmt.scope_module !== undefined) shape.scope_module = type_stmt.scope_module;
    if (type_stmt.context !== undefined) shape.context = type_stmt.context;
    if (type_stmt instanceof YangStringTypeStmt || type_stmt instanceof YangDerivedTypeStmt) {
      if (type_stmt.patterns?.length) shape.patterns = type_stmt.patterns.map((p) => ({
        pattern: p.pattern, invert_match: p.invert_match,
        ...(p.error_message !== undefined ? { error_message: p.error_message } : {}),
        ...(p.error_app_tag !== undefined ? { error_app_tag: p.error_app_tag } : {})
      }));
    }
    for (const kind of ["range", "length"] as const) {
      const restriction = kind === "range"
        ? (type_stmt instanceof YangNumericTypeStmt || type_stmt instanceof YangDerivedTypeStmt ? type_stmt.range_restriction : undefined)
        : (type_stmt instanceof YangBinaryTypeStmt || type_stmt instanceof YangDerivedTypeStmt ? type_stmt.length_restriction : undefined);
      if (restriction) {
        shape[kind] = restriction.expression;
        for (const key of ["error_message", "error_app_tag", "description", "reference"] as const) {
          if (restriction[key] !== undefined) (shape as Record<string, unknown>)[`${kind}_${key}`] = restriction[key];
        }
      }
    }
    if (type_stmt instanceof YangDecimalTypeStmt && type_stmt.fraction_digits !== undefined) shape.fraction_digits = type_stmt.fraction_digits;
    if (type_stmt instanceof YangEnumerationTypeStmt || type_stmt instanceof YangDerivedTypeStmt) {
      if (type_stmt.enums) shape.enums = [...type_stmt.enums];
    }
    if (type_stmt instanceof YangBitsTypeStmt || type_stmt instanceof YangDerivedTypeStmt) {
      if (type_stmt.bits) shape.bits = type_stmt.bits.map((b) => ({ name: b.name, position: b.position ?? 0 }));
    }
    if (type_stmt instanceof YangUnionTypeStmt) shape.types = type_stmt.types.map((member) => this.fromTypeShape(member));
    if (type_stmt instanceof YangIdentityrefTypeStmt) shape.identityref_bases = type_stmt.identityref_bases.map((base) => ({ ...base }));
    if (type_stmt instanceof YangInstanceIdentifierTypeStmt || type_stmt instanceof YangDerivedTypeStmt) {
      if (type_stmt.require_instance !== undefined) shape.require_instance = type_stmt.require_instance;
    }
    if (type_stmt instanceof YangLeafrefTypeStmt) {
      if (type_stmt.path !== undefined) shape.path = type_stmt.path;
      if (type_stmt.xpath_prefixes) shape.xpath_prefixes = type_stmt.xpath_prefixes;
    }
    return shape;
  }

  private extract_type_shape(typeStmt: YangStatement): TypeShape {
    const name = typeStmt.argument ?? "string";
    const shape: TypeShape = { name };
    for (const child of typeStmt.statements ?? []) {
      if (child.keyword === "pattern" && child.argument) {
        const patterns = shape.patterns ?? [];
        patterns.push({ pattern: child.argument, invert_match: false });
        shape.patterns = patterns;
      }
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

  parse_description(tokens: TokenStream, context: ParserContext): string {
    tokens.consume(kw.DESCRIPTION);
    const desc = this.parse_string_argument(tokens);
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
    return desc;
  }

  parse_optional_description(tokens: TokenStream, context: ParserContext): void {
    if (tokens.has_more() && tokens.peek() === kw.DESCRIPTION) {
      this.parse_description(tokens, context);
    }
  }

  parse_units(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.UNITS);
    const units = this.parse_string_argument(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    const parent = context.current_parent as { units?: string } | undefined;
    if (parent && "units" in parent) {
      parent.units = units;
    }
  }

  parse_reference(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.REFERENCE);
    const ref = this.parse_string_argument(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    const parent = context.current_parent;
    if (parent && typeof parent === "object" && "reference" in parent) {
      (parent as { reference?: string }).reference = ref;
    }
  }

  parse_reference_string_only(tokens: TokenStream, context: ParserContext): void {
    this.parse_reference(tokens, context);
  }

  parse_status_ignored(tokens: TokenStream, _context: ParserContext): void {
    this.parse_status_argument(tokens);
  }

  parse_config(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.CONFIG);
    const value = this.parse_boolean_argument(tokens, "config");
    const parent = context.current_parent;
    if (parent instanceof YangRefineStmt) {
      parent.refined_config = value;
    } else if (parent && typeof parent === "object" && "config" in parent) {
      (parent as { config?: boolean }).config = value;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_typedef_default(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.DEFAULT);
    const parent = context.current_parent;
    if (parent instanceof YangTypedefStmt) {
      parent.default = this.parse_default_value_tokens(tokens);
    }
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

    const imports = (module.import_prefixes as Record<string, YangModule> | undefined) ?? {};
    module.import_prefixes = imports;

    if (imports[localPrefix]) {
      const includedFrom = this.includingSubmoduleName;
      if (includedFrom) {
        const existingName = String((imports[localPrefix] as { name?: string }).name ?? "");
        if (existingName === moduleName) {
          return;
        }
        throw new YangSemanticError(
          `Import prefix '${localPrefix}' from include of '${includedFrom}' conflicts with existing import of '${existingName}'`
        );
      }
      throw new YangSemanticError(`Duplicate import prefix '${localPrefix}'`);
    }

    if (!this.importResolver) {
      throw new YangSemanticError("Import resolution is not configured for this parser instance");
    }
    imports[localPrefix] = this.importResolver(moduleName, localPrefix, revisionDate, context, tokens);
  }

  parse_ordered_by(tokens: TokenStream): void {
    tokens.consume(kw.ORDERED_BY);
    this.parse_keyword_argument(tokens, "ordered-by", ["user", "system"]);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_list_key(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.KEY);
    const value = this.parse_string_argument(tokens);
    const parent: any = context.current_parent;
    if (parent && "key" in parent) parent.key = value;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  /** `unique "<descendant-path> ..."` (RFC 7950 §7.8.3). */
  parse_list_unique(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.UNIQUE);
    const arg = this.parse_string_argument(tokens);
    const paths = arg
      .split(/\s+/)
      .filter(Boolean)
      .map((path) =>
        path
          .split("/")
          .filter(Boolean)
          .map((seg) => seg.slice(seg.indexOf(":") + 1))
          .join("/")
      );
    if (paths.length === 0) {
      tokens.syntaxError("unique requires at least one descendant path");
    }
    const parent: unknown = context.current_parent;
    if (parent instanceof YangListStmt) {
      parent.unique.push(paths);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_min_elements(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.MIN_ELEMENTS);
    const value = this.parse_integer_or_unbounded(tokens, "min-elements");
    const parent: any = context.current_parent;
    if (parent && "min_elements" in parent) parent.min_elements = value;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_max_elements(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.MAX_ELEMENTS);
    const value = this.parse_integer_or_unbounded(tokens, "max-elements");
    const parent: any = context.current_parent;
    if (parent && "max_elements" in parent) parent.max_elements = value;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_leaf_mandatory(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.MANDATORY);
    const value = this.parse_boolean_argument(tokens, "mandatory");
    const parent: unknown = context.current_parent;
    if (parent instanceof YangRefineStmt) {
      parent.refined_mandatory = value;
      tokens.consume_if_type(YangTokenType.SEMICOLON);
      return;
    }
    if (parent && typeof parent === "object" && "mandatory" in parent) {
      (parent as { mandatory?: boolean }).mandatory = value;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_leaf_default(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.DEFAULT);
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
    tokens.consume(kw.PRESENCE);
    const parent: any = context.current_parent;
    const value = this.parse_string_argument(tokens);
    if (parent && "presence" in parent) parent.presence = value;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_default_value_tokens(tokens: TokenStream): string {
    return this.parse_string_argument(tokens);
  }

  private parse_prefixed_extension_statement(tokens: TokenStream, context: ParserContext): YangStatement {
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
      this.parseBody(
        tokens,
        childContext,
        "extension-invocation",
        `extension invocation '${invocation.name}'`
      );
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
    if (tt === YangTokenType.LBRACE || tt === YangTokenType.SEMICOLON || tt === YangTokenType.RBRACE) {
      return undefined;
    }
    return this.parse_string_argument(tokens);
  }

  private resolve_prefixed_module(
    context: ParserContext,
    prefix: string
  ): YangModule | Record<string, unknown> | undefined {
    const module = context.module as Record<string, unknown>;
    const ownPrefix = String(module.prefix ?? "").replace(/^['"]|['"]$/g, "");
    if (prefix === ownPrefix) {
      return module;
    }
    const imports = module.import_prefixes as Record<string, YangModule> | undefined;
    return imports?.[prefix];
  }

  private resolve_extension_definition(
    resolvedModule: YangModule | Record<string, unknown>,
    extensionName: string
  ): YangExtensionStmt | undefined {
    const direct = (resolvedModule.extensions as Record<string, YangExtensionStmt> | undefined)?.[extensionName];
    if (direct) {
      return direct;
    }

    const statements = Array.isArray(resolvedModule.statements)
      ? (resolvedModule.statements as YangStatement[])
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
