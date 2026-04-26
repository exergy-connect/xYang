import * as kw from "../keywords";
import { YangExtensionStmt } from "../../core/ast";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class ExtensionStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_extension_stmt(tokens: TokenStream, context: ParserContext): YangExtensionStmt {
    tokens.consume(kw.EXTENSION);
    const name = tokens.consume_type(YangTokenType.IDENTIFIER);
    const ext = new YangExtensionStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(ext);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        const tt = this.parsers.dispatch_key(tokens);
        if (tt === kw.ARGUMENT) {
          this.parse_extension_argument_stmt(tokens, child);
        } else {
          this.parsers.parseStatement(tokens, child);
        }
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    (context.module as any).extensions[name] = ext;
    this.parsers.add_to_parent_or_module(context, ext);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return ext;
  }

  parse_extension_argument_stmt(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.ARGUMENT);
    const arg = tokens.peek_type() === YangTokenType.STRING
      ? tokens.consume_type(YangTokenType.STRING)
      : tokens.consume_type(YangTokenType.IDENTIFIER);
    const parent = context.current_parent as YangExtensionStmt;
    if (parent instanceof YangExtensionStmt) {
      parent.argument_name = arg;
    }
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        if (tokens.peek() === kw.YIN_ELEMENT) {
          tokens.consume(kw.YIN_ELEMENT);
          const [, tt] = tokens.consume_oneof([kw.TRUE, kw.FALSE]);
          parent.argument_yin_element = tt === kw.TRUE;
          tokens.consume_if_type(YangTokenType.SEMICOLON);
        } else {
          this.parsers.parseStatement(tokens, context);
        }
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
}
