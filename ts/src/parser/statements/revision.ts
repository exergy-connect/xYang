import * as kw from "../keywords";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class RevisionStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_revision(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.REVISION);
    const date = this.parsers.parse_string_argument(tokens);
    const rev: { date: string; description: string; reference: string } = {
      date,
      description: "",
      reference: "",
    };
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const body = { description: "", reference: "" };
      const child = context.push_parent(body);
      this.parsers.parseBody(tokens, child, "revision", "revision");
      rev.description = body.description;
      rev.reference = body.reference;
      tokens.consume_type(YangTokenType.RBRACE);
    }
    ((context.module as any).revisions ??= []).push(rev);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_revision_date_statement(tokens: TokenStream): string {
    tokens.consume(kw.REVISION_DATE);
    const date = this.parsers.parse_string_argument(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return date;
  }
}
