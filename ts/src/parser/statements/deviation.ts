import * as kw from "../keywords";
import { parseAbsoluteSchemaPath } from "../../core/identifier-ref";
import { YangSyntaxError } from "../../core/errors";
import type { SerializedStatement } from "../../core/model";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import { _consume_balanced_braces, warn_unsupported_deviate } from "../unsupported-skip";
import type { StatementParsers } from "../statement-parsers";

export class DeviationStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  parse_deviation(tokens: TokenStream, context: ParserContext): SerializedStatement {
    tokens.consume(kw.DEVIATION);
    if (tokens.peek_type() !== YangTokenType.STRING) {
      tokens.syntaxError("deviation argument must be a quoted absolute schema path");
    }
    const path = this.parsers.parse_string_concatenation(tokens);
    let segments: ReturnType<typeof parseAbsoluteSchemaPath>;
    try {
      segments = parseAbsoluteSchemaPath(path);
    } catch (err) {
      throw new YangSyntaxError(err instanceof Error ? err.message : String(err));
    }
    const holder: { description: string; reference: string } = { description: "", reference: "" };
    let notSupported = false;
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const body = context.push_parent(holder);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        const peek = tokens.peek();
        if (peek === kw.DESCRIPTION) {
          this.parsers.parse_description(tokens, body);
        } else if (peek === kw.REFERENCE) {
          this.parsers.parse_reference(tokens, body);
        } else if (peek === kw.DEVIATE) {
          if (this.parseDeviate(tokens, path)) {
            notSupported = true;
          }
        } else if (!this.parsers.skip_unsupported_or_raise_unknown(tokens, "deviation")) {
          /* unreachable */
        }
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    const stmt: SerializedStatement = {
      __class__: "YangStatement",
      keyword: "deviation",
      name: "deviation",
      argument: path,
      deviation_path: path,
      deviation_path_segments: segments,
      not_supported: notSupported,
      statements: []
    };
    if (holder.description) {
      stmt.description = holder.description;
    }
    if (holder.reference) {
      stmt.reference = holder.reference;
    }
    return stmt;
  }

  /** Returns true when the substatement is ``deviate not-supported``. */
  private parseDeviate(tokens: TokenStream, path: string): boolean {
    tokens.consume(kw.DEVIATE);
    if (tokens.peek_type() !== YangTokenType.IDENTIFIER) {
      tokens.syntaxError(`Expected deviate argument, got '${tokens.peek() ?? ""}'`);
    }
    const kind = tokens.consume_type(YangTokenType.IDENTIFIER);
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
