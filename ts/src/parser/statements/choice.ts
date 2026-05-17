import * as kw from "../keywords";
import { YangCaseStmt, YangChoiceStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import { withDataNodeSubstatements } from "../metadata-substatements";
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
  private readonly choiceSubstatementDispatch: Record<string, (tokens: TokenStream, context: ParserContext) => void>;
  private readonly caseSubstatementDispatch: Record<string, (tokens: TokenStream, context: ParserContext) => void>;

  constructor(private readonly parsers: StatementParsers) {
    this.choiceSubstatementDispatch = withDataNodeSubstatements(this.parsers, {
      [kw.WHEN]: (tokens, context) => {
        this.parsers.when_parser.parse_when(tokens, context);
      },
      [kw.IF_FEATURE]: (tokens, context) => {
        this.parsers.feature_parser.parse_if_feature_stmt(tokens, context);
      },
      [kw.CASE]: (tokens, context) => {
        this.parse_case(tokens, context);
      },
      [kw.MANDATORY]: (tokens, context) => {
        this.parse_choice_mandatory(tokens, context);
      }
    });
    this.caseSubstatementDispatch = withDataNodeSubstatements(this.parsers, {
      [kw.WHEN]: (tokens, context) => {
        this.parsers.when_parser.parse_when(tokens, context);
      },
      [kw.IF_FEATURE]: (tokens, context) => {
        this.parsers.feature_parser.parse_if_feature_stmt(tokens, context);
      },
      [kw.USES]: (tokens, context) => {
        this.parsers.uses_parser.parse_uses(tokens, context);
      },
      [kw.LEAF]: (tokens, context) => {
        this.parsers.leaf_parser.parse_leaf(tokens, context);
      },
      [kw.CONTAINER]: (tokens, context) => {
        this.parsers.container_parser.parse_container(tokens, context);
      },
      [kw.LIST]: (tokens, context) => {
        this.parsers.list_parser.parse_list(tokens, context);
      },
      [kw.LEAF_LIST]: (tokens, context) => {
        this.parsers.leaf_list_parser.parse_leaf_list(tokens, context);
      },
      [kw.ANYDATA]: (tokens, context) => {
        this.parsers.anydata_parser.parse_anydata(tokens, context);
      },
      [kw.ANYXML]: (tokens, context) => {
        this.parsers.anyxml_parser.parse_anyxml(tokens, context);
      },
      [kw.CHOICE]: (tokens, context) => {
        this.parse_choice(tokens, context);
      }
    });
  }

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
    const unsupported = `choice '${choiceName}'`;
    const handler = this.parsers.substatement_handler(tokens, this.choiceSubstatementDispatch);
    if (handler) {
      handler(tokens, context);
      return;
    }
    const key = this.parsers.dispatch_key(tokens);
    if (typeof key === "string" && INLINE_CHOICE_SCHEMA_KEYS.has(key)) {
      this.parse_choice_implicit_case(tokens, context);
      return;
    }
    if (tokens.peek_type() === YangTokenType.IDENTIFIER && tokens.peek_type_at(1) === YangTokenType.COLON) {
      this.parsers.parse_prefixed_extension_statement_public(tokens, context);
      return;
    }
    this.parsers.skip_unsupported_or_raise_unknown(tokens, unsupported);
  }

  private parse_choice_implicit_case(tokens: TokenStream, context: ParserContext): void {
    const choice = context.current_parent;
    if (!(choice instanceof YangChoiceStmt)) {
      tokens.syntaxError("internal: implicit choice case outside choice body");
    }
    const caseStmt = new YangCaseStmt({ name: "" });
    const caseCtx = context.push_parent(caseStmt);
    const handler = this.parsers.substatement_handler(tokens, this.caseSubstatementDispatch);
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
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parse_case_substatement(tokens, child, name);
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

  private parse_case_substatement(tokens: TokenStream, context: ParserContext, caseName: string): void {
    const unsupported = `case '${caseName}'`;
    const handler = this.parsers.substatement_handler(tokens, this.caseSubstatementDispatch);
    if (handler) {
      handler(tokens, context);
      return;
    }
    if (tokens.peek_type() === YangTokenType.IDENTIFIER && tokens.peek_type_at(1) === YangTokenType.COLON) {
      this.parsers.parse_prefixed_extension_statement_public(tokens, context);
      return;
    }
    if (this.parsers.skip_unsupported_if_present(tokens, unsupported)) {
      return;
    }
    this.parsers.skip_unsupported_or_raise_unknown(tokens, unsupported);
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
