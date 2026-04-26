import * as kw from "../keywords";
import { YangGroupingStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class GroupingStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_grouping(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.GROUPING);
    const name = tokens.consume();
    const stmt = new YangGroupingStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    (context.module as any).groupings[name] = stmt;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
}
