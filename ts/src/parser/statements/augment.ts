import * as kw from "../keywords";
import { YangAugmentStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class AugmentStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_augment(tokens: TokenStream, context: ParserContext): YangAugmentStmt {
    tokens.consume(kw.AUGMENT);
    const augment_path = this.parsers.parse_string_concatenation(tokens);
    const stmt = new YangAugmentStmt({ name: "augment", augment_path });
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
