import * as kw from "../keywords";
import { YangTypedefStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class TypedefStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_typedef(tokens: TokenStream, context: ParserContext): YangTypedefStmt {
    tokens.consume(kw.TYPEDEF);
    const name = tokens.consume_type(YangTokenType.IDENTIFIER);
    const stmt = new YangTypedefStmt({ name });
    const unsupportedCtx = `typedef '${name}'`;
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child, "typedef", unsupportedCtx);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    (context.module as any).typedefs[name] = stmt;
    // Keep nested typedefs on the parent (grouping/container/…) so ``uses``
    // expansion can re-register them on the importing module (RFC 7950 §7.13).
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
}
