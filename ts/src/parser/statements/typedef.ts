import * as kw from "../keywords";
import { YangTypedefStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import { withMetadataSubstatements } from "../metadata-substatements";
import type { StatementParsers } from "../statement-parsers";

export class TypedefStatementParser {
  private readonly typedefBodyDispatch: Record<string, (tokens: TokenStream, context: ParserContext) => void>;

  constructor(private readonly parsers: StatementParsers) {
    this.typedefBodyDispatch = withMetadataSubstatements(this.parsers, {
      [kw.TYPE]: (tokens, context) => {
        this.parsers.type_parser.parse_type(tokens, context);
      },
      [kw.DEFAULT]: (tokens, context) => {
        this.parsers.parse_typedef_default(tokens, context);
      }
    });
  }

  parse_typedef(tokens: TokenStream, context: ParserContext): YangTypedefStmt {
    tokens.consume(kw.TYPEDEF);
    const name = tokens.consume_type(YangTokenType.IDENTIFIER);
    const stmt = new YangTypedefStmt({ name });
    const unsupportedCtx = `typedef '${name}'`;
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        const handler = this.parsers.substatement_handler(tokens, this.typedefBodyDispatch);
        if (handler) {
          handler(tokens, child);
        } else if (!this.parsers.skip_unsupported_or_raise_unknown(tokens, unsupportedCtx)) {
          /* unreachable */
        }
      }
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
