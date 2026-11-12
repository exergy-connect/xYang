"""Deterministic source line counts for the Python and TypeScript libraries (stdlib only).

A line counts when any code token touches it. Blank lines and comment-only lines
do not count. Python docstrings (first string statement of a module, class, or
function) are treated as comments, matching TypeScript JSDoc. A token that spans
several lines (a multi-line string or template literal) counts every line it
touches.

Python uses the ``tokenize`` and ``ast`` modules. TypeScript uses the small lexer
below: strings, template literals (with nested ``${}``), ``//`` and ``/* */``
comments, and regex literals (recognised from the preceding token).
"""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

SCOPES: dict[str, dict[str, Any]] = {
    "python": {
        "root": "src/xyang",
        "pattern": "**/*.py",
        "excludes": ["src/xyang.egg-info/ (generated packaging metadata, outside the counted root)"],
    },
    "typescript": {
        "root": "ts/src",
        "pattern": "**/*.ts",
        "excludes": ["*.d.ts"],
    },
}

EXCLUDED_ELSEWHERE = [
    "tests/, ts/test/ (tests)",
    "tests/cases/, examples/, benchmarks/ (fixtures and workloads)",
    "ts/dist/, artifacts/, docs/*.js (generated bundles)",
    "ts/node_modules/ (dependencies)",
    "ts/bench/, ts/scripts/ (tooling)",
]

_SKIP_TOKENS = {
    tokenize.COMMENT,
    tokenize.NL,
    tokenize.NEWLINE,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.ENDMARKER,
    tokenize.ENCODING,
}


def count_python(text: str) -> int:
    docstrings: set[tuple[int, int]] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add((first.lineno, first.col_offset))
    lines: set[int] = set()
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type in _SKIP_TOKENS:
            continue
        if tok.type == tokenize.STRING and tok.start in docstrings:
            continue
        lines.update(range(tok.start[0], tok.end[0] + 1))
    return len(lines)


_REGEX_AFTER_KEYWORDS = {
    "return", "typeof", "case", "do", "else", "in", "of", "new", "delete",
    "void", "throw", "yield", "await", "instanceof",
}  # fmt: skip
_REGEX_AFTER_PUNCT = set("([{,;:=!&|?+-*%<>~^}")


def count_typescript(text: str) -> int:
    lines: set[int] = set()
    n = len(text)
    i = 0
    line = 1
    # prev: last significant token, used to tell a regex literal from division.
    prev = ""
    stack: list[str] = []

    def mark(start_line: int, end_line: int) -> None:
        lines.update(range(start_line, end_line + 1))

    def scan_template(i: int, line: int) -> tuple[int, int, bool]:
        """Scan template text from i; return (index, line, entered_substitution)."""
        start = line
        while i < n:
            c = text[i]
            if c == "\\":
                if i + 1 < n and text[i + 1] == "\n":
                    line += 1
                i += 2
                continue
            if c == "\n":
                line += 1
            elif c == "`":
                mark(start, line)
                return i + 1, line, False
            elif c == "$" and i + 1 < n and text[i + 1] == "{":
                mark(start, line)
                return i + 2, line, True
            i += 1
        raise ValueError("unterminated template literal")

    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif c in " \t\r\f\v\ufeff":
            i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise ValueError("unterminated block comment")
            line += text.count("\n", i, end)
            i = end + 2
        elif c in "'\"":
            start = line
            i += 1
            while i < n and text[i] != c:
                if text[i] == "\\":
                    if i + 1 < n and text[i + 1] == "\n":
                        line += 1
                    i += 1
                elif text[i] == "\n":
                    raise ValueError(f"unterminated string on line {start}")
                i += 1
            mark(start, line)
            i += 1
            prev = "str"
        elif c == "`":
            i, line, sub = scan_template(i + 1, line)
            if sub:
                stack.append("tmpl")
                prev = "{"
            else:
                prev = "str"
        elif c == "{":
            mark(line, line)
            stack.append("{")
            prev = "{"
            i += 1
        elif c == "}":
            mark(line, line)
            if stack and stack[-1] == "tmpl":
                stack.pop()
                i, line, sub = scan_template(i + 1, line)
                if sub:
                    stack.append("tmpl")
                    prev = "{"
                else:
                    prev = "str"
            else:
                if stack:
                    stack.pop()
                prev = "}"
                i += 1
        elif c == "/" and (prev == "" or prev in _REGEX_AFTER_PUNCT or prev in _REGEX_AFTER_KEYWORDS):
            mark(line, line)
            i += 1
            in_class = False
            while i < n:
                ch = text[i]
                if ch == "\\":
                    i += 2
                    continue
                if ch == "\n":
                    raise ValueError(f"unterminated regex on line {line}")
                if ch == "[":
                    in_class = True
                elif ch == "]":
                    in_class = False
                elif ch == "/" and not in_class:
                    break
                i += 1
            i += 1
            while i < n and (text[i].isalnum() or text[i] == "_"):
                i += 1
            prev = "regex"
        elif c.isalnum() or c in "_$":
            j = i
            while j < n and (text[j].isalnum() or text[j] in "_$"):
                j += 1
            mark(line, line)
            prev = text[i:j]
            i = j
        else:
            mark(line, line)
            prev = c
            i += 1
    if stack and "tmpl" in stack:
        raise ValueError("unterminated template substitution")
    return len(lines)


def _files(scope: dict[str, Any]) -> list[Path]:
    root = ROOT / scope["root"]
    files = sorted(p for p in root.glob(scope["pattern"]) if p.is_file() and not p.name.endswith(".d.ts"))
    return files


def count_all() -> dict[str, Any]:
    out: dict[str, Any] = {
        "method": (
            "benchmarks/loc.py: nonblank lines touched by a code token; comment-only lines "
            "and Python docstrings excluded (Python: tokenize/ast; TypeScript: built-in lexer)"
        ),
        "excluded": EXCLUDED_ELSEWHERE,
        "languages": {},
    }
    counters = {"python": count_python, "typescript": count_typescript}
    for lang, scope in SCOPES.items():
        files = _files(scope)
        total_lines = 0
        code = 0
        for path in files:
            text = path.read_text(encoding="utf-8")
            total_lines += len(text.splitlines())
            try:
                code += counters[lang](text)
            except (ValueError, SyntaxError, tokenize.TokenError) as exc:
                raise RuntimeError(f"cannot count {path.relative_to(ROOT)}: {exc}") from exc
        out["languages"][lang] = {
            "root": scope["root"],
            "pattern": scope["pattern"],
            "excludes": scope["excludes"],
            "files": len(files),
            "physical_lines": total_lines,
            "code_lines": code,
        }
    return out


if __name__ == "__main__":
    import json

    print(json.dumps(count_all(), indent=2))
