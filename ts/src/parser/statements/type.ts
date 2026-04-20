import { YangTypeStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import { parseXPath } from "../../xpath/parser";
import type { StatementParsers } from "../statement-parsers";

export class TypeStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_type(tokens: TokenStream, context: ParserContext): YangTypeStmt {
    tokens.consume_type(YangTokenType.TYPE);
    const name = tokens.peek_type() === YangTokenType.IDENTIFIER
      ? this.parsers.consume_qname_from_identifier(tokens)
      : tokens.consume();
    const type_stmt = new YangTypeStmt({ name });

    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(type_stmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        const tt = tokens.peek_type();
        if (tt === YangTokenType.PATTERN) {
          this.parse_type_pattern(tokens, child, type_stmt);
        } else if (tt === YangTokenType.LENGTH) {
          this.parse_type_length(tokens, child, type_stmt);
        } else if (tt === YangTokenType.RANGE) {
          this.parse_type_range(tokens, child, type_stmt);
        } else if (tt === YangTokenType.FRACTION_DIGITS) {
          this.parse_type_fraction_digits(tokens, child, type_stmt);
        } else if (tt === YangTokenType.ENUM) {
          this.parse_type_enum(tokens, child, type_stmt);
        } else if (tt === YangTokenType.BIT) {
          this.parsers.bits_parser.parse_type_bit(tokens, child, type_stmt);
        } else if (tt === YangTokenType.PATH) {
          this.parse_type_path(tokens, child, type_stmt);
        } else if (tt === YangTokenType.REQUIRE_INSTANCE) {
          this.parse_type_require_instance(tokens, child, type_stmt);
        } else if (tt === YangTokenType.BASE) {
          this.parse_type_base(tokens, child, type_stmt);
        } else if (tt === YangTokenType.TYPE) {
          const nested = this.parse_type(tokens, child);
          type_stmt.types.push(nested);
        } else {
          this.parsers.parseStatement(tokens, child);
        }
      }
      tokens.consume_type(YangTokenType.RBRACE);
      if (type_stmt.name === YangTokenType.ENUMERATION && type_stmt.enums.length === 0) {
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
    tokens.consume_type(YangTokenType.BASE);
    type_stmt.identityref_bases.push(this.parsers.consume_qname_from_identifier(tokens));
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_pattern(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume_type(YangTokenType.PATTERN);
    type_stmt.pattern = tokens.consume_type(YangTokenType.STRING);
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        const tt = tokens.peek_type();
        if (tt === YangTokenType.ERROR_MESSAGE) {
          tokens.consume_type(YangTokenType.ERROR_MESSAGE);
          type_stmt.pattern_error_message = tokens.consume_type(YangTokenType.STRING);
          tokens.consume_if_type(YangTokenType.SEMICOLON);
        } else if (tt === YangTokenType.ERROR_APP_TAG) {
          tokens.consume_type(YangTokenType.ERROR_APP_TAG);
          type_stmt.pattern_error_app_tag = tokens.consume_type(YangTokenType.STRING);
          tokens.consume_if_type(YangTokenType.SEMICOLON);
        } else {
          tokens.consume();
        }
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_length(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume_type(YangTokenType.LENGTH);
    type_stmt.length = tokens.consume();
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_range(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume_type(YangTokenType.RANGE);
    type_stmt.range = tokens.consume_type(YangTokenType.STRING);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_fraction_digits(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume_type(YangTokenType.FRACTION_DIGITS);
    type_stmt.fraction_digits = Number.parseInt(tokens.consume_type(YangTokenType.INTEGER), 10);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_enum(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume_type(YangTokenType.ENUM);
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
    tokens.consume_type(YangTokenType.PATH);
    const path = tokens.consume_type(YangTokenType.STRING);
    type_stmt.path = parseXPath(path);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_type_require_instance(tokens: TokenStream, _context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume_type(YangTokenType.REQUIRE_INSTANCE);
    const [, tt] = tokens.consume_oneof([YangTokenType.TRUE, YangTokenType.FALSE]);
    type_stmt.require_instance = tt === YangTokenType.TRUE;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
}
