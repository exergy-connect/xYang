import * as kw from "../keywords";
import { YangUsesStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class UsesStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_uses(tokens: TokenStream, context: ParserContext): YangUsesStmt {
    tokens.consume(kw.USES);
    const grouping_name = tokens.peek_type() === YangTokenType.IDENTIFIER
      ? this.parsers.consume_qname_from_identifier(tokens)
      : tokens.consume();
    const stmt = new YangUsesStmt({ name: "uses", grouping_name });
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
