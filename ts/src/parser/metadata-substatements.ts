import {
  DATA_NODE_SUBSTATEMENTS,
  METADATA_SUBSTATEMENTS
} from "./dispatch-registry";
import * as kw from "./keywords";
import type { StatementParsers } from "./statement-parsers";
import type { ParserContext, TokenStream } from "./parser-context";

export type SubstatementHandler = (tokens: TokenStream, context: ParserContext) => void;

/**
 * Thin wrappers over the keyword groups in `dispatch-registry`.
 * Prefer the registry. These helpers remain so a caller can still merge the
 * metadata or data-node keywords into a handler map.
 */
function metadataHandlers(parsers: StatementParsers): Record<string, SubstatementHandler> {
  return {
    [kw.DESCRIPTION]: (tokens, context) => {
      parsers.parse_description(tokens, context);
    },
    [kw.UNITS]: (tokens, context) => {
      parsers.parse_units(tokens, context);
    },
    [kw.REFERENCE]: (tokens, context) => {
      parsers.parse_reference(tokens, context);
    },
    [kw.STATUS]: (tokens, context) => {
      parsers.parse_status_ignored(tokens, context);
    }
  };
}

export function withMetadataSubstatements(
  parsers: StatementParsers,
  dispatch: Record<string, SubstatementHandler>
): Record<string, SubstatementHandler> {
  const out = { ...dispatch };
  const handlers = metadataHandlers(parsers);
  for (const key of METADATA_SUBSTATEMENTS) {
    out[key] ??= handlers[key]!;
  }
  return out;
}

export function withDataNodeSubstatements(
  parsers: StatementParsers,
  dispatch: Record<string, SubstatementHandler>
): Record<string, SubstatementHandler> {
  const out = withMetadataSubstatements(parsers, dispatch);
  for (const key of DATA_NODE_SUBSTATEMENTS) {
    if (METADATA_SUBSTATEMENTS.has(key)) {
      continue;
    }
    if (key === kw.CONFIG) {
      out[key] ??= (tokens, context) => {
        parsers.parse_config(tokens, context);
      };
    } else if (key === kw.TYPEDEF) {
      out[key] ??= (tokens, context) => {
        parsers.typedef_parser.parse_typedef(tokens, context);
      };
    }
  }
  return out;
}
