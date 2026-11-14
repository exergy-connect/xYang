import * as kw from "../keywords";
import { parseAbsoluteSchemaPath } from "../../core/identifier-ref";
import { YangSyntaxError } from "../../core/errors";
import { YangStatement } from "../../core/model";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import { _consume_balanced_braces, warn_unsupported_deviate } from "../unsupported-skip";
import type { StatementParsers } from "../statement-parsers";

export class DeviationStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_deviation(tokens: TokenStream, context: ParserContext): YangStatement {
    tokens.consume(kw.DEVIATION);
    const path = this.parsers.parse_string_argument(tokens);
    let segments: ReturnType<typeof parseAbsoluteSchemaPath>;
    try {
      segments = parseAbsoluteSchemaPath(path);
    } catch (err) {
      throw new YangSyntaxError(err instanceof Error ? err.message : String(err));
    }
    const holder: { description: string; reference: string; not_supported: boolean; target_path: string } = {
      description: "",
      reference: "",
      not_supported: false,
      target_path: path
    };
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const body = context.push_parent(holder);
      this.parsers.parseBody(tokens, body, "deviation", "deviation");
      tokens.consume_type(YangTokenType.RBRACE);
    }
    const notSupported = holder.not_supported;
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    const stmt: YangStatement = new YangStatement({
      keyword: "deviation",
      name: "deviation",
      argument: path,
      deviation_path: path,
      deviation_path_segments: segments,
      not_supported: notSupported,
      statements: []
    });
    if (holder.description) {
      stmt.description = holder.description;
    }
    if (holder.reference) {
      stmt.reference = holder.reference;
    }
    return stmt;
  }

  parse_deviate_substatement(tokens: TokenStream, context: ParserContext): void {
    const holder = context.current_parent as { not_supported: boolean; target_path: string };
    if (this.parseDeviate(tokens, holder.target_path)) {
      holder.not_supported = true;
    }
  }

  /** Returns true when the substatement is ``deviate not-supported``. */
  private parseDeviate(tokens: TokenStream, path: string): boolean {
    tokens.consume(kw.DEVIATE);
    const kind = this.parsers.parse_string_argument(tokens);
    if (kind === kw.NOT_SUPPORTED) {
      tokens.consume_if_type(YangTokenType.SEMICOLON);
      return true;
    }
    if (kw.UNSUPPORTED_DEVIATE_KINDS.has(kind)) {
      warn_unsupported_deviate(kind, path);
      if (tokens.peek_type() === YangTokenType.LBRACE) {
        _consume_balanced_braces(tokens);
      }
      tokens.consume_if_type(YangTokenType.SEMICOLON);
      return false;
    }
    tokens.syntaxError(`Unknown deviate argument '${kind}'`);
  }
}
