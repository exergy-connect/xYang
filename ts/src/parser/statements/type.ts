import * as kw from "../keywords";
import { YangPatternSpec, YangTypeStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import { parseXPath } from "../../xpath/parser";
import type { StatementParsers } from "../statement-parsers";

export class TypeStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_type(tokens: TokenStream, context: ParserContext): YangTypeStmt {
    tokens.consume(kw.TYPE);
    const name = tokens.peek_type() === YangTokenType.IDENTIFIER
      ? this.parsers.consume_qname_from_identifier(tokens)
      : tokens.consume();
    const type_stmt = new YangTypeStmt({ name });

    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(type_stmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        const tt = this.parsers.dispatch_key(tokens);
        if (tt === kw.PATTERN) {
          this.parse_type_pattern(tokens, child, type_stmt);
        } else if (tt === kw.LENGTH) {
          this.parse_type_length(tokens, child, type_stmt);
        } else if (tt === kw.RANGE) {
          this.parse_type_range(tokens, child, type_stmt);
        } else if (tt === kw.FRACTION_DIGITS) {
          this.parse_type_fraction_digits(tokens, child, type_stmt);
        } else if (tt === kw.ENUM) {
          this.parse_type_enum(tokens, child, type_stmt);
        } else if (tt === kw.BIT) {
          this.parsers.bits_parser.parse_type_bit(tokens, child, type_stmt);
        } else if (tt === kw.PATH) {
          this.parse_type_path(tokens, child, type_stmt);
        } else if (tt === kw.REQUIRE_INSTANCE) {
          this.parse_type_require_instance(tokens, child, type_stmt);
        } else if (tt === kw.BASE) {
          this.parse_type_base(tokens, child, type_stmt);
        } else if (tt === kw.TYPE) {
          const nested = this.parse_type(tokens, child);
          type_stmt.types.push(nested);
        } else {
          this.parsers.parseStatement(tokens, child);
        }
      }
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
    type_stmt.identityref_bases.push(this.parsers.consume_qname_from_identifier(tokens));
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_pattern(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume(kw.PATTERN);
    const pattern = tokens.consume_type(YangTokenType.STRING);
    let invertMatch = false;
    let patternErrorMessage: string | undefined;
    let patternErrorAppTag: string | undefined;
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        const tt = this.parsers.dispatch_key(tokens);
        if (tt === kw.ERROR_MESSAGE) {
          tokens.consume(kw.ERROR_MESSAGE);
          patternErrorMessage = tokens.consume_type(YangTokenType.STRING);
          tokens.consume_if_type(YangTokenType.SEMICOLON);
        } else if (tt === kw.ERROR_APP_TAG) {
          tokens.consume(kw.ERROR_APP_TAG);
          patternErrorAppTag = tokens.consume_type(YangTokenType.STRING);
          tokens.consume_if_type(YangTokenType.SEMICOLON);
        } else if (tt === kw.MODIFIER) {
          tokens.consume(kw.MODIFIER);
          invertMatch = tokens.consume() === "invert-match";
          tokens.consume_if_type(YangTokenType.SEMICOLON);
        } else {
          this.parsers.parseStatement(tokens, _context);
        }
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    type_stmt.patterns.push(
      new YangPatternSpec({
        pattern,
        invert_match: invertMatch,
        error_message: patternErrorMessage,
        error_app_tag: patternErrorAppTag
      })
    );
    // Backward compatible mirrors: last pattern entry.
    type_stmt.pattern = pattern;
    type_stmt.pattern_error_message = patternErrorMessage;
    type_stmt.pattern_error_app_tag = patternErrorAppTag;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_length(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume(kw.LENGTH);
    type_stmt.length = tokens.consume();
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_range(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume(kw.RANGE);
    type_stmt.range = tokens.consume_type(YangTokenType.STRING);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_fraction_digits(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume(kw.FRACTION_DIGITS);
    type_stmt.fraction_digits = Number.parseInt(tokens.consume_type(YangTokenType.INTEGER), 10);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_enum(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume(kw.ENUM);
    type_stmt.enums.push(tokens.consume());
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        tokens.consume();
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_path(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume(kw.PATH);
    const path = tokens.consume_type(YangTokenType.STRING);
    type_stmt.path = parseXPath(path);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_require_instance(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume(kw.REQUIRE_INSTANCE);
    const [, tt] = tokens.consume_oneof([kw.TRUE, kw.FALSE]);
    type_stmt.require_instance = tt === kw.TRUE;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
}
