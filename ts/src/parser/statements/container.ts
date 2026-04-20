import { YangContainerStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class ContainerStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_container(tokens: TokenStream, context: ParserContext): YangContainerStmt {
    tokens.consume_type(YangTokenType.CONTAINER);
    const name = tokens.consume();
    const stmt = new YangContainerStmt({ name });
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
