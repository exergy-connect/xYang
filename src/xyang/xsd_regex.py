"""
Translate YANG ``pattern`` arguments (XSD regular expressions, RFC 7950 §9.4.5,
XML Schema Part 2 Appendix F) into compiled Python ``re`` patterns.

Supported beyond plain characters, classes, groups, ``|`` and quantifiers:
``\\p{X}`` / ``\\P{X}`` for Unicode general categories, ``\\i`` / ``\\I`` / ``\\c`` / ``\\C``
(XML name characters), and the XSD meanings of ``.``, ``\\d``, ``\\s``, ``\\w`` and their
negations. The whole pattern is anchored. A backslash before any other ASCII printable
non-alphanumeric character is a literal of that character (#204). Other XSD constructs
(block escapes such as ``\\p{IsBasicLatin}``, class subtraction ``[a-z-[aeiou]]``, and an
undefined letter or digit escape such as ``\\q``) raise :class:`YangSemanticError`.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from functools import lru_cache
from typing import Dict, List, Tuple

from .errors import YangSemanticError

Ranges = List[Tuple[int, int]]

MAX_CP = sys.maxunicode

GENERAL_CATEGORIES = {
    "L": ("Lu", "Ll", "Lt", "Lm", "Lo"),
    "M": ("Mn", "Mc", "Me"),
    "N": ("Nd", "Nl", "No"),
    "P": ("Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po"),
    "Z": ("Zs", "Zl", "Zp"),
    "S": ("Sm", "Sc", "Sk", "So"),
    "C": ("Cc", "Cf", "Co", "Cn"),
}
_SUBCATEGORIES = {sub for subs in GENERAL_CATEGORIES.values() for sub in subs}

# XML 1.0 (5th ed.) NameStartChar / NameChar.
_NAME_START: Ranges = [
    (0x3A, 0x3A), (0x41, 0x5A), (0x5F, 0x5F), (0x61, 0x7A), (0xC0, 0xD6), (0xD8, 0xF6),
    (0xF8, 0x2FF), (0x370, 0x37D), (0x37F, 0x1FFF), (0x200C, 0x200D), (0x2070, 0x218F),
    (0x2C00, 0x2FEF), (0x3001, 0xD7FF), (0xF900, 0xFDCF), (0xFDF0, 0xFFFD), (0x10000, 0xEFFFF),
]
_NAME_CHAR: Ranges = _NAME_START + [
    (0x2D, 0x2E), (0x30, 0x39), (0xB7, 0xB7), (0x300, 0x36F), (0x203F, 0x2040),
]
_XSD_SPACE: Ranges = [(0x9, 0xA), (0xD, 0xD), (0x20, 0x20)]
_XSD_DOT_EXCLUDED: Ranges = [(0xA, 0xA), (0xD, 0xD)]

# Single-character escapes (XSD SingleCharEsc).
_SINGLE_ESCAPES = {"n": 0xA, "r": 0xD, "t": 0x9}
_SINGLE_ESCAPE_LITERALS = set("\\|.-^?*+{}()[]")


def _is_literal_punctuation(ch: str) -> bool:
    """A backslash before this character is a literal of it.

    XSD ``SingleCharEsc`` punctuation, plus any other ASCII printable
    non-alphanumeric (#204). Letters and digits are defined escapes or errors.
    """
    if ch in _SINGLE_ESCAPE_LITERALS:
        return True
    o = ord(ch)
    return 0x20 <= o <= 0x7E and not ch.isalnum()


def _normalize(ranges: Ranges) -> Ranges:
    out: Ranges = []
    for lo, hi in sorted(ranges):
        if out and lo <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def _complement(ranges: Ranges) -> Ranges:
    out: Ranges = []
    nxt = 0
    for lo, hi in _normalize(ranges):
        if lo > nxt:
            out.append((nxt, lo - 1))
        nxt = hi + 1
    if nxt <= MAX_CP:
        out.append((nxt, MAX_CP))
    return out


@lru_cache(maxsize=1)
def _category_table() -> Dict[str, Ranges]:
    """Code point ranges per two-letter general category, built once."""
    table: Dict[str, Ranges] = {}
    start = 0
    current = unicodedata.category(chr(0))
    for cp in range(1, MAX_CP + 1):
        cat = unicodedata.category(chr(cp))
        if cat != current:
            table.setdefault(current, []).append((start, cp - 1))
            start, current = cp, cat
    table.setdefault(current, []).append((start, MAX_CP))
    return table


@lru_cache(maxsize=None)
def _category_ranges(name: str) -> Tuple[Tuple[int, int], ...]:
    table = _category_table()
    subs = GENERAL_CATEGORIES.get(name, (name,))
    ranges: Ranges = []
    for sub in subs:
        ranges.extend(table.get(sub, []))
    return tuple(_normalize(ranges))


def _render(ranges: Ranges) -> str:
    """Class body (no brackets) for code point ranges."""
    parts = []
    for lo, hi in ranges:
        parts.append(f"\\U{lo:08X}" if lo == hi else f"\\U{lo:08X}-\\U{hi:08X}")
    return "".join(parts)


class _Translator:
    def __init__(self, pattern: str) -> None:
        self.src = pattern
        self.pos = 0

    def unsupported(self, construct: str) -> YangSemanticError:
        return YangSemanticError(f"unsupported XSD regex construct {construct!r} in pattern {self.src!r}")

    def peek(self, offset: int = 0) -> str:
        i = self.pos + offset
        return self.src[i] if i < len(self.src) else ""

    def escape_ranges(self) -> Tuple[Ranges, bool]:
        """Parse an escape at ``pos`` (after ``\\``) into ranges; second item is "negated"."""
        ch = self.peek()
        if not ch:
            raise self.unsupported("\\")
        self.pos += 1
        if ch in "pP":
            if self.peek() != "{":
                raise self.unsupported("\\" + ch)
            end = self.src.find("}", self.pos)
            if end < 0:
                raise self.unsupported(self.src[self.pos - 2 :])
            name = self.src[self.pos + 1 : end]
            self.pos = end + 1
            if name not in GENERAL_CATEGORIES and name not in _SUBCATEGORIES:
                raise self.unsupported(f"\\{ch}{{{name}}}")
            return list(_category_ranges(name)), ch == "P"
        if ch in _SINGLE_ESCAPES:
            cp = _SINGLE_ESCAPES[ch]
            return [(cp, cp)], False
        if _is_literal_punctuation(ch):
            return [(ord(ch), ord(ch))], False
        if ch in "dD":
            return list(_category_ranges("Nd")), ch == "D"
        if ch in "sS":
            return list(_XSD_SPACE), ch == "S"
        if ch in "wW":
            excluded = list(_category_ranges("P")) + list(_category_ranges("Z")) + list(_category_ranges("C"))
            return _normalize(excluded), ch == "w"
        if ch in "iI":
            return list(_NAME_START), ch == "I"
        if ch in "cC":
            return list(_NAME_CHAR), ch == "C"
        raise self.unsupported("\\" + ch)

    def class_atom(self) -> Ranges:
        ch = self.peek()
        if ch == "\\":
            self.pos += 1
            ranges, negated = self.escape_ranges()
            return _complement(ranges) if negated else ranges
        if ch == "[":
            raise self.unsupported("[")
        self.pos += 1
        return [(ord(ch), ord(ch))]

    def char_class(self) -> str:
        """Parse ``[...]`` at ``pos`` (after ``[``)."""
        start = self.pos - 1
        negated = self.peek() == "^"
        if negated:
            self.pos += 1
        ranges: Ranges = []
        first = True
        while True:
            ch = self.peek()
            if not ch:
                raise YangSemanticError(f"unterminated character class in pattern {self.src!r}")
            if ch == "]" and not first:
                self.pos += 1
                break
            if ch == "-" and self.peek(1) == "[":
                end = self.src.find("]", self.pos)
                raise self.unsupported(self.src[start : end + 2 if end >= 0 else len(self.src)])
            first = False
            single = ch != "\\" or (self.peek(1) not in "pPdDsSwWiIcC")
            lo_ranges = self.class_atom()
            if single and self.peek() == "-" and self.peek(1) not in ("]", "["):
                self.pos += 1
                hi_ranges = self.class_atom()
                if (
                    len(lo_ranges) != 1
                    or len(hi_ranges) != 1
                    or lo_ranges[0][0] != lo_ranges[0][1]
                    or hi_ranges[0][0] != hi_ranges[0][1]
                ):
                    raise self.unsupported(self.src[start : self.pos])
                lo, hi = lo_ranges[0][0], hi_ranges[0][1]
                if hi < lo:
                    raise YangSemanticError(f"invalid character range in pattern {self.src!r}")
                ranges.append((lo, hi))
            else:
                ranges.extend(lo_ranges)
        ranges = _normalize(ranges)
        if negated:
            ranges = _complement(ranges)
        return f"[{_render(ranges)}]" if ranges else "(?!)"

    def translate(self) -> str:
        out: List[str] = []
        while self.pos < len(self.src):
            ch = self.peek()
            if ch == "\\":
                self.pos += 1
                ranges, negated = self.escape_ranges()
                ranges = _complement(ranges) if negated else ranges
                out.append(f"[{_render(ranges)}]" if ranges else "(?!)")
            elif ch == "[":
                self.pos += 1
                out.append(self.char_class())
            elif ch == ".":
                self.pos += 1
                out.append(f"[{_render(_complement(_XSD_DOT_EXCLUDED))}]")
            elif ch == "(":
                if self.peek(1) == "?":
                    raise self.unsupported("(?")
                self.pos += 1
                out.append("(?:")
            elif ch in "^$":
                self.pos += 1
                out.append(re.escape(ch))
            elif ch in "|)*+?":
                self.pos += 1
                out.append(ch)
            elif ch == "{":
                m = re.compile(r"\{\d+(,\d*)?\}").match(self.src, self.pos)
                if not m:
                    raise self.unsupported("{")
                self.pos = m.end()
                out.append(m.group(0))
            else:
                self.pos += 1
                out.append(re.escape(ch))
        return "".join(out)


@lru_cache(maxsize=1024)
def translate(pattern: str) -> "re.Pattern[str]":
    """Compile an XSD regex to an anchored Python pattern; use ``.match`` on the result."""
    body = _Translator(pattern).translate()
    try:
        return re.compile(f"(?:{body})\\Z")
    except re.error as exc:
        raise YangSemanticError(f"invalid pattern {pattern!r}: {exc}") from exc
