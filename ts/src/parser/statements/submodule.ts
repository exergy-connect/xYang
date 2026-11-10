import * as kw from "../keywords";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";
import { ModuleStatementParser } from "./module";

/** Header and linkage statements are applied for their side effects, not copied as schema nodes. */
const INCLUDED_STATEMENT_SKIP = new Set([
  "yang-version",
  "namespace",
  "prefix",
  "organization",
  "contact",
  "description",
  "reference",
  "revision",
  "import",
  "include",
  "unsupported"
]);

export class SubmoduleStatementParser {
  constructor(
    private readonly parsers: StatementParsers,
    private readonly module_parser: ModuleStatementParser
  ) {}

  parse_submodule(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.SUBMODULE);
    (context.module as any).name = tokens.consume_type(YangTokenType.IDENTIFIER);
    tokens.consume_type(YangTokenType.LBRACE);
    while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
      if (tokens.peek() === kw.BELONGS_TO) {
        this.parse_belongs_to(tokens, context);
      } else {
        const stmt = this.parsers.parseStatement(tokens, context);
        if (!INCLUDED_STATEMENT_SKIP.has(stmt.keyword ?? "")) {
          this.parsers.pushIncludedStatement(context, stmt);
        }
      }
    }
    tokens.consume_type(YangTokenType.RBRACE);
  }

  parse_belongs_to(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.BELONGS_TO);
    (context.module as any).belongs_to_module = tokens.consume_type(YangTokenType.IDENTIFIER);
    tokens.consume_type(YangTokenType.LBRACE);
    while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
      if (tokens.peek() === kw.PREFIX) {
        this.module_parser.parse_prefix_value_stmt(tokens);
      } else {
        this.parsers.parseStatement(tokens, context);
      }
    }
    tokens.consume_type(YangTokenType.RBRACE);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
}
