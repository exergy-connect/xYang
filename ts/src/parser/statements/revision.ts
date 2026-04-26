import * as kw from "../keywords";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class RevisionStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_revision(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.REVISION);
    let date = "";
    if (tokens.peek_type() === YangTokenType.STRING) {
      date = tokens.consume_type(YangTokenType.STRING);
    } else {
      while (tokens.has_more() && ![YangTokenType.LBRACE, YangTokenType.SEMICOLON].includes(tokens.peek_type())) {
        date += tokens.consume();
      }
    }
    const rev = { date, description: "" };
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        if (tokens.peek() === kw.DESCRIPTION) {
          tokens.consume(kw.DESCRIPTION);
          rev.description = tokens.consume_type(YangTokenType.STRING);
          tokens.consume_if_type(YangTokenType.SEMICOLON);
        } else {
          this.parsers.parseStatement(tokens, context);
        }
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    ((context.module as any).revisions ??= []).push(rev);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_revision_date_statement(tokens: TokenStream): string {
    tokens.consume(kw.REVISION_DATE);
    let date = "";
    if (tokens.peek_type() === YangTokenType.STRING) {
      date = tokens.consume_type(YangTokenType.STRING);
    } else {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.SEMICOLON) {
        date += tokens.consume();
      }
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return date;
  }
}
