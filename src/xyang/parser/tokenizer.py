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
        current_line = 1
        line_start = 0

        def advance() -> None:
            nonlocal i, current_line, line_start
            if i < content_len and content[i] == "\n":
                current_line += 1
                line_start = i + 1
            i += 1

        def add_token(
            tok_type: YangTokenType,
            value: str,
            token_start: int,
            line_num: int,
            line_start_pos: int,
        ) -> None:
            char_pos = token_start - line_start_pos
            token_list.append(
                YangToken(
                    type=tok_type,
                    value=value,
                    line_num=line_num,
                    char_pos=char_pos,
                )
            )

        while i < content_len:
            if content[i].isspace():
                advance()
                continue

            char = content[i]

            # Quoted string (value = inner content, no quotes)
            if char in ("\"", "'"):
                quote = char
                token_start = i
                token_line = current_line
                token_line_start = line_start
                advance()
                start = i
                while i < content_len:
                    if content[i] == quote:
                        break
                    if content[i] == "\\" and i + 1 < content_len:
                        advance()
                        advance()
                    else:
                        advance()
                add_token(
                    YangTokenType.STRING,
                    content[start:i],
                    token_start,
                    token_line,
                    token_line_start,
                )
                advance()
                continue

            # Identifier or keyword (letter | _ | - | . then alnum | _ | - | .)
            if char.isalnum() or char in ("_", "-", "."):
                token_start = i
                token_line = current_line
                token_line_start = line_start
                start = i
                advance()
                while i < content_len:
                    c = content[i]
                    if not (c.isalnum() or c in ("_", "-", ".")):
                        break
                    advance()
                lexeme = content[start:i]
                if lexeme in YANG_KEYWORDS:
                    add_token(YANG_KEYWORDS[lexeme], lexeme, token_start, token_line, token_line_start)
                elif self._is_integer(lexeme):
                    add_token(YangTokenType.INTEGER, lexeme, token_start, token_line, token_line_start)
                else:
                    add_token(YangTokenType.IDENTIFIER, lexeme, token_start, token_line, token_line_start)
                continue

            # Punctuation (grammar: { } ; = + /)
            if char == "{":
                add_token(YangTokenType.LBRACE, "{", i, current_line, line_start)
                advance()
            elif char == "}":
                add_token(YangTokenType.RBRACE, "}", i, current_line, line_start)
                advance()
            elif char == ";":
                add_token(YangTokenType.SEMICOLON, ";", i, current_line, line_start)
                advance()
            elif char == "=":
                add_token(YangTokenType.EQUALS, "=", i, current_line, line_start)
                advance()
            elif char == "+":
                add_token(YangTokenType.PLUS, "+", i, current_line, line_start)
                advance()
            elif char == "/":
                add_token(YangTokenType.SLASH, "/", i, current_line, line_start)
                advance()
            else:
                advance()

        return TokenStream(token_list=token_list, lines=lines, filename=filename)

    @staticmethod
    def _is_integer(lexeme: str) -> bool:
        """True if lexeme is an integer (optional minus + digits)."""
        if not lexeme:
            return False
        if lexeme[0] == "-":
            return len(lexeme) > 1 and lexeme[1:].isdigit()
        return lexeme.isdigit()
