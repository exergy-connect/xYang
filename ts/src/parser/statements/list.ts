import * as kw from "../keywords";
import { YangLeafStmt, YangListStmt } from "../../core/ast";
import { YangSemanticError } from "../../core/errors";
import { ParserContext, TokenStream, YangTokenType } from "../parser-context";
import type { StatementParsers } from "../statement-parsers";

export class ListStatementParser {
  constructor(private readonly parsers: StatementParsers) {}

  private validateKeyLeafConditions(stmt: YangListStmt): void {
    if (!stmt.key) {
      return;
    }
    const keyLeaves = new Map(
      stmt.statements
        .filter((child): child is YangLeafStmt => child instanceof YangLeafStmt)
        .map((child) => [child.name, child])
    );
    for (const keyName of stmt.key.split(/\s+/).filter(Boolean)) {
      const child = keyLeaves.get(keyName);
      if (child === undefined) {
        throw new YangSemanticError(
          `List '${stmt.name}': key leaf '${keyName}' does not exist ` +
            "(RFC 7950: each list key name must refer to a child leaf)."
        );
      }
      let illegal: string | undefined;
      if (child.when !== undefined) {
        illegal = "when";
      } else if (child.if_features.length > 0) {
        illegal = "if-feature";
      }
      if (illegal === undefined) {
        continue;
      }
      throw new YangSemanticError(
        `List '${stmt.name}': key leaf '${child.name}' must not have '${illegal}' ` +
          "(RFC 7950: 'when' and 'if-feature' are illegal on list keys)."
      );
    }
  }

  parse_list(tokens: TokenStream, context: ParserContext): YangListStmt {
    tokens.consume(kw.LIST);
    const name = tokens.consume();
    const stmt = new YangListStmt({ name });
    if (tokens.consume_if_type(YangTokenType.LBRACE)) {
      const child = context.push_parent(stmt);
      while (tokens.has_more() && tokens.peek_type() !== YangTokenType.RBRACE) {
        this.parsers.parseStatement(tokens, child);
      }
      tokens.consume_type(YangTokenType.RBRACE);
    }
    this.validateKeyLeafConditions(stmt);
    this.parsers.add_to_parent_or_module(context, stmt);
    tokens.consume_if_type(YangTokenType.SEMICOLON);
    return stmt;
  }
}
