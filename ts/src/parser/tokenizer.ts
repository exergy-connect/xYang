import { makeYangToken, TokenStream, YangToken, YangTokenType } from "./parser-context";

const IDENTIFIER_START = /[A-Za-z_]/;
const IDENTIFIER_CONT = /[A-Za-z0-9_.-]/;

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
      if (/\s/.test(content[i])) {
        advance();
        continue;
      }

      if (content[i] === "/" && i + 1 < content_len && content[i + 1] === "*") {
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

      if (content[i] === "/" && i + 1 < content_len && content[i + 1] === "/") {
        advance();
        advance();
        while (i < content_len && content[i] !== "\n") {
          advance();
        }
        continue;
      }

      const ch = content[i];

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
            advance();
          } else {
            advance();
          }
        }
        add_token(
          YangTokenType.STRING,
          content.slice(start, i),
          token_start,
          token_line,
          token_line_start
        );
        advance();
        continue;
      }

      if (ch === "-" && i + 1 < content_len && /\d/.test(content[i + 1])) {
        const token_start = i;
        const token_line = current_line;
        const token_line_start = line_start;
        advance();
        const start = i;
        while (i < content_len && /\d/.test(content[i])) {
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

      if (/\d/.test(ch)) {
        const token_start = i;
        const token_line = current_line;
        const token_line_start = line_start;
        const start = i;
        while (i < content_len && /\d/.test(content[i])) {
          advance();
        }
        if (i < content_len && content[i] === "." && i + 1 < content_len && /\d/.test(content[i + 1])) {
          advance();
          while (i < content_len && /\d/.test(content[i])) {
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

      if (IDENTIFIER_START.test(ch)) {
        const token_start = i;
        const token_line = current_line;
        const token_line_start = line_start;
        const start = i;
        advance();
        while (i < content_len && IDENTIFIER_CONT.test(content[i])) {
          advance();
        }
        const lexeme = content.slice(start, i);
        add_token(YangTokenType.IDENTIFIER, lexeme, token_start, token_line, token_line_start);
        continue;
      }

      if (ch === "{") {
        add_token(YangTokenType.LBRACE, ch, i, current_line, line_start);
        advance();
      } else if (ch === "}") {
        add_token(YangTokenType.RBRACE, ch, i, current_line, line_start);
        advance();
      } else if (ch === ";") {
        add_token(YangTokenType.SEMICOLON, ch, i, current_line, line_start);
        advance();
      } else if (ch === ":") {
        add_token(YangTokenType.COLON, ch, i, current_line, line_start);
        advance();
      } else if (ch === "=") {
        add_token(YangTokenType.EQUALS, ch, i, current_line, line_start);
        advance();
      } else if (ch === "+") {
        add_token(YangTokenType.PLUS, ch, i, current_line, line_start);
        advance();
      } else if (ch === "/") {
        add_token(YangTokenType.SLASH, ch, i, current_line, line_start);
        advance();
      } else {
        advance();
      }
    }

    return new TokenStream(token_list, content, filename);
  }
}

// Compatibility helper for existing TS parser code.
export function tokenizeYang(source: string): YangToken[] {
  return new YangTokenizer().tokenize(source).token_list;
}

export type { YangToken };
