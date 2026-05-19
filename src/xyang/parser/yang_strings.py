"""
RFC 7950 §6.2 quoted string decoding for YANG source text.
"""

from __future__ import annotations


def unescape_yang_quoted_string(content: str, quote: str) -> str:
    """
    Decode the inner text of a YANG single- or double-quoted string.

    Args:
        content: Characters between the opening and closing quote (escapes still present).
        quote: ``"`` or ``'`` — the delimiter that wrapped this string.
    """
    if quote not in ("'", '"'):
        raise ValueError(f"quote must be \"'\" or '\"', got {quote!r}")

    out: list[str] = []
    i = 0
    n = len(content)
    while i < n:
        ch = content[i]
        if ch != "\\" or i + 1 >= n:
            out.append(ch)
            i += 1
            continue
        nxt = content[i + 1]
        if nxt == "\\":
            out.append("\\")
            i += 2
            continue
        if nxt == "n":
            out.append("\n")
            i += 2
            continue
        if nxt == "t":
            out.append("\t")
            i += 2
            continue
        if quote == '"' and nxt == '"':
            out.append('"')
            i += 2
            continue
        if quote == "'" and nxt == "'":
            out.append("'")
            i += 2
            continue
        if nxt in "\r\n":
            i += 2
            if nxt == "\r" and i < n and content[i] == "\n":
                i += 1
            while i < n and content[i] in " \t":
                i += 1
            continue
        # Unrecognized escape: keep backslash and next character (single-quoted patterns).
        out.append("\\")
        out.append(nxt)
        i += 2
    return "".join(out)
