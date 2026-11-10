"""
YANG tokenizer implementation.

Produces tokens according to the minimal YANG grammar (meta-model-grammar.ebnf),
using YangTokenType enum for token kinds.
"""

import re
import sys
from typing import Optional, List

from .parser_context import TokenStream, YangToken, YangTokenType
from .yang_strings import unescape_yang_quoted_string

# Exactly the characters ``str.isspace`` accepts, so a run can be skipped in one match.
_WHITESPACE_RUN = re.compile(
    "[" + "".join(re.escape(chr(c)) for c in range(sys.maxunicode + 1) if chr(c).isspace()) + "]+"
)
# Quoted-string body: a backslash escapes the next character; a trailing backslash is kept.
_QUOTED_BODY = {
    '"': re.compile(r'(?:[^"\\]|\\[\s\S]|\\\Z)*'),
    "'": re.compile(r"(?:[^'\\]|\\[\s\S]|\\\Z)*"),
}


class YangTokenizer:
    """Tokenizer for YANG content. Emits YangToken with grammar-aligned types."""

    # Single-char punctuation; // and /* are skipped before this lookup.
    _PUNCTUATION = {t.value: t for t in YangTokenType if len(t.value) == 1}

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
        append = token_list.append
        punctuation = self._PUNCTUATION
        whitespace_run = _WHITESPACE_RUN.match
        i = 0
        content_len = len(content)
        current_line = 1
        line_start = 0

        def skip_to(end: int) -> None:
            """Move ``i`` to ``end``, counting newlines in the skipped span."""
            nonlocal i, current_line, line_start
            newlines = content.count("\n", i, end)
            if newlines:
                current_line += newlines
                line_start = content.rindex("\n", i, end) + 1
            i = end

        while i < content_len:
            char = content[i]
            if char.isspace():
                skip_to(whitespace_run(content, i).end())
                continue

            if char == "/" and i + 1 < content_len:
                nxt = content[i + 1]
                # Block comment: /* ... */ — recognize and skip (do not emit tokens)
                if nxt == "*":
                    close = content.find("*/", i + 2)
                    skip_to(content_len if close < 0 else close + 2)
                    continue
                # Line comment: // ... EOL (only here — never inside quoted-string lexing)
                if nxt == "/":
                    eol = content.find("\n", i + 2)
                    i = content_len if eol < 0 else eol
                    continue

            # Quoted string (value = inner content, no quotes)
            if char == '"' or char == "'":
                token_start = i
                token_line = current_line
                token_line_start = line_start
                start = i + 1
                end = _QUOTED_BODY[char].match(content, start).end()
                skip_to(end)
                value = unescape_yang_quoted_string(content[start:end], char)
                # RFC 7950 §6.1.3 permits concatenation only between quoted
                # strings. Check for it here, where quoted strings are lexed.
                if (
                    len(token_list) >= 2
                    and token_list[-1].type == YangTokenType.PLUS
                    and token_list[-2].type == YangTokenType.STRING
                ):
                    token_list[-2].value += value
                    token_list.pop()
                else:
                    append(
                        YangToken(
                            type=YangTokenType.STRING,
                            value=value,
                            line_num=token_line,
                            char_pos=token_start - token_line_start,
                        )
                    )
                i += 1
                continue

            # Negative integer: - DIGIT+
            if char == "-" and i + 1 < content_len and content[i + 1].isdigit():
                token_start = i
                j = i + 1
                while j < content_len and content[j].isdigit():
                    j += 1
                append(
                    YangToken(
                        type=YangTokenType.INTEGER,
                        value="-" + content[i + 1 : j],
                        line_num=current_line,
                        char_pos=token_start - line_start,
                    )
                )
                i = j
                continue

            # Unsigned integer or dotted decimal
            # (e.g. yang-version 1.1 — not an identifier in RFC 7950)
            if char.isdigit():
                start = i
                j = i
                while j < content_len and content[j].isdigit():
                    j += 1
                tok_type = YangTokenType.INTEGER
                if j < content_len and content[j] == "." and j + 1 < content_len and content[j + 1].isdigit():
                    j += 1
                    while j < content_len and content[j].isdigit():
                        j += 1
                    tok_type = YangTokenType.DOTTED_NUMBER
                append(
                    YangToken(
                        type=tok_type,
                        value=content[start:j],
                        line_num=current_line,
                        char_pos=start - line_start,
                    )
                )
                i = j
                continue

            # Identifier: ( ALPHA / "_" ) *( ALPHA / DIGIT / "_" / "-" / "." )
            if char.isalpha() or char == "_":
                start = i
                j = i + 1
                while j < content_len:
                    c = content[j]
                    if not (c.isalnum() or c in ("_", "-", ".")):
                        break
                    j += 1
                append(
                    YangToken(
                        type=YangTokenType.IDENTIFIER,
                        value=content[start:j],
                        line_num=current_line,
                        char_pos=start - line_start,
                    )
                )
                i = j
                continue

            # Punctuation (grammar: { } ; : = + /)
            tok_type = punctuation.get(char)
            if tok_type is not None:
                append(YangToken(type=tok_type, value=char, line_num=current_line, char_pos=i - line_start))
            i += 1

        return TokenStream(token_list=token_list, source=content, filename=filename)
