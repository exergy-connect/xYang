import * as kw from "../keywords";
import { YangInputStmt, YangOutputStmt, YangRpcStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import { withMetadataSubstatements } from "../metadata-substatements";
import type { StatementParsers } from "../statement-parsers";

/** Parser for ``rpc`` and its ``input`` / ``output`` substatements (RFC 7950 §7.14). */
export class RpcStatementParser {
  private readonly ioSubstatementDispatch: Record<string, (tokens: TokenStream, context: ParserContext) => void>;
  private readonly rpcSubstatementDispatch: Record<string, (tokens: TokenStream, context: ParserContext) => void>;

  constructor(private readonly parsers: StatementParsers) {
    this.ioSubstatementDispatch = withMetadataSubstatements(this.parsers, {
      [kw.TYPEDEF]: (tokens, context) => {
        this.parsers.typedef_parser.parse_typedef(tokens, context);
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
        this.parsers.container_parser.parse_container(tokens, context);
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
      }
    });

    this.rpcSubstatementDispatch = withMetadataSubstatements(this.parsers, {
      [kw.WHEN]: (tokens, context) => {
        this.parsers.when_parser.parse_when(tokens, context);
      },
      [kw.MUST]: (tokens, context) => {
        this.parsers.must_parser.parse_must(tokens, context);
      },
      [kw.INPUT]: (tokens, context) => {
        this.parse_input(tokens, context);
      },
      [kw.OUTPUT]: (tokens, context) => {
        this.parse_output(tokens, context);
      },
      [kw.IF_FEATURE]: (tokens, context) => {
        this.parsers.feature_parser.parse_if_feature_stmt(tokens, context);
      }
    });
  }

  private parseIoSubstatement(tokens: TokenStream, context: ParserContext, blockName: string): void {
    const handler = this.parsers.substatement_handler(tokens, this.ioSubstatementDispatch);
    if (handler) {
      handler(tokens, context);
      return;
    }
    if (tokens.peek_type() === YangTokenType.IDENTIFIER && tokens.peek_type_at(1) === YangTokenType.COLON) {
      this.parsers.parse_prefixed_extension_statement_public(tokens, context);
      return;
    }
    if (!this.parsers.skip_unsupported_or_raise_unknown(tokens, `${blockName} block`)) {
      /* unreachable */
    }
  }

  private parseIoBlock(
    tokens: TokenStream,
    context: ParserContext,
    keyword: string,
    ioStmt: YangInputStmt | YangOutputStmt
  ): YangInputStmt | YangOutputStmt {
    tokens.consume(keyword);
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(ioStmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parseIoSubstatement(tokens, child, keyword);
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, ioStmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return ioStmt;
  }

  parse_input(tokens: TokenStream, context: ParserContext): YangInputStmt {
    return this.parseIoBlock(tokens, context, kw.INPUT, new YangInputStmt()) as YangInputStmt;
  }

  parse_output(tokens: TokenStream, context: ParserContext): YangOutputStmt {
    return this.parseIoBlock(tokens, context, kw.OUTPUT, new YangOutputStmt()) as YangOutputStmt;
  }

  private parseRpcSubstatement(tokens: TokenStream, context: ParserContext, rpcName: string): void {
    const handler = this.parsers.substatement_handler(tokens, this.rpcSubstatementDispatch);
    if (handler) {
      handler(tokens, context);
      return;
    }
    if (tokens.peek_type() === YangTokenType.IDENTIFIER && tokens.peek_type_at(1) === YangTokenType.COLON) {
      this.parsers.parse_prefixed_extension_statement_public(tokens, context);
      return;
    }
    if (!this.parsers.skip_unsupported_or_raise_unknown(tokens, `rpc '${rpcName}'`)) {
      /* unreachable */
    }
  }

  parse_rpc(tokens: TokenStream, context: ParserContext): YangRpcStmt {
    tokens.consume(kw.RPC);
    const rpcName = tokens.consume();
    const rpcStmt = new YangRpcStmt({ name: rpcName });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(rpcStmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parseRpcSubstatement(tokens, child, rpcName);
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, rpcStmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return rpcStmt;
  }
}
