"""Run ``xyang parse`` and ``xyang-zig parse`` side by side and require the same result.

Usage: ``python zig/tests/cross_check.py [path/to/xyang-zig]`` from the repository root,
with the Python package installed (``pip install -e .``). Exits non-zero on any mismatch.

Checked:
- every ``.yang`` file under ``tests/cases`` and ``examples/meta-model.yang``: exit code,
  stdout and stderr must be identical. A file xyang-zig refuses as unsupported (it needs
  a later phase of #165) must belong to a case listed in ``zig/conformance-pending.txt``,
  and so must a file where Python reports an error or warning from a later phase
  (uses expansion, XPath, XSD patterns) that xyang-zig does not check yet.
- command-line usage errors and ``parse --help``, with the program name normalized.
- the parser dispatch registry against Python's ``dispatch_registry_parity_snapshot()``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "tests" / "cases"
ZIG = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "zig" / "zig-out" / "bin" / "xyang-zig"
RUNNER = ZIG.with_name("xyang-zig-conformance")
UNSUPPORTED = ("xyang-zig cannot ", "xyang-zig does not ")


def run(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=ROOT)
    return proc.returncode, proc.stdout, proc.stderr


def python_cli(*args: str) -> tuple[int, str, str]:
    return run([sys.executable, "-m", "xyang", *args])


def zig_cli(*args: str) -> tuple[int, str, str]:
    return run([str(ZIG), *args])


def pending_cases() -> set[str]:
    lines = (ROOT / "zig" / "conformance-pending.txt").read_text().splitlines()
    return {line.split()[0] for line in lines if line.strip() and not line.startswith("#")}


def main() -> int:
    failures: list[str] = []
    pending = pending_cases()
    files = sorted(CASES.rglob("*.yang")) + [ROOT / "examples" / "meta-model.yang"]
    same = deferred = 0
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        case = path.parent.relative_to(CASES).as_posix() if CASES in path.parents else None
        py, zg = python_cli("parse", str(path)), zig_cli("parse", str(path))
        if py == zg:
            same += 1
            continue
        refused = zg[0] == 1 and any(marker in zg[2] for marker in UNSUPPORTED)
        later_phase_error = py[0] != 0 and zg[0] == 0
        # Same output; Python also logged a warning from a later phase (e.g. uses expansion).
        later_phase_warning = py[:2] == zg[:2] and not zg[2]
        if refused or later_phase_error or later_phase_warning:
            if case in pending:
                deferred += 1
                continue
            failures.append(f"{rel}: differs outside a pending case\n  python: {py}\n  zig:    {zg}")
            continue
        failures.append(f"{rel}: results differ\n  python: {py}\n  zig:    {zg}")

    def normalized(result: tuple[int, str, str]) -> tuple[int, str, str]:
        code, out, err = result
        return code, out.replace("xyang-zig", "xyang"), err.replace("xyang-zig", "xyang")

    usage_calls = [
        ["parse"],
        ["parse", "--include-path"],
        ["parse", "a.yang", "b.yang"],
        ["parse", "--bogus", "x.yang"],
        ["parse", "missing-file.yang"],
        ["parse", "--help"],
        ["parse", "-h"],
    ]
    for args in usage_calls:
        py, zg = python_cli(*args), normalized(zig_cli(*args))
        if args[1:2] in (["a.yang"], ["--bogus"]):
            # The top-level usage line lists every Python command; compare the error line.
            py = (py[0], py[1], py[2].splitlines()[-1])
            zg = (zg[0], zg[1], zg[2].splitlines()[-1])
        if py != zg:
            failures.append(f"xyang {' '.join(args)}: CLI differs\n  python: {py}\n  zig:    {zg}")

    from xyang.parser.dispatch_registry import dispatch_registry_parity_snapshot

    code, out, err = run([str(RUNNER), "--registry-snapshot"])
    if code != 0 or json.loads(out) != dispatch_registry_parity_snapshot():
        failures.append(f"dispatch registry differs from Python\n  zig: {out or err}")

    for failure in failures:
        print(f"FAIL {failure}")
    print(f"{len(files)} files: {same} identical, {deferred} deferred to a pending phase; {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
