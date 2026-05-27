import * as kw from "../keywords";
import { YangContainerStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import { withDataNodeSubstatements } from "../metadata-substatements";
import type { StatementParsers } from "../statement-parsers";

export class ContainerStatementParser {
  private readonly containerSubstatementDispatch: Record<
    string,
    (tokens: TokenStream, context: ParserContext) => void
  >;

  constructor(private readonly parsers: StatementParsers) {
    this.containerSubstatementDispatch = withDataNodeSubstatements(this.parsers, {
      [kw.PRESENCE]: (tokens, context) => {
        this.parsers.parse_presence(tokens, context);
      },
      [kw.WHEN]: (tokens, context) => {
        this.parsers.when_parser.parse_when(tokens, context);
      },
      [kw.MUST]: (tokens, context) => {
        this.parsers.must_parser.parse_must(tokens, context);
      },
      [kw.LEAF]: (tokens, context) => {
        this.parsers.leaf_parser.parse_leaf(tokens, context);
      },
      [kw.CONTAINER]: (tokens, context) => {
        this.parse_container(tokens, context);
      },
      [kw.LIST]: (tokens, context) => {
        this.parsers.list_parser.parse_list(tokens, context);
      },
      [kw.LEAF_LIST]: (tokens, context) => {
        this.parsers.leaf_list_parser.parse_leaf_list(tokens, context);
      },
      [kw.USES]: (tokens, context) => {
        this.parsers.uses_parser.parse_uses(tokens, context);
      },
      [kw.CHOICE]: (tokens, context) => {
        this.parsers.choice_parser.parse_choice(tokens, context);
      },
      [kw.IF_FEATURE]: (tokens, context) => {
        this.parsers.feature_parser.parse_if_feature_stmt(tokens, context);
      },
      [kw.ANYDATA]: (tokens, context) => {
        this.parsers.anydata_parser.parse_anydata(tokens, context);
      },
      [kw.ANYXML]: (tokens, context) => {
        this.parsers.anyxml_parser.parse_anyxml(tokens, context);
      },
      [kw.NOTIFICATION]: (tokens, context) => {
        this.parsers.notification_parser.parse_notification(tokens, context);
      }
    });
  }

  private parseContainerSubstatement(tokens: TokenStream, context: ParserContext, containerName: string): void {
    const handler = this.parsers.substatement_handler(tokens, this.containerSubstatementDispatch);
    if (handler) {
      handler(tokens, context);
      return;
    }
    if (tokens.peek_type() === YangTokenType.IDENTIFIER && tokens.peek_type_at(1) === YangTokenType.COLON) {
      this.parsers.parse_prefixed_extension_statement_public(tokens, context);
      return;
    }
    if (!this.parsers.skip_unsupported_or_raise_unknown(tokens, `container '${containerName}'`)) {
      /* unreachable */
    }
  }

  parse_container(tokens: TokenStream, context: ParserContext): YangContainerStmt {
    tokens.consume(kw.CONTAINER);
    const name = tokens.consume();
    const stmt = new YangContainerStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parseContainerSubstatement(tokens, child, name);
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
}
