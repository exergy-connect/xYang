import * as kw from "../keywords";
import { YangExtensionStmt } from "../../core/ast";
import { ensureBuiltinExtensionsLoaded, getExtensionApplyCallback } from "../../ext/capabilities";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class ExtensionStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_extension_stmt(tokens: TokenStream, context: ParserContext): YangExtensionStmt {
    tokens.consume(kw.EXTENSION);
    const name = this.parsers.parse_identifier_argument(tokens, "extension");
    const ext = new YangExtensionStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(ext);
      this.parsers.parseBody(tokens, child, "extension", `extension '${name}'`);
      tokens.consume_type(YangTokenType.RBRACE);
    }
    ensureBuiltinExtensionsLoaded();
    const moduleName = String((context.module as { name?: string }).name ?? "");
    const callback = getExtensionApplyCallback(moduleName, name);
    if (callback) {
      ext.apply_callback = callback as unknown as typeof ext.apply_callback;
    }
    (context.module as any).extensions[name] = ext;
    this.parsers.add_to_parent_or_module(context, ext);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return ext;
  }

  parse_extension_argument_stmt(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.ARGUMENT);
    const arg = this.parsers.parse_identifier_argument(tokens, "argument");
    const parent = context.current_parent as YangExtensionStmt;
    if (parent instanceof YangExtensionStmt) {
      parent.argument_name = arg;
    }
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      this.parsers.parseBody(tokens, context, "argument", "extension argument");
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }

  parse_yin_element(tokens: TokenStream, context: ParserContext): void {
    tokens.consume(kw.YIN_ELEMENT);
    const value = this.parsers.parse_boolean_argument(tokens, "yin-element");
    const parent = context.current_parent;
    if (parent instanceof YangExtensionStmt) {
      parent.argument_yin_element = value;
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
}
