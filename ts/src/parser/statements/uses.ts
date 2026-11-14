import * as kw from "../keywords";
import { YangUsesStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class UsesStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_uses(tokens: TokenStream, context: ParserContext): YangUsesStmt {
    tokens.consume(kw.USES);
    const ref = this.parsers.consume_identifier_ref(tokens);
    const grouping_prefix = ref.prefix;
    const grouping_name = ref.name;
    const stmt = new YangUsesStmt({
      name: "uses",
      grouping_name,
      grouping_prefix
    });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child, "uses", `uses '${grouping_name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
}
