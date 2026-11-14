import * as kw from "../keywords";
import { parseAbsoluteSchemaPath } from "../../core/identifier-ref";
import { YangSyntaxError } from "../../core/errors";
import { YangStatement, type DeviateRecord } from "../../core/model";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

type DeviationHolder = {
  description: string;
  reference: string;
  not_supported: boolean;
  target_path: string;
  deviates: DeviateRecord[];
};

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
    const holder: DeviationHolder = {
      description: "",
      reference: "",
      not_supported: false,
      target_path: path,
      deviates: []
    };
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const body = context.push_parent(holder);
      this.parsers.parseBody(tokens, body, "deviation", "deviation");
      tokens.consume_type(YangTokenType.RBRACE);
    }
    if (holder.not_supported && holder.deviates.length > 0) {
      tokens.syntaxError(
        `deviation '${path}': 'deviate not-supported' cannot be combined with other deviate statements (RFC 7950 §7.20.3.2)`
      );
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    const stmt: YangStatement = new YangStatement({
      keyword: "deviation",
      name: "deviation",
      argument: path,
      deviation_path: path,
      deviation_path_segments: segments,
      not_supported: holder.not_supported,
      deviates: holder.deviates,
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
    const holder = context.current_parent as DeviationHolder;
    tokens.consume(kw.DEVIATE);
    const kind = this.parsers.parse_string_argument(tokens);
    if (kind === kw.NOT_SUPPORTED) {
      if (tokens.peek_type() === YangTokenType.LBRACE) {
        tokens.consume_type(YangTokenType.LBRACE);
        tokens.consume_type(YangTokenType.RBRACE);
      }
      tokens.consume_if_type(YangTokenType.SEMICOLON);
      holder.not_supported = true;
      return;
    }
    const allowed = kw.DEVIATE_SUBSTATEMENTS.get(kind);
    if (!allowed) {
      tokens.syntaxError(`Unknown deviate argument '${kind}'`);
    }
    const deviate: DeviateRecord = { kind, defaults: [], must: [], unique: [] };
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        const keyword = tokens.peek() ?? "";
        if (!allowed.has(keyword)) {
          tokens.syntaxError(`'${keyword}' is not allowed in 'deviate ${kind}' (RFC 7950 §7.20.3.2)`);
        }
        this.parseProperty(tokens, context, deviate, keyword);
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    holder.deviates.push(deviate);
  }

  private parseProperty(tokens: TokenStream, context: ParserContext, deviate: DeviateRecord, keyword: string): void {
    const p = this.parsers;
    if (keyword === kw.MUST) {
      deviate.must.push(p.mustStatement(p.must_parser.parse_must(tokens, context)));
      return;
    }
    if (keyword === kw.TYPE) {
      if (deviate.type !== undefined) {
        tokens.syntaxError(`duplicate 'type' in 'deviate ${deviate.kind}'`);
      }
      deviate.type = p.typeShape(p.type_parser.parse_type(tokens, context));
      return;
    }
    tokens.consume(keyword);
    const named: Record<string, boolean> = {
      config: deviate.config !== undefined,
      mandatory: deviate.mandatory !== undefined,
      "min-elements": deviate.min_elements !== undefined,
      "max-elements": deviate.max_elements_set === true,
      units: deviate.units !== undefined
    };
    if (named[keyword]) {
      tokens.syntaxError(`duplicate '${keyword}' in 'deviate ${deviate.kind}'`);
    }
    if (keyword === kw.CONFIG) {
      deviate.config = p.parse_boolean_argument(tokens, "config");
    } else if (keyword === kw.MANDATORY) {
      deviate.mandatory = p.parse_boolean_argument(tokens, "mandatory");
    } else if (keyword === kw.MIN_ELEMENTS) {
      const value = p.parse_integer_or_unbounded(tokens, "min-elements");
      if (value === undefined) {
        tokens.syntaxError("min-elements cannot be 'unbounded'");
      }
      deviate.min_elements = value;
    } else if (keyword === kw.MAX_ELEMENTS) {
      const value = p.parse_integer_or_unbounded(tokens, "max-elements");
      if (value !== undefined) {
        deviate.max_elements = value;
      }
      deviate.max_elements_set = true;
    } else if (keyword === kw.UNITS) {
      deviate.units = p.parse_string_argument(tokens);
    } else if (keyword === kw.DEFAULT) {
      deviate.defaults.push(p.parse_default_value_tokens(tokens));
    } else if (keyword === kw.UNIQUE) {
      const arg = p.parse_string_argument(tokens);
      const paths = arg
        .split(/\s+/)
        .filter(Boolean)
        .map((path) =>
          path
            .split("/")
            .filter(Boolean)
            .map((seg) => (seg.includes(":") ? seg.slice(seg.indexOf(":") + 1) : seg))
            .join("/")
        );
      if (paths.length === 0) {
        tokens.syntaxError("unique requires at least one descendant path");
      }
      deviate.unique.push(paths);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
  }
}
