"""Generate ``zig/src/unicode_categories.zig`` from Python's ``unicodedata``.

``src/xyang/xsd_regex.py`` builds its ``\\p{X}`` ranges from ``unicodedata.category``; the
Zig port reads the same data from this table so both accept the same code points.

Usage: ``python3 zig/tools/gen_unicode_categories.py`` from the repository root. The
Unicode version is the one of the running Python and is recorded in the output.
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

CATEGORIES = [
    "Lu", "Ll", "Lt", "Lm", "Lo",
    "Mn", "Mc", "Me",
    "Nd", "Nl", "No",
    "Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po",
    "Zs", "Zl", "Zp",
    "Sm", "Sc", "Sk", "So",
    "Cc", "Cf", "Cs", "Co", "Cn",
]


def runs() -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    current = None
    for cp in range(sys.maxunicode + 1):
        cat = CATEGORIES.index(unicodedata.category(chr(cp)))
        if cat != current:
            out.append((cp, cat))
            current = cat
    return out


def main() -> None:
    table = runs()
    lines = [
        "//! Unicode general category of every code point, as runs (generated; do not edit).",
        "//!",
        f"//! Source: Python `unicodedata` {unicodedata.unidata_version}, through",
        "//! `zig/tools/gen_unicode_categories.py`. Each entry is `start << 5 | category`; a run",
        "//! lasts until the next entry's start. `CATEGORIES[category]` is the two-letter name.",
        "",
        f'pub const UNICODE_VERSION = "{unicodedata.unidata_version}";',
        "",
        "pub const CATEGORIES = [_][]const u8{ " + ", ".join(f'"{c}"' for c in CATEGORIES) + " };",
        "",
        "pub const RUNS = [_]u32{",
    ]
    per_line = 10
    cells = [f"0x{(start << 5) | cat:x}," for start, cat in table]
    width = max(len(cell) for cell in cells) + 1
    for i in range(0, len(cells), per_line):
        chunk = cells[i : i + per_line]
        # Column alignment as `zig fmt` writes it.
        lines.append("    " + "".join(cell.ljust(width) for cell in chunk[:-1]) + chunk[-1])
    lines.append("};")
    lines.append("")
    out = Path(__file__).resolve().parents[1] / "src" / "unicode_categories.zig"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({len(table)} runs)")


if __name__ == "__main__":
    main()
