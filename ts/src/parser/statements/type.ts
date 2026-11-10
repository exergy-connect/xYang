import * as kw from "../keywords";
import { YangPatternSpec, YangTypeStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import { parseXPathPath } from "../../xpath/parser";
import type { StatementParsers } from "../statement-parsers";

export class TypeStatementParser {
  private patternBody: { errorMessage?: string; errorAppTag?: string; invert: boolean } | undefined;

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
    const type_stmt = new YangTypeStmt({ name, prefix });

    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(type_stmt);
      this.parsers.parseBody(tokens, child, "type", `type '${name}'`, type_stmt);
      tokens.consume_type(YangTokenType.RBRACE);
      if (type_stmt.name === kw.ENUMERATION && type_stmt.enums.length === 0) {
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
    tokens.consume(kw.BASE);
    type_stmt.identityref_bases.push(this.parsers.consume_identifier_ref(tokens));
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_pattern(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
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
    type_stmt.patterns.push(
      new YangPatternSpec({
        pattern,
        invert_match: invertMatch,
        error_message: patternErrorMessage,
        error_app_tag: patternErrorAppTag
      })
    );
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_length(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    // One string: ``1..127`` or ``"1..127"``.
    tokens.consume(kw.LENGTH);
    type_stmt.length = this.parsers.parse_string_argument(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_range(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume(kw.RANGE);
    type_stmt.range = this.parsers.parse_string_argument(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_fraction_digits(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume(kw.FRACTION_DIGITS);
    type_stmt.fraction_digits = Number.parseInt(tokens.consume_type(YangTokenType.INTEGER), 10);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_enum(tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume(kw.ENUM);
    const enumName = tokens.consume();
    type_stmt.enums.push(enumName);
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      this.parsers.parseBody(tokens, context, "enum", `enum '${enumName}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_path(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume(kw.PATH);
    const path = this.parsers.parse_string_argument(tokens);
    type_stmt.path = parseXPathPath(path);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_require_instance(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume(kw.REQUIRE_INSTANCE);
    const [, tt] = tokens.consume_oneof([kw.TRUE, kw.FALSE]);
    type_stmt.require_instance = tt === kw.TRUE;
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
