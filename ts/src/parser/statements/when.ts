import * as kw from "../keywords";
import { YangStatementWithWhen, YangWhenStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class WhenStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_when(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.WHEN);
    const expression = this.parsers.parse_string_concatenation(tokens);
    const whenStmt = new YangWhenStmt({ expression });

    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(whenStmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }

    if (context.current_parent instanceof YangStatementWithWhen) {
      context.current_parent.when = whenStmt;
    }

    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
}
