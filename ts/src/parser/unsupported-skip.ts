import * as kw from "./keywords";
import { TokenStream, YangTokenType } from "./parser-context";

export const UNSUPPORTED_CONSTRUCT_TYPES = new Set<string>([
  kw.DEVIATION,
  kw.RPC,
  kw.ACTION,
  kw.INPUT,
  kw.OUTPUT
]);

export function _consume_balanced_braces(tokens: TokenStream): void {
  let depth = 0;
  while (tokens.has_more()) {
    const pt = tokens.peek_type();
    if (pt === YangTokenType.LBRACE) {
      depth += 1;
      tokens.consume_type(YangTokenType.LBRACE);
    } else if (pt === YangTokenType.RBRACE) {
      depth -= 1;
      tokens.consume_type(YangTokenType.RBRACE);
      if (depth === 0) {
        return;
      }
    } else {
      tokens.consume();
    }
  }
}

export function skip_unsupported_construct(tokens: TokenStream, { context }: { context: string }): void {
  const tok = tokens.peek_token();
  if (!tok || !UNSUPPORTED_CONSTRUCT_TYPES.has(tok.value)) {
    return;
  }

  const kw = tok.value;
  const [line_num, char_pos] = tokens.position();
  const where = tokens.filename ?? "<string>";
  // Keep same behavior as Python version: warn and continue.
  // eslint-disable-next-line no-console
  console.warn(`Ignoring unsupported YANG statement '${kw}' (${context}) at ${where}:${line_num}:${char_pos}`);

  tokens.consume();
  while (tokens.has_more()) {
    const pt = tokens.peek_type();
    if (pt === YangTokenType.LBRACE) {
      _consume_balanced_braces(tokens);
      break;
    }
    if (pt === YangTokenType.SEMICOLON) {
      tokens.consume_type(YangTokenType.SEMICOLON);
      return;
    }
    if (pt === YangTokenType.RBRACE) {
      return;
    }
    tokens.consume();
  }
  tokens.consume_if_type(YangTokenType.SEMICOLON);
}

export function is_unsupported_construct_start(tokens: TokenStream): boolean {
  const tok = tokens.peek_token();
  return tok !== undefined && UNSUPPORTED_CONSTRUCT_TYPES.has(tok.value);
}

/** Consume ``status current|deprecated|obsolete;`` (RFC 7950 §7.21.2); not stored on the AST. */
export function skip_status_substatement(tokens: TokenStream): void {
  tokens.consume(kw.STATUS);
  if (tokens.peek_type() === YangTokenType.IDENTIFIER) {
    tokens.consume_type(YangTokenType.IDENTIFIER);
  }
  tokens.consume_if_type(YangTokenType.SEMICOLON);
}

export function skip_config_substatement(tokens: TokenStream, { context }: { context: string }): void {
  const [line_num, char_pos] = tokens.position();
  const where = tokens.filename ?? "<string>";
  tokens.consume(kw.CONFIG);
  let value: string | undefined;
  if (tokens.peek() === kw.TRUE || tokens.peek() === kw.FALSE) {
    value = tokens.consume();
  }
  tokens.consume_if_type(YangTokenType.SEMICOLON);
  // eslint-disable-next-line no-console
  console.warn(
    `Ignoring unsupported YANG substatement 'config' (${context}) at ${where}:${line_num}:${char_pos} (value=${JSON.stringify(value)})`
  );
}
