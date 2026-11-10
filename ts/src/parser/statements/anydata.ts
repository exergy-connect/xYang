import * as kw from "../keywords";
import { YangAnydataStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class AnydataStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_anydata(tokens: TokenStream, context: ParserContext): YangAnydataStmt {
    tokens.consume(kw.ANYDATA);
    const name = tokens.consume();
    const stmt = new YangAnydataStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child, "anydata", `anydata '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
}
