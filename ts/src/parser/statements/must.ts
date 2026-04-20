import { YangMustStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class MustStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_must(tokens: TokenStream, context: ParserContext): YangMustStmt {
    tokens.consume_type(YangTokenType.MUST);
    const expression = this.parsers.parse_string_concatenation(tokens);
    const stmt = new YangMustStmt({ expression });

    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        if (tokens.peek_type() === YangTokenType.ERROR_MESSAGE) {
          this.parse_must_error_message(tokens, child);
        } else {
          this.parsers.parseStatement(tokens, child);
        }
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }

    const parent = context.current_parent as { must_statements?: YangMustStmt[] };
    if (Array.isArray(parent?.must_statements)) {
      parent.must_statements.push(stmt);
    }

    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }

  parse_must_error_message(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.ERROR_MESSAGE);
    const parent = context.current_parent as YangMustStmt;
    if (parent instanceof YangMustStmt) {
      parent.error_message = tokens.consume_type(YangTokenType.STRING);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
}
