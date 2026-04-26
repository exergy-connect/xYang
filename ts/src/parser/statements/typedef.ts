import * as kw from "../keywords";
import { YangTypedefStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class TypedefStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_typedef(tokens: TokenStream, context: ParserContext): YangTypedefStmt {
    tokens.consume(kw.TYPEDEF);
    const name = tokens.consume_type(YangTokenType.IDENTIFIER);
    const stmt = new YangTypedefStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    (context.module as any).typedefs[name] = stmt;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
}
