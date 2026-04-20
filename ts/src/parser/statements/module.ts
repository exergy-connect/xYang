import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import { YangSemanticError } from "../../core/errors";
import type { StatementParsers } from "../statement-parsers";

export class ModuleStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_module(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.MODULE);
    (context.module as any).name = tokens.consume_type(YangTokenType.IDENTIFIER);
    tokens.consume_type(YangTokenType.LBRACE);
    while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
      this.parsers.parseStatement(tokens, context);
    }
    tokens.consume_type(YangTokenType.RBRACE);
  }

  parse_yang_version(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.YANG_VERSION);
    const [version] = tokens.consume_oneof([YangTokenType.IDENTIFIER, YangTokenType.DOTTED_NUMBER]);
    (context.module as any).yang_version = version;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_namespace(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.NAMESPACE);
    (context.module as any).namespace = tokens.consume_type(YangTokenType.STRING);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_prefix(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.PREFIX);
    const tt = tokens.peek_type();
    (context.module as any).prefix = tt === YangTokenType.STRING
      ? tokens.consume_type(YangTokenType.STRING)
      : tokens.consume_type(YangTokenType.IDENTIFIER);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_organization(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.ORGANIZATION);
    (context.module as any).organization = tokens.consume_type(YangTokenType.STRING);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_contact(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.CONTACT);
    (context.module as any).contact = tokens.consume_type(YangTokenType.STRING);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_import_stmt(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.IMPORT);
    const moduleName = tokens.consume_type(YangTokenType.IDENTIFIER);
    let localPrefix: string | undefined;
    let revisionDate: string | undefined;
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        const tt = tokens.peek_type();
        if (tt === YangTokenType.PREFIX) {
          tokens.consume_type(YangTokenType.PREFIX);
          localPrefix = tokens.peek_type() === YangTokenType.STRING
            ? tokens.consume_type(YangTokenType.STRING)
            : tokens.consume_type(YangTokenType.IDENTIFIER);
          tokens.consume_if_type(YangTokenType.SEMICOLON);
          continue;
        }
        if (tt === YangTokenType.REVISION_DATE) {
          revisionDate = this.parsers.revision_parser.parse_revision_date_statement(tokens);
          continue;
        }
        this.skip_nested_statement(tokens);
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    if (!localPrefix || localPrefix.trim().length === 0) {
      throw new YangSemanticError(`Import '${moduleName}' is missing required prefix substatement`);
    }
    this.parsers.register_import(context, moduleName, localPrefix, revisionDate, tokens);
  }

  parse_include_stmt(tokens: TokenStream, context: ParserContext): void {
    tokens.consume_type(YangTokenType.INCLUDE);
    tokens.consume_type(YangTokenType.IDENTIFIER);
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parsers.parseStatement(tokens, context);
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_prefix_value_stmt(tokens: TokenStream): void {
    tokens.consume_type(YangTokenType.PREFIX);
    if (tokens.peek_type() === YangTokenType.STRING) {
      tokens.consume_type(YangTokenType.STRING);
    } else {
      tokens.consume_type(YangTokenType.IDENTIFIER);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  private skip_nested_statement(tokens: TokenStream): void {
    let depth = 0;
    while (tokens.has_more()) {
      const tt = tokens.peek_type();
      if (tt === YangTokenType.LBRACE) {
        depth += 1;
        tokens.consume_type(YangTokenType.LBRACE);
        continue;
      }
      if (tt === YangTokenType.RBRACE) {
        if (depth === 0) {
          return;
        }
        depth -= 1;
        tokens.consume_type(YangTokenType.RBRACE);
        continue;
      }
      if (tt === YangTokenType.SEMICOLON && depth === 0) {
        tokens.consume_type(YangTokenType.SEMICOLON);
        return;
      }
      tokens.consume();
    }
  }
}
