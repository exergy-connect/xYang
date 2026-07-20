import { makeYangToken, TokenStream, YangToken, YangTokenType } from "./parser-context";
import { unescapeYangQuotedString } from "./yang-strings";

// RFC 7950 §6.1.1: space, tab, carriage return, line feed
const isWhitespace = (ch: string): boolean =>
  ch === " " || ch === "\t" || ch === "\n" || ch === "\r";

const isDigit = (ch: string): boolean => ch >= "0" && ch <= "9";

// Identifier: ( ALPHA / "_" ) *( ALPHA / DIGIT / "_" / "-" / "." )
const isIdentifierStart = (ch: string): boolean =>
  (ch >= "A" && ch <= "Z") || (ch >= "a" && ch <= "z") || ch === "_";

const isIdentifierCont = (ch: string): boolean =>
  isIdentifierStart(ch) || isDigit(ch) || ch === "-" || ch === ".";

// Single-char punctuation; // and /* are skipped before this lookup.
const PUNCTUATION = new Map<string, YangTokenType>(
  (Object.values(YangTokenType) as YangTokenType[])
    .filter((v) => v.length === 1)
    .map((v) => [v, v])
);

export class YangTokenizer {
  tokenize(content: string, filename?: string): TokenStream {
    const token_list: YangToken[] = [];
    let i = 0;
    const content_len = content.length;
    let current_line = 1;
    let line_start = 0;

    const advance = (): void => {
      if (i < content_len && content[i] === "\n") {
        current_line += 1;
        line_start = i + 1;
      }
      i += 1;
    };

    const add_token = (
      tok_type: YangTokenType,
      value: string,
      token_start: number,
      line_num: number,
      line_start_pos: number
    ): void => {
      const char_pos = token_start - line_start_pos;
      token_list.push(makeYangToken(tok_type, value, line_num, char_pos));
    };

    while (i < content_len) {
      const ch = content[i];

      if (isWhitespace(ch)) {
        advance();
        continue;
      }

      // Block comment: /* ... */ — recognize and skip (do not emit tokens)
      if (ch === "/" && i + 1 < content_len && content[i + 1] === "*") {
        advance();
        advance();
        while (i < content_len) {
          if (i + 1 < content_len && content[i] === "*" && content[i + 1] === "/") {
            advance();
            advance();
            break;
          }
          advance();
        }
        continue;
      }

      // Line comment: // ... EOL (only here — never inside quoted-string lexing)
      if (ch === "/" && i + 1 < content_len && content[i + 1] === "/") {
        advance();
        advance();
        while (i < content_len && content[i] !== "\n") {
          advance();
        }
        continue;
      }

      if (ch === '"' || ch === "'") {
        const quote = ch;
        const token_start = i;
        const token_line = current_line;
        const token_line_start = line_start;
        advance();
        const start = i;
        while (i < content_len) {
          if (content[i] === quote) {
            break;
          }
          if (content[i] === "\\" && i + 1 < content_len) {
            advance();
          }
          advance();
        }
        const value = unescapeYangQuotedString(content.slice(start, i), quote as "'" | '"');
        // RFC 7950 §6.1.3 permits concatenation only between quoted strings.
        // Check for it here, where quoted strings are lexed.
        if (
          token_list.at(-1)?.type === YangTokenType.PLUS
          && token_list.at(-2)?.type === YangTokenType.STRING
        ) {
          token_list[token_list.length - 2]!.value += value;
          token_list.pop();
        } else {
          add_token(
            YangTokenType.STRING,
            value,
            token_start,
            token_line,
            token_line_start
          );
        }
        advance();
        continue;
      }

      if (ch === "-" && i + 1 < content_len && isDigit(content[i + 1])) {
        const token_start = i;
        const token_line = current_line;
        const token_line_start = line_start;
        advance();
        const start = i;
        while (i < content_len && isDigit(content[i])) {
          advance();
        }
        add_token(
          YangTokenType.INTEGER,
          `-${content.slice(start, i)}`,
          token_start,
          token_line,
          token_line_start
        );
        continue;
      }

      if (isDigit(ch)) {
        const token_start = i;
        const token_line = current_line;
        const token_line_start = line_start;
        const start = i;
        while (i < content_len && isDigit(content[i])) {
          advance();
        }
        if (i < content_len && content[i] === "." && i + 1 < content_len && isDigit(content[i + 1])) {
          advance();
          while (i < content_len && isDigit(content[i])) {
            advance();
          }
          add_token(
            YangTokenType.DOTTED_NUMBER,
            content.slice(start, i),
            token_start,
            token_line,
            token_line_start
          );
        } else {
          add_token(
            YangTokenType.INTEGER,
            content.slice(start, i),
            token_start,
            token_line,
            token_line_start
          );
        }
        continue;
      }

      if (isIdentifierStart(ch)) {
        const token_start = i;
        const token_line = current_line;
        const token_line_start = line_start;
        const start = i;
        advance();
        while (i < content_len && isIdentifierCont(content[i])) {
          advance();
        }
        const lexeme = content.slice(start, i);
        add_token(YangTokenType.IDENTIFIER, lexeme, token_start, token_line, token_line_start);
        continue;
      }

      const tok_type = PUNCTUATION.get(ch);
      if (tok_type !== undefined) {
        add_token(tok_type, ch, i, current_line, line_start);
      }
      advance();
    }

    return new TokenStream(token_list, content, filename);
  }
}

// Compatibility helper for existing TS parser code.
export function tokenizeYang(source: string): YangToken[] {
  return new YangTokenizer().tokenize(source).token_list;
}

export type { YangToken };
