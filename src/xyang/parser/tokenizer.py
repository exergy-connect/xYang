"""
YANG tokenizer implementation.

Produces tokens according to the minimal YANG grammar (meta-model-grammar.ebnf),
using YangTokenType enum for token kinds.
"""

from typing import Optional, List

from .parser_context import TokenStream, YangToken, YangTokenType


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

            # Block comment: /* ... */ — recognize and skip (do not emit tokens)
            if content[i] == "/" and i + 1 < content_len and content[i + 1] == "*":
                advance()
                advance()
                while i < content_len:
                    if i + 1 < content_len and content[i] == "*" and content[i + 1] == "/":
                        advance()
                        advance()
                        break
                    advance()
                continue

            # Line comment: // ... EOL (only here — never inside quoted-string lexing)
            if content[i] == "/" and i + 1 < content_len and content[i + 1] == "/":
                advance()
                advance()
                while i < content_len and content[i] != "\n":
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

            # Negative integer: - DIGIT+
            if char == "-" and i + 1 < content_len and content[i + 1].isdigit():
                token_start = i
                token_line = current_line
                token_line_start = line_start
                advance()
                start = i
                while i < content_len and content[i].isdigit():
                    advance()
                lexeme = "-" + content[start:i]
                add_token(YangTokenType.INTEGER, lexeme, token_start, token_line, token_line_start)
                continue

            # Unsigned integer or dotted decimal (e.g. yang-version 1.1 — not an identifier in RFC 7950)
            if char.isdigit():
                token_start = i
                token_line = current_line
                token_line_start = line_start
                start = i
                while i < content_len and content[i].isdigit():
                    advance()
                if (
                    i < content_len
                    and content[i] == "."
                    and i + 1 < content_len
                    and content[i + 1].isdigit()
                ):
                    advance()
                    while i < content_len and content[i].isdigit():
                        advance()
                    lexeme = content[start:i]
                    add_token(
                        YangTokenType.DOTTED_NUMBER,
                        lexeme,
                        token_start,
                        token_line,
                        token_line_start,
                    )
                else:
                    lexeme = content[start:i]
                    add_token(YangTokenType.INTEGER, lexeme, token_start, token_line, token_line_start)
                continue

            # Identifier: ( ALPHA / "_" ) *( ALPHA / DIGIT / "_" / "-" / "." )
            if char.isalpha() or char == "_":
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
                add_token(
                    YangTokenType.IDENTIFIER,
                    lexeme,
                    token_start,
                    token_line,
                    token_line_start,
                )
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
            elif char == ":":
                add_token(YangTokenType.COLON, ":", i, current_line, line_start)
                advance()
            elif char == "=":
                add_token(YangTokenType.EQUALS, "=", i, current_line, line_start)
                advance()
            elif char == "+":
                add_token(YangTokenType.PLUS, "+", i, current_line, line_start)
                advance()
            elif char == "/":
                # Not // or /* (handled above)
                add_token(YangTokenType.SLASH, "/", i, current_line, line_start)
                advance()
            else:
                advance()

        return TokenStream(token_list=token_list, source=content, filename=filename)
