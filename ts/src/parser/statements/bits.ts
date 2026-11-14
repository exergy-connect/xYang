import * as kw from "../keywords";
import { YangBitStmt, YangTypeStmt, YangBitsTypeStmt, YangDerivedTypeStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class BitsStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_type_bit(tokens: TokenStream, context: ParserContext, type_stmt: YangTypeStmt): void {
    if (!(type_stmt instanceof YangBitsTypeStmt || type_stmt instanceof YangDerivedTypeStmt)) tokens.syntaxError("bit requires a bits or derived type");
    const bits = type_stmt.bits ??= [];
    tokens.consume(kw.BIT);
    const name = this.parsers.parse_identifier_argument(tokens, "bit");
    const bit = new YangBitStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(bit);
      this.parsers.parseBody(tokens, child, "bit", "bit");
      tokens.consume_type(YangTokenType.RBRACE);
    }
    if (bits.some((existing) => existing.name === name)) {
      tokens.syntaxError(`Duplicate bit name '${name}' in bits type`);
    }
    bits.push(bit);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_bit_position(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.POSITION);
    const parent = context.current_parent;
    if (parent instanceof YangBitStmt && parent.position !== undefined) {
      tokens.syntaxError("Duplicate position in bit statement");
    }
    const position = this.parsers.parse_integer_argument(tokens, "position");
    if (parent instanceof YangBitStmt) {
      parent.position = position;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  finalize_bits_type(type_stmt: YangBitsTypeStmt): void {
    let max = -1;
    for (const bit of type_stmt.bits) {
      if (bit.position === undefined) {
        bit.position = max + 1;
      }
      max = Math.max(max, bit.position);
    }
  }
}
