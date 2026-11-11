import * as kw from "../keywords";
import { YangActionStmt, YangInputStmt, YangOutputStmt, YangRpcStmt } from "../../core/ast";
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
    return this.parseOperation(tokens, context, kw.RPC, new YangRpcStmt());
  }

  /** ``action`` under a container, list, grouping or augment (RFC 7950 §7.15). */
  parse_action(tokens: TokenStream, context: ParserContext): YangActionStmt {
    return this.parseOperation(tokens, context, kw.ACTION, new YangActionStmt()) as YangActionStmt;
  }

  private parseOperation(tokens: TokenStream, context: ParserContext, keyword: string, stmt: YangRpcStmt): YangRpcStmt {
    tokens.consume(keyword);
    const name = tokens.consume();
    stmt.name = name;
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      this.parsers.parseBody(tokens, child, keyword, `${keyword} '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
}
