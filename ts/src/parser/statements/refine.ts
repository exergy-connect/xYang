import * as kw from "../keywords";
import { YangRefineStmt, YangUsesStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class RefineStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_refine(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.REFINE);
    const target_path = this.parsers.parse_string_argument(tokens);
    const stmt = new YangRefineStmt({ name: "refine", target_path });

    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child, "refine", `refine '${target_path}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }

    if (context.current_parent instanceof YangUsesStmt) {
      context.current_parent.refines.push(stmt);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
}
