import * as kw from "../keywords";
import { modulePrefixResolver, YangPatternSpec, YangTypeStmt, createTypeStmt, YangRestriction, YangStringTypeStmt, YangDerivedTypeStmt, YangBinaryTypeStmt, YangNumericTypeStmt, YangDecimalTypeStmt, YangEnumerationTypeStmt, YangIdentityrefTypeStmt, YangLeafrefTypeStmt, YangInstanceIdentifierTypeStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import { bindXPathPrefixes, parseXPathPath, xpathPrefixes } from "../../xpath/parser";
import type { StatementParsers } from "../statement-parsers";

export class TypeStatementParser {
  private patternBody: { errorMessage?: string; errorAppTag?: string; invert: boolean } | undefined;
  private restrictionBody:
    | { description: string; reference: string; errorMessage?: string; errorAppTag?: string }
    | undefined;

  constructor(private readonly parsers: StatementParsers) {}

  parse_type(tokens: TokenStream, context: ParserContext): YangTypeStmt {
    tokens.consume(kw.TYPE);
    let prefix: string | undefined;
    let name: string;
    if (tokens.peek_type() === YangTokenType.IDENTIFIER) {
      const ref = this.parsers.consume_identifier_ref(tokens);
      prefix = ref.prefix;
      name = ref.name;
    } else {
      name = tokens.consume().trim();
    }
    const type_stmt = createTypeStmt({ name, prefix, context: context.typedef_context });
    const writer = context.module as { name?: string; belongs_to_module?: string };
    const scope = writer.belongs_to_module || writer.name;
    if (scope) type_stmt.scope_module = scope;

    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(type_stmt);
      this.parsers.parseBody(tokens, child, "type", `type '${name}'`, type_stmt);
      tokens.consume_type(YangTokenType.RBRACE);
      if (type_stmt instanceof YangEnumerationTypeStmt && type_stmt.enums.length === 0) {
        tokens.syntaxError("enumeration type must contain at least one enum statement");
      }
    }

    const parent: any = context.current_parent;
    if (parent && "type" in parent && !parent.type) {
      parent.type = type_stmt;
    }

    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return type_stmt;
  }

  parse_type_base(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    if (!(type_stmt instanceof YangIdentityrefTypeStmt)) tokens.syntaxError("base requires an identityref type");
    tokens.consume(kw.BASE);
    type_stmt.identityref_bases.push(this.parsers.consume_identifier_ref(tokens));
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_pattern(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    if (!(type_stmt instanceof YangStringTypeStmt || type_stmt instanceof YangDerivedTypeStmt)) tokens.syntaxError("pattern requires a string or derived type");
    tokens.consume(kw.PATTERN);
    const pattern = this.parsers.parse_string_concatenation(tokens);
    let invertMatch = false;
    let patternErrorMessage: string | undefined;
    let patternErrorAppTag: string | undefined;
    this.patternBody = { invert: false };
    try {
      if (tokens.consume_if_type(YangTokenType.LBRACE)) {
        this.parsers.parseBody(tokens, _context, "pattern", "pattern");
        tokens.consume_type(YangTokenType.RBRACE);
      }
      invertMatch = this.patternBody.invert;
      patternErrorMessage = this.patternBody.errorMessage;
      patternErrorAppTag = this.patternBody.errorAppTag;
    } finally {
      this.patternBody = undefined;
    }
    (type_stmt.patterns ??= []).push(
      new YangPatternSpec({
        pattern,
        invert_match: invertMatch,
        error_message: patternErrorMessage,
        error_app_tag: patternErrorAppTag
      })
    );
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_length(tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt): void {
    if (!(type_stmt instanceof YangBinaryTypeStmt || type_stmt instanceof YangDerivedTypeStmt)) tokens.syntaxError("length requires a string, binary or derived type");
    tokens.consume(kw.LENGTH);
    const expression = this.parsers.parse_string_argument(tokens);
    const meta = this.parseRestrictionBody(tokens, context, "length");
    type_stmt.length_restriction = new YangRestriction(expression, {
      error_message: meta.errorMessage, error_app_tag: meta.errorAppTag,
      description: meta.description, reference: meta.reference
    });
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_range(tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt): void {
    if (!(type_stmt instanceof YangNumericTypeStmt || type_stmt instanceof YangDerivedTypeStmt)) tokens.syntaxError("range requires a numeric or derived type");
    tokens.consume(kw.RANGE);
    const expression = this.parsers.parse_string_argument(tokens);
    const meta = this.parseRestrictionBody(tokens, context, "range");
    type_stmt.range_restriction = new YangRestriction(expression, {
      error_message: meta.errorMessage, error_app_tag: meta.errorAppTag,
      description: meta.description, reference: meta.reference
    });
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  private parseRestrictionBody(
    tokens: TokenStream,
    context: ParserContext,
    parent: string
  ): { description: string; reference: string; errorMessage?: string; errorAppTag?: string } {
    const holder = { description: "", reference: "", errorMessage: undefined as string | undefined, errorAppTag: undefined as string | undefined };
    if (!tokens.consume_if_type(YangTokenType.LBRACE)) {
      return holder;
    }
    const body = context.push_parent(holder);
    this.restrictionBody = holder;
    try {
      this.parsers.parseBody(tokens, body, parent, parent);
    } finally {
      this.restrictionBody = undefined;
    }
    tokens.consume_type(YangTokenType.RBRACE);
    return holder;
  }

  parse_restriction_error_message(tokens: TokenStream, _context: ParserContext): void {
    tokens.consume(kw.ERROR_MESSAGE);
    this.restrictionBody!.errorMessage = this.parsers.parse_string_concatenation(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_restriction_error_app_tag(tokens: TokenStream, _context: ParserContext): void {
    tokens.consume(kw.ERROR_APP_TAG);
    this.restrictionBody!.errorAppTag = this.parsers.parse_string_concatenation(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_fraction_digits(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    if (!(type_stmt instanceof YangDecimalTypeStmt)) tokens.syntaxError("fraction-digits requires decimal64");
    tokens.consume(kw.FRACTION_DIGITS);
    type_stmt.fraction_digits = Number.parseInt(tokens.consume_type(YangTokenType.INTEGER), 10);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_enum(tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt): void {
    if (!(type_stmt instanceof YangEnumerationTypeStmt || type_stmt instanceof YangDerivedTypeStmt)) tokens.syntaxError("enum requires an enumeration or derived type");
    tokens.consume(kw.ENUM);
    // One argument: ``100GE`` lexes as INTEGER + IDENTIFIER (RFC 7950 §9.6.4).
    const enumName = this.parsers.parse_string_argument(tokens);
    (type_stmt.enums ??= []).push(enumName);
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      this.parsers.parseBody(tokens, context, "enum", `enum '${enumName}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_path(tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt): void {
    if (!(type_stmt instanceof YangLeafrefTypeStmt)) tokens.syntaxError("path requires leafref");
    tokens.consume(kw.PATH);
    const path = this.parsers.parse_string_argument(tokens);
    const ast = parseXPathPath(path);
    const used = xpathPrefixes(ast);
    if (used.size > 0) {
      const resolve = modulePrefixResolver(context.module);
      bindXPathPrefixes(ast, resolve, path);
      type_stmt.xpath_prefixes = Object.fromEntries([...used].map((prefix) => [prefix, resolve(prefix) as string]));
    }
    type_stmt.path = ast as YangLeafrefTypeStmt["path"];
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_require_instance(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    if (!(type_stmt instanceof YangInstanceIdentifierTypeStmt || type_stmt instanceof YangDerivedTypeStmt)) tokens.syntaxError("require-instance requires a reference type");
    tokens.consume(kw.REQUIRE_INSTANCE);
    type_stmt.require_instance = this.parsers.parse_boolean_argument(tokens, "require-instance");
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_pattern_error_message(tokens: TokenStream, _context: ParserContext): void {
    tokens.consume(kw.ERROR_MESSAGE);
    this.patternBody!.errorMessage = this.parsers.parse_string_concatenation(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_pattern_error_app_tag(tokens: TokenStream, _context: ParserContext): void {
    tokens.consume(kw.ERROR_APP_TAG);
    this.patternBody!.errorAppTag = this.parsers.parse_string_concatenation(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_pattern_modifier(tokens: TokenStream, _context: ParserContext): void {
    tokens.consume(kw.MODIFIER);
    this.patternBody!.invert = tokens.consume() === "invert-match";
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_enum_value(tokens: TokenStream, _context: ParserContext): void {
    tokens.consume(kw.VALUE);
    const raw = this.parsers.parse_string_argument(tokens);
    if (!/^[+-]?\d+$/.test(raw)) {
      tokens.syntaxError(`value argument must be an integer, got '${raw}'`);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_enum_status(tokens: TokenStream, _context: ParserContext): void {
    tokens.consume(kw.STATUS);
    tokens.consume_type(YangTokenType.IDENTIFIER);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
}
