"""
YANG tokenizer implementation.

Produces tokens according to the minimal YANG grammar (meta-model-grammar.ebnf),
using YangTokenType enum for token kinds.
"""

from typing import Optional, List

from .parser_context import TokenStream, YangToken, YangTokenType, YANG_KEYWORDS


class YangTokenizer:
    """Tokenizer for YANG content. Emits YangToken with grammar-aligned types."""

    def tokenize(self, content: str, filename: Optional[str] = None) -> TokenStream:
        """
        Tokenize YANG content and return a TokenStream.

        Args:
            content: YANG file content
            filename: Optional filename for error reporting

        Returns:
            TokenStream with typed tokens and position information
        """
        lines = content.split("\n")

        # Remove single-line comments, keep line structure for positions
        cleaned_lines = []
        for line in lines:
            comment_idx = line.find("//")
            if comment_idx >= 0:
                line = line[:comment_idx]
            cleaned_lines.append(line.rstrip())

        content = "\n".join(cleaned_lines)

        token_list: List[YangToken] = []
        i = 0
        content_len = len(content)

        # Line map: character position of start of each line
        line_map = [0]
        for j, char in enumerate(content):
            if char == "\n":
                line_map.append(j + 1)

        def get_line_num(pos: int) -> int:
            for line_idx, line_start in enumerate(line_map):
                if line_start > pos:
                    return line_idx
            return len(line_map)

        def add_token(tok_type: YangTokenType, value: str, token_start: int) -> None:
            line_num = get_line_num(token_start)
            char_pos = token_start - line_map[line_num - 1] if line_num > 0 else 0
            token_list.append(YangToken(type=tok_type, value=value, line_num=line_num, char_pos=char_pos))

        while i < content_len:
            if content[i].isspace():
                i += 1
                continue

            char = content[i]

            # Quoted string (value = inner content, no quotes)
            if char in ("\"", "'"):
                quote = char
                token_start = i
                i += 1
                start = i
                while i < content_len:
                    if content[i] == quote:
                        break
                    if content[i] == "\\" and i + 1 < content_len:
                        i += 2
                    else:
                        i += 1
                add_token(YangTokenType.STRING, content[start:i], token_start)
                i += 1
                continue

            # Identifier or keyword (letter | _ | - | . then alnum | _ | - | .)
            if char.isalnum() or char in ("_", "-", "."):
                token_start = i
                start = i
                i += 1
                while i < content_len:
                    c = content[i]
                    if not (c.isalnum() or c in ("_", "-", ".")):
                        break
                    i += 1
                lexeme = content[start:i]
                if lexeme in YANG_KEYWORDS:
                    add_token(YANG_KEYWORDS[lexeme], lexeme, token_start)
                elif self._is_integer(lexeme):
                    add_token(YangTokenType.INTEGER, lexeme, token_start)
                else:
                    add_token(YangTokenType.IDENTIFIER, lexeme, token_start)
                continue

            # Punctuation (grammar: { } ; = + /)
            if char == "{":
                add_token(YangTokenType.LBRACE, "{", i)
                i += 1
            elif char == "}":
                add_token(YangTokenType.RBRACE, "}", i)
                i += 1
            elif char == ";":
                add_token(YangTokenType.SEMICOLON, ";", i)
                i += 1
            elif char == "=":
                add_token(YangTokenType.EQUALS, "=", i)
                i += 1
            elif char == "+":
                add_token(YangTokenType.PLUS, "+", i)
                i += 1
            elif char == "/":
                add_token(YangTokenType.SLASH, "/", i)
                i += 1
            else:
                i += 1

        return TokenStream(token_list=token_list, lines=lines, filename=filename)

    @staticmethod
    def _is_integer(lexeme: str) -> bool:
        """True if lexeme is an integer (optional minus + digits)."""
        if not lexeme:
            return False
        if lexeme[0] == "-":
            return len(lexeme) > 1 and lexeme[1:].isdigit()
        return lexeme.isdigit()
