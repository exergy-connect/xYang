import { registerTypedef, type ScopedTypedef } from "../../typedef-scope";
import * as kw from "../keywords";
import { YangTypedefStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class TypedefStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_typedef(tokens: TokenStream, context: ParserContext): YangTypedefStmt {
    tokens.consume(kw.TYPEDEF);
    const name = this.parsers.parse_identifier_argument(tokens, "typedef");
    const stmt = new YangTypedefStmt({ name, scope: context.typedef_context || undefined });
    const unsupportedCtx = `typedef '${name}'`;
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child, "typedef", unsupportedCtx);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    const typedefs = (context.module as { typedefs: Record<string, ScopedTypedef> }).typedefs;
    const key = (stmt.scope ? stmt.scope + "/" : "") + name;
    if (this.parsers.includingSubmoduleName && key in typedefs) {
      // Include guards distinguish a repeated include from a different declaration.
      typedefs[key] = stmt as unknown as ScopedTypedef;
    } else {
      registerTypedef(typedefs, stmt as unknown as ScopedTypedef);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
}
