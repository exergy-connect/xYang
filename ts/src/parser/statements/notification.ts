import * as kw from "../keywords";
import { YangNotificationStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

/** Parser for ``notification`` statements (RFC 7950 §7.16). */
export class NotificationStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_notification(tokens: TokenStream, context: ParserContext): YangNotificationStmt {
    tokens.consume(kw.NOTIFICATION);
    const name = tokens.consume();
    const stmt = new YangNotificationStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
}
