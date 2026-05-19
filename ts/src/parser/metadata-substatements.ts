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
  return out;
}
