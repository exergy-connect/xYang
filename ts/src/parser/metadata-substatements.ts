import * as kw from "./keywords";
import type { StatementParsers } from "./statement-parsers";
import type { ParserContext, TokenStream } from "./parser-context";

export type SubstatementHandler = (tokens: TokenStream, context: ParserContext) => void;

export function withMetadataSubstatements(
  parsers: StatementParsers,
  dispatch: Record<string, SubstatementHandler>
): Record<string, SubstatementHandler> {
  const out = { ...dispatch };
  out[kw.DESCRIPTION] ??= (tokens, context) => {
    parsers.parse_description(tokens, context);
  };
  out[kw.REFERENCE] ??= (tokens, context) => {
    parsers.parse_reference(tokens, context);
  };
  out[kw.STATUS] ??= (tokens, context) => {
    parsers.parse_status_ignored(tokens, context);
  };
  return out;
}

export function withDataNodeSubstatements(
  parsers: StatementParsers,
  dispatch: Record<string, SubstatementHandler>
): Record<string, SubstatementHandler> {
  const out = withMetadataSubstatements(parsers, dispatch);
  out[kw.CONFIG] ??= (tokens, context) => {
    parsers.parse_config(tokens, context);
  };
  out[kw.STATUS] ??= (tokens, context) => {
    parsers.parse_status_ignored(tokens, context);
  };
  // RFC 7950 §7.13 — typedef is legal in container, list, choice, case, augment, …
  out[kw.TYPEDEF] ??= (tokens, context) => {
    parsers.typedef_parser.parse_typedef(tokens, context);
  };
  return out;
}
