import { YangRefineStmt, YangUsesStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class RefineStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_refine(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.REFINE);
    const parts = [tokens.consume()];
    while (tokens.has_more() && tokens.peek_type() === YangTokenType.SLASH) {
      tokens.consume_type(YangTokenType.SLASH);
      parts.push(tokens.consume());
    }
    const target_path = parts.join("/");
    const stmt = new YangRefineStmt({ name: "refine", target_path });

    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }

    if (context.current_parent instanceof YangUsesStmt) {
      context.current_parent.refines.push(stmt);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
}
