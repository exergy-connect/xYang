import * as kw from "../keywords";
import { YangAugmentStmt, YangUsesStmt } from "../../core/ast";
import { parseAbsoluteSchemaPath } from "../../core/identifier-ref";
import { YangSyntaxError } from "../../core/errors";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import { withDataNodeSubstatements } from "../metadata-substatements";
import type { StatementParsers } from "../statement-parsers";

export class AugmentStatementParser {
  private readonly augmentBodyDispatch: Record<string, (tokens: TokenStream, context: ParserContext) => void>;

  constructor(private readonly parsers: StatementParsers) {
    this.augmentBodyDispatch = withDataNodeSubstatements(this.parsers, {
      [kw.IF_FEATURE]: (tokens, context) => {
        this.parsers.feature_parser.parse_if_feature_stmt(tokens, context);
      },
      [kw.USES]: (tokens, context) => {
        this.parsers.uses_parser.parse_uses(tokens, context);
      },
      [kw.LEAF]: (tokens, context) => {
        this.parsers.leaf_parser.parse_leaf(tokens, context);
      },
      [kw.LEAF_LIST]: (tokens, context) => {
        this.parsers.leaf_list_parser.parse_leaf_list(tokens, context);
      },
      [kw.CONTAINER]: (tokens, context) => {
        this.parsers.container_parser.parse_container(tokens, context);
      },
      [kw.LIST]: (tokens, context) => {
        this.parsers.list_parser.parse_list(tokens, context);
      },
      [kw.CHOICE]: (tokens, context) => {
        this.parsers.choice_parser.parse_choice(tokens, context);
      },
      [kw.CASE]: (tokens, context) => {
        this.parsers.choice_parser.parse_case(tokens, context);
      },
      [kw.ANYDATA]: (tokens, context) => {
        this.parsers.anydata_parser.parse_anydata(tokens, context);
      },
      [kw.ANYXML]: (tokens, context) => {
        this.parsers.anyxml_parser.parse_anyxml(tokens, context);
      },
      [kw.WHEN]: (tokens, context) => {
        this.parsers.when_parser.parse_when(tokens, context);
      },
      [kw.MUST]: (tokens, context) => {
        this.parsers.must_parser.parse_must(tokens, context);
      },
      [kw.NOTIFICATION]: (tokens, context) => {
        this.parsers.notification_parser.parse_notification(tokens, context);
      }
    });
  }

  parse_augment(tokens: TokenStream, context: ParserContext): YangAugmentStmt {
    tokens.consume(kw.AUGMENT);
    const augment_path = this.parsers.parse_string_concatenation(tokens);
    // Absolute schema paths are segmented at parse time; relative paths under
    // ``uses`` stay as the path string until uses-expand resolves them.
    let augment_path_segments: ReturnType<typeof parseAbsoluteSchemaPath> = [];
    const raw = augment_path.replace(/^["']|["']$/g, "");
    if (raw.startsWith("/")) {
      try {
        augment_path_segments = parseAbsoluteSchemaPath(augment_path);
      } catch (err) {
        throw new YangSyntaxError(err instanceof Error ? err.message : String(err));
      }
    }
    const stmt = new YangAugmentStmt({ name: "augment", augment_path, augment_path_segments });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        const handler = this.parsers.substatement_handler(tokens, this.augmentBodyDispatch);
        if (handler) {
          handler(tokens, child);
        } else if (
          tokens.peek_type() === YangTokenType.IDENTIFIER &&
          tokens.peek_type_at(1) === YangTokenType.COLON
        ) {
          this.parsers.parse_prefixed_extension_statement_public(tokens, child);
        } else if (!this.parsers.skip_unsupported_or_raise_unknown(tokens, "augment")) {
          /* unreachable */
        }
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    const parent = context.current_parent;
    if (parent instanceof YangUsesStmt) {
      parent.augmentations.push(stmt);
    } else {
      this.parsers.add_to_parent_or_module(context, stmt);
    }
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
}
