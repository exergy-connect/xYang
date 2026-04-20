import { YangLeafListStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class LeafListStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_leaf_list(tokens: TokenStream, context: ParserContext): YangLeafListStmt {
    tokens.consume_type(YangTokenType.LEAF_LIST);
    const name = tokens.consume();
    const stmt = new YangLeafListStmt({ name });
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
