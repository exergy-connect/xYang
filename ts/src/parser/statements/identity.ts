import { YangIdentityStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class IdentityStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_identity(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.IDENTITY);
    const name = tokens.consume_type(YangTokenType.IDENTIFIER);
    const stmt = new YangIdentityStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        if (tokens.peek_type() === YangTokenType.BASE) {
          this.parse_identity_base(tokens, child);
        } else {
          this.parsers.parseStatement(tokens, child);
        }
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    (context.module as any).identities[name] = stmt;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_identity_base(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.BASE);
    const base = this.parsers.consume_qname_from_identifier(tokens);
    const parent = context.current_parent as YangIdentityStmt;
    if (parent instanceof YangIdentityStmt) {
      parent.bases.push(base);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
}
