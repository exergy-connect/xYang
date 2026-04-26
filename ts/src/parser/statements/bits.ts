import * as kw from "../keywords";
import { YangBitStmt, YangTypeStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class BitsStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_type_bit(tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt): void {
    tokens.consume(kw.BIT);
    const name = tokens.consume();
    let position: number | undefined;
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        if (tokens.peek() === kw.POSITION) {
          tokens.consume(kw.POSITION);
          position = Number.parseInt(tokens.consume_type(YangTokenType.INTEGER), 10);
          tokens.consume_if_type(YangTokenType.SEMICOLON);
        } else {
          this.parsers.parseStatement(tokens, context);
        }
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    type_stmt.bits.push(new YangBitStmt({ name, position }));
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  finalize_bits_type(type_stmt: YangTypeStmt): void {
    let max = -1;
    for (const bit of type_stmt.bits) {
      if (bit.position === undefined) {
        bit.position = max + 1;
      }
      max = Math.max(max, bit.position);
    }
  }
}
