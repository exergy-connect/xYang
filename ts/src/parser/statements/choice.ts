import * as kw from "../keywords";
import { YangCaseStmt, YangChoiceStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

const INLINE_CHOICE_SCHEMA_KEYS = new Set([
  kw.LEAF,
  kw.LEAF_LIST,
  kw.CONTAINER,
  kw.LIST,
  kw.ANYDATA,
  kw.ANYXML,
  kw.CHOICE
]);

export class ChoiceStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_choice(tokens: TokenStream, context: ParserContext): YangChoiceStmt {
    tokens.consume(kw.CHOICE);
    const name = tokens.consume();
    const stmt = new YangChoiceStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parse_choice_substatement(tokens, child, name);
      }
      tokens.consume_type(YangTokenType.RBRACE);
      stmt.validate_case_unique_child_names();
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }

  private parse_choice_substatement(tokens: TokenStream, context: ParserContext, choiceName: string): void {
    const key = this.parsers.dispatch_key(tokens);
    if (typeof key === "string" && INLINE_CHOICE_SCHEMA_KEYS.has(key)) {
      this.parse_choice_implicit_case(tokens, context);
      return;
    }
    this.parsers.dispatchSubstatement(tokens, context, "choice", `choice '${choiceName}'`);
  }

  private parse_choice_implicit_case(tokens: TokenStream, context: ParserContext): void {
    const choice = context.current_parent;
    if (!(choice instanceof YangChoiceStmt)) {
      tokens.syntaxError("internal: implicit choice case outside choice body");
    }
    const caseStmt = new YangCaseStmt({ name: "" });
    const caseCtx = context.push_parent(caseStmt);
    const key = this.parsers.dispatch_key(tokens);
    const handler = typeof key === "string" ? this.parsers.handlerFor("case", key) : undefined;
    if (!handler) {
      tokens.syntaxError(`internal: unsupported implicit choice schema '${String(tokens.peek())}'`);
    }
    handler(tokens, caseCtx);
    if (caseStmt.statements.length === 0) {
      tokens.syntaxError("Expected a schema node in implicit choice case (RFC 7950 §7.9.2)");
    }
    const first = caseStmt.statements[0]!;
    const caseName = first.name || first.get_schema_node();
    if (!caseName) {
      tokens.syntaxError("Implicit choice case requires a named schema node (RFC 7950 §7.9.2)");
    }
    caseStmt.name = caseName;
    choice.cases.push(caseStmt);
  }

  parse_case(tokens: TokenStream, context: ParserContext): YangCaseStmt {
    tokens.consume(kw.CASE);
    const name = tokens.consume();
    const stmt = new YangCaseStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child, "case", `case '${name}'`);
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
    const value = this.parsers.parse_boolean_argument(tokens, "mandatory");
    const parent = context.current_parent as YangChoiceStmt;
    if (parent instanceof YangChoiceStmt) {
      parent.mandatory = value;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_choice_default(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.DEFAULT);
    const name = this.parsers.parse_string_argument(tokens);
    const parent = context.current_parent;
    if (parent instanceof YangChoiceStmt) {
      parent.default = name;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
}
