import * as kw from "../keywords";
import { YangAnyxmlStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class AnyxmlStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_anyxml(tokens: TokenStream, context: ParserContext): YangAnyxmlStmt {
    tokens.consume(kw.ANYXML);
    const name = tokens.consume();
    const stmt = new YangAnyxmlStmt({ name });
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
