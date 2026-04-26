import * as kw from "../keywords";
import { YangCaseStmt, YangChoiceStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

/** RFC 7950 `case-stmt` data-def and common metadata substmts (not `mandatory` on the case itself). */
const CASE_BODY_ALLOWED_STATEMENT_STARTS: readonly YangTokenType[] = [
  kw.CONTAINER,
  kw.LIST,
  kw.LEAF,
  kw.LEAF_LIST,
  kw.CHOICE,
  kw.ANYDATA,
  kw.ANYXML,
  kw.USES,
  kw.AUGMENT,
  kw.DESCRIPTION,
  kw.IF_FEATURE,
  kw.WHEN,
  kw.REFERENCE,
  kw.STATUS
];

export class ChoiceStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_choice(tokens: TokenStream, context: ParserContext): YangChoiceStmt {
    tokens.consume(kw.CHOICE);
    const name = tokens.consume();
    const stmt = new YangChoiceStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        if (tokens.peek() === kw.CASE) {
          this.parse_case(tokens, child);
        } else {
          this.parsers.parseStatement(tokens, child);
        }
      }
      tokens.consume_type(YangTokenType.RBRACE);
      stmt.validate_case_unique_child_names();
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }

  parse_case(tokens: TokenStream, context: ParserContext): YangCaseStmt {
    tokens.consume(kw.CASE);
    const name = tokens.consume();
    const stmt = new YangCaseStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parsers.parseStatement(tokens, child, {
          allowedStatementStarts: CASE_BODY_ALLOWED_STATEMENT_STARTS,
          restrictionContext: "under 'case'"
        });
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    const parent = context.current_parent as YangChoiceStmt;
    if (parent instanceof YangChoiceStmt) {
      parent.cases.push(stmt);
    } else {
      this.parsers.add_to_parent_or_module(context, stmt);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }

  parse_choice_mandatory(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.MANDATORY);
    const [, tt] = tokens.consume_oneof([kw.TRUE, kw.FALSE]);
    const parent = context.current_parent as YangChoiceStmt;
    if (parent instanceof YangChoiceStmt) {
      parent.mandatory = tt === kw.TRUE;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
}
