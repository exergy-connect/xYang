import * as kw from "../keywords";
import { YangInputStmt, YangOutputStmt, YangRpcStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

/** Parser for ``rpc`` and its ``input`` / ``output`` substatements (RFC 7950 §7.14). */
export class RpcStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  private parseIoBlock(
    tokens: TokenStream,
    context: ParserContext,
    keyword: string,
    ioStmt: YangInputStmt | YangOutputStmt
  ): YangInputStmt | YangOutputStmt {
    tokens.consume(keyword);
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(ioStmt);
      this.parsers.parseBody(tokens, child, keyword, `${keyword} block`);
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

  parse_rpc(tokens: TokenStream, context: ParserContext): YangRpcStmt {
    tokens.consume(kw.RPC);
    const rpcName = tokens.consume();
    const rpcStmt = new YangRpcStmt({ name: rpcName });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(rpcStmt);
      this.parsers.parseBody(tokens, child, "rpc", `rpc '${rpcName}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, rpcStmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return rpcStmt;
  }
}
