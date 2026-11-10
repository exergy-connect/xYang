import * as kw from "../keywords";
import { YangAugmentStmt, YangUsesStmt } from "../../core/ast";
import { parseAbsoluteSchemaPath } from "../../core/identifier-ref";
import { YangSyntaxError } from "../../core/errors";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class AugmentStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

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
      this.parsers.parseBody(tokens, child, "augment", "augment");
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
