import * as kw from "../keywords";
import { YangListStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class ListStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_list(tokens: TokenStream, context: ParserContext): YangListStmt {
    tokens.consume(kw.LIST);
    const name = this.parsers.parse_identifier_argument(tokens, "list");
    const stmt = new YangListStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child, "list", `list '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
}
