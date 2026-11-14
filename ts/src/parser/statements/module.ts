import { DISPATCH_REGISTRY } from "../dispatch-registry";
import * as kw from "../keywords";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import { YangSemanticError } from "../../core/errors";
import type { StatementParsers } from "../statement-parsers";

export class ModuleStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_module(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.MODULE);
    (context.module as any).name = this.parsers.parse_identifier_argument(tokens, "module");
    tokens.consume_type(YangTokenType.LBRACE);
    const scoped = context.with_dispatch("module", "module body");
    while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
      this.parsers.parseStatement(tokens, scoped);
    }
    tokens.consume_type(YangTokenType.RBRACE);
  }

  parse_yang_version(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.YANG_VERSION);
    const version = this.parsers.parse_string_argument(tokens);
    if (version !== "1" && version !== "1.1") {
      tokens.syntaxError(`yang-version argument must be '1' or '1.1', got '${version}'`);
    }
    (context.module as any).yang_version = version;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_namespace(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.NAMESPACE);
    (context.module as any).namespace = this.parsers.parse_string_argument(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_prefix(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.PREFIX);
    (context.module as any).prefix = this.parsers.parse_identifier_argument(tokens, "prefix");
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_organization(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.ORGANIZATION);
    (context.module as any).organization = this.parsers.parse_string_argument(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_contact(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.CONTACT);
    (context.module as any).contact = this.parsers.parse_string_argument(tokens);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_import_stmt(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.IMPORT);
    const moduleName = this.parsers.parse_identifier_argument(tokens, "import");
    let localPrefix: string | undefined;
    let revisionDate: string | undefined;
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const acc: { localPrefix?: string; revisionDate?: string } = {};
      this.parsers.importAcc = acc;
      try {
        while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
          const tt = this.parsers.dispatch_key(tokens);
          if (typeof tt === "string" && DISPATCH_REGISTRY.import!.keywords.has(tt)) {
            this.parsers.dispatchSubstatement(tokens, context, "import", "import");
          } else {
            // Known drift: unknown import body statements are skipped, not raised.
            this.skip_nested_statement(tokens);
          }
        }
      } finally {
        this.parsers.importAcc = undefined;
      }
      localPrefix = acc.localPrefix;
      revisionDate = acc.revisionDate;
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    if (!localPrefix || localPrefix.trim().length === 0) {
      throw new YangSemanticError(`Import '${moduleName}' is missing required prefix substatement`);
    }
    this.parsers.register_import(context, moduleName, localPrefix, revisionDate, tokens);
  }

  parse_include_stmt(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.INCLUDE);
    const name = this.parsers.parse_identifier_argument(tokens, "include");
    let revisionDate: string | undefined;
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      this.parsers.includeRevisionDate = undefined;
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        const tt = this.parsers.dispatch_key(tokens);
        if (typeof tt === "string" && DISPATCH_REGISTRY.include!.keywords.has(tt)) {
          this.parsers.dispatchSubstatement(tokens, context, "include", "include");
        } else {
          // Known drift: unknown include body statements are skipped, not raised.
          this.skip_nested_statement(tokens);
        }
      }
      revisionDate = this.parsers.includeRevisionDate;
      this.parsers.includeRevisionDate = undefined;
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    this.parsers.resolveInclude(context, name, revisionDate, tokens);
  }

  parse_prefix_value_stmt(tokens: TokenStream): void {
    tokens.consume(kw.PREFIX);
    this.parsers.parse_identifier_argument(tokens, "prefix");
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  private skip_nested_statement(tokens: TokenStream): void {
    let depth = 0;
    while (tokens.has_more()) {
      const tt = this.parsers.dispatch_key(tokens);
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
