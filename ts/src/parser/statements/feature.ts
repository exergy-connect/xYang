import * as kw from "../keywords";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class FeatureStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_feature_stmt(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.FEATURE);
    const name = tokens.consume_type(YangTokenType.IDENTIFIER);
    ((context.module as any).features ??= new Set<string>()).add(name);
    const featParent = { if_features: [] as string[] };
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(featParent);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    if (featParent.if_features.length > 0) {
      const mod = context.module as Record<string, unknown>;
      const fif = (mod.feature_if_features ??= {}) as Record<string, string[]>;
      fif[name] = [...featParent.if_features];
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_if_feature_stmt(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.IF_FEATURE);
    let expression = this.parsers.parse_string_argument(tokens);
    // ``prefix:name`` is one unquoted argument; the lexer splits on ':'.
    if (tokens.has_more() && tokens.peek_type() === YangTokenType.COLON) {
      tokens.consume_type(YangTokenType.COLON);
      expression = `${expression}:${tokens.consume()}`;
    }
    const parent: any = context.current_parent;
    if (parent && Array.isArray(parent.if_features)) {
      parent.if_features.push(expression);
    }
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parsers.parseStatement(tokens, context);
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
}
