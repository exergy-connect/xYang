"""Run ``xyang parse`` and ``xyang-zig parse`` side by side and require the same result.

Usage: ``python zig/tests/cross_check.py [path/to/xyang-zig]`` from the repository root,
with the Python package installed (``pip install -e .``). Exits non-zero on any mismatch.

Checked:
- every ``.yang`` file under ``tests/cases`` and ``examples/meta-model.yang``: exit code,
  stdout and stderr must be identical. A file xyang-zig refuses as unsupported (it needs
  a later phase of #165) must belong to a case listed in ``zig/conformance-pending.txt``,
  and so must a file where Python reports an error from a later phase (XPath, XSD
  patterns) that xyang-zig does not check yet. A case module whose ``case.json`` records
  an ``xfail`` for Python's missing ``schema_error`` must make xyang-zig fail with the
  case's ``code`` instead.
- module resolution through ``--include-path``: imports, revision-date fallback,
  submodules, foreign ``augment`` and ``deviation``, and their errors and warnings.
- the resolved schema tree of every case that loads in both (as the case runners load
  it, sibling modules included): ``uses``/``refine``/``augment``/``deviation`` results,
  if-feature, when, must, cardinality, defaults and the module's definitions.
- command-line usage errors and ``parse --help``, with the program name normalized.
- the parser dispatch registry against Python's ``dispatch_registry_parity_snapshot()``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
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


def python_xfail_met(case: str, path: Path, zg: tuple[int, str, str]) -> bool:
    """A case whose ``xfail`` records that Python misses its ``schema_error``, and xyang-zig
    fails loading the case module with the expected ``code``."""
    spec = json.loads((CASES / case / "case.json").read_text())
    if not (spec.get("schema_error") and "python" in spec.get("xfail", {})):
        return False
    if path.name != spec["module"]:
        return False
    return zg[0] == 1 and not zg[1] and spec.get("code", "") in zg[2]


HEADER = 'yang-version 1.1; namespace "urn:{name}"; prefix {prefix};'

# Module resolution through the CLI: file name -> source, then (args, ...) to compare.
RESOLUTION_FILES = {
    "main/main.yang": """module main { %s
  import lib { prefix l; revision-date 2023-01-01; }
  include main-sub;
  container top { uses l:g; uses sub-g; leaf n { type sub-t; } }
  augment "/l:box" { leaf extra { type string; } }
  deviation "/l:box/l:gone" { deviate not-supported; }
  deviation "/main:top/main:n" { deviate add { default "x"; } }
}""" % HEADER.format(name="main", prefix="main"),
    "main/main-sub.yang": """submodule main-sub { yang-version 1.1;
  belongs-to main { prefix main; }
  typedef sub-t { type string; units "s"; }
  feature f;
  grouping sub-g { leaf from-sub { if-feature f; type sub-t; } }
}""",
    "lib/lib@2024-06-01.yang": """module lib { %s
  grouping g { leaf a { type string; } }
  container box { leaf gone { type string; } leaf kept { type string; } }
}""" % HEADER.format(name="lib", prefix="lib"),
    "bad/missing-import.yang": "module missing-import { %s import nowhere { prefix n; } }" % HEADER.format(name="m", prefix="m"),
    "bad/cycle-a.yang": "module cycle-a { %s import cycle-b { prefix b; } }" % HEADER.format(name="a", prefix="a"),
    "bad/cycle-b.yang": "module cycle-b { %s import cycle-a { prefix a; } }" % HEADER.format(name="b", prefix="b"),
    "bad/own-prefix.yang": "module own-prefix { %s import cycle-b { prefix o; } }" % HEADER.format(name="o", prefix="o"),
    "bad/dup-prefix.yang": "module dup-prefix { %s import lib { prefix x; } import lib { prefix x; } }" % HEADER.format(name="d", prefix="d"),
    "bad/wrong-owner.yang": "module wrong-owner { %s include other-sub; }" % HEADER.format(name="w", prefix="w"),
    "bad/other-sub.yang": "submodule other-sub { belongs-to someone { prefix s; } }",
    "bad/bad-augment.yang": 'module bad-augment { %s augment "/q:top" { leaf a { type string; } } }' % HEADER.format(name="ba", prefix="ba"),
}

RESOLUTION_CALLS = [
    ["main/main.yang"],
    ["--include-path", "{dir}/lib", "main/main.yang"],
    ["--include-path", "{dir}/lib", "bad/missing-import.yang"],
    ["bad/cycle-a.yang"],
    ["bad/own-prefix.yang"],
    ["--include-path", "{dir}/lib", "bad/dup-prefix.yang"],
    ["bad/wrong-owner.yang"],
    ["bad/bad-augment.yang"],
]


def resolution_failures() -> list[str]:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp).resolve()
        for rel, text in RESOLUTION_FILES.items():
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        for call in RESOLUTION_CALLS:
            args = [a.format(dir=base) if a.startswith("{dir}") else a for a in call]
            args[-1] = str(base / args[-1])
            py, zg = python_cli("parse", *args), zig_cli("parse", *args)
            if py != zg:
                failures.append(f"xyang parse {' '.join(call)}: module resolution differs\n  python: {py}\n  zig:    {zg}")
    return failures


def _kind(stmt) -> str:
    name = type(stmt).__name__.removeprefix("Yang").removesuffix("Stmt")
    return "".join(f"_{c.lower()}" if c.isupper() and i else c.lower() for i, c in enumerate(name))


def _dump_node(stmt) -> dict:
    when = getattr(stmt, "when", None)
    type_stmt = getattr(stmt, "type", None)
    kind = _kind(stmt)
    defaults = getattr(stmt, "defaults", None) if kind == "leaf_list" else None
    return {
        "kind": kind,
        "name": stmt.name,
        "description": stmt.description,
        "units": stmt.units,
        "config": getattr(stmt, "config", None),
        "if_features": list(getattr(stmt, "if_features", [])),
        "when": when.expression if when is not None else None,
        "when_parent": bool(when.evaluate_with_parent_context) if when is not None else False,
        "must": [m.expression for m in getattr(stmt, "must_statements", [])],
        "defining_module": getattr(stmt, "defining_module", None),
        "type": type_stmt.name if kind in ("leaf", "leaf_list") and type_stmt is not None else None,
        "mandatory": getattr(stmt, "mandatory", None) if kind in ("leaf", "choice", "anydata", "anyxml") else None,
        "default": getattr(stmt, "default", None) if kind == "leaf" else None,
        "defaults": list(defaults) if defaults is not None else None,
        "key": getattr(stmt, "key", None) if kind == "list" else None,
        "min": getattr(stmt, "min_elements", None) if kind in ("list", "leaf_list") else None,
        "max": getattr(stmt, "max_elements", None) if kind in ("list", "leaf_list") else None,
        "children": [_dump_node(s) for s in stmt.statements],
        "cases": [_dump_node(c) for c in stmt.cases] if kind == "choice" else None,
    }


def python_case_tree(case_dir: Path, module_file: str) -> dict:
    """The resolved primary module as ``tests/test_cases.py::_load_case_module`` loads it."""
    import logging

    from xyang.parser import YangParser

    # Warnings are compared through the CLI above; keep this report readable.
    logging.disable(logging.WARNING)

    try:
        parser = YangParser(include_path=(case_dir,))
        primary = (case_dir / module_file).resolve()
        mod = parser.parse_file(primary)
        parser._module_cache[primary] = mod
        for sibling in sorted(case_dir.glob("*.yang")):
            if sibling.resolve() == primary or sibling.read_text(encoding="utf-8").lstrip().startswith("submodule"):
                continue
            parser.parse_file(sibling)
    except Exception as exc:  # noqa: BLE001 - any load failure is compared as an error
        return {"error": str(exc)}
    return {
        "name": mod.name,
        "typedefs": sorted(mod.typedefs),
        "identities": sorted(mod.identities),
        "groupings": sorted(mod.groupings),
        "features": sorted(mod.features),
        "imports": {p: m.name for p, m in mod.import_prefixes.items()},
        "statements": [_dump_node(s) for s in mod.statements],
    }


def tree_failures() -> tuple[int, list[str]]:
    """Compare the effective schema tree of every case module that loads in both."""
    failures: list[str] = []
    compared = 0
    for case_json in sorted(CASES.rglob("case.json")):
        case_dir = case_json.parent
        case = case_dir.relative_to(CASES).as_posix()
        spec = json.loads(case_json.read_text())
        code, out, err = run([str(RUNNER), "--cases", str(CASES), "--dump-case", case])
        if code != 0:
            failures.append(f"{case}: tree dump failed: {err}")
            continue
        zig_tree = json.loads(out)
        py_tree = python_case_tree(case_dir, spec["module"])
        if "error" in zig_tree or "error" in py_tree:
            # Load errors are compared by the conformance runner and the parse check above.
            continue
        compared += 1
        if zig_tree != py_tree:
            failures.append(f"{case}: resolved schema tree differs from Python\n  python: {json.dumps(py_tree)[:2000]}\n  zig:    {json.dumps(zig_tree)[:2000]}")
    return compared, failures


def validate_failures() -> tuple[int, int, list[str]]:
    """``xyang validate`` and ``xyang-zig validate`` on every case instance, in both output
    formats: exit code, stdout and stderr must be identical. xyang-zig may refuse an
    instance as unsupported (exit 2) only in a case listed as pending."""
    failures: list[str] = []
    same = deferred = 0
    pending = pending_cases()
    with tempfile.TemporaryDirectory() as tmp:
        data_path = Path(tmp) / "data.json"
        for case_json in sorted(CASES.rglob("case.json")):
            case_dir = case_json.parent
            case = case_dir.relative_to(CASES).as_posix()
            spec = json.loads(case_json.read_text())
            for inst in spec.get("instances") or []:
                if any(key in inst for key in ("rpc", "action", "context", "usage_error")):
                    continue
                data_path.write_text(json.dumps(inst["data"]))
                for fmt in ("text", "json"):
                    args = ["validate", "--format", fmt, "--include-path", str(case_dir)]
                    if "features" in spec:
                        args += ["--features", json.dumps(spec["features"])]
                    if inst.get("encoding") == "native":
                        args.append("--native-json")
                    args += [str(case_dir / spec["module"]), str(data_path)]
                    py, zg = python_cli(*args), zig_cli(*args)
                    if py == zg:
                        same += 1
                        continue
                    if zg[0] == 2 and any(marker in zg[2] for marker in UNSUPPORTED) and case in pending:
                        deferred += 1
                        continue
                    failures.append(f"{case} / {inst['name']} ({fmt}): validate differs\n  python: {py}\n  zig:    {zg}")
    return same, deferred, failures


def main() -> int:
    failures: list[str] = []
    pending = pending_cases()
    files = sorted(CASES.rglob("*.yang")) + [ROOT / "examples" / "meta-model.yang"]
    same = deferred = divergent = 0
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        case = path.parent.relative_to(CASES).as_posix() if CASES in path.parents else None
        py, zg = python_cli("parse", str(path)), zig_cli("parse", str(path))
        if py == zg:
            same += 1
            continue
        refused = zg[0] == 1 and any(marker in zg[2] for marker in UNSUPPORTED)
        later_phase_error = py[0] != 0 and zg[0] == 0
        if refused or later_phase_error:
            if case in pending:
                deferred += 1
                continue
            failures.append(f"{rel}: differs outside a pending case\n  python: {py}\n  zig:    {zg}")
            continue
        if case is not None and python_xfail_met(case, path, zg):
            divergent += 1
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
        ["validate"],
        ["validate", "--format"],
        ["validate", "--format", "xml", "a.yang"],
        ["validate", "--a", "x", "a.yang"],
        ["validate", "--native-json=1", "a.yang"],
        ["validate", "a.yang", "b.json", "c.json"],
        ["validate", "a.yang", "--format", "json", "b.json"],
        ["validate", "missing-file.yang"],
        ["validate", "--rpc", "r", "--action", "/m:a", "examples/meta-model.yang"],
        ["validate", "--output", "examples/meta-model.yang"],
        ["validate", "--features", "[1]", "examples/meta-model.yang"],
        ["validate", "examples/meta-model.yang", "missing-data.json"],
        ["validate", "--help"],
        ["validate", "-h"],
    ]
    for args in usage_calls:
        py, zg = python_cli(*args), normalized(zig_cli(*args))
        if py[0] == 2 and "unrecognized arguments" in py[2]:
            # The top-level usage line lists every Python command; compare the error line.
            py = (py[0], py[1], py[2].splitlines()[-1])
            zg = (zg[0], zg[1], zg[2].splitlines()[-1])
        if py != zg:
            failures.append(f"xyang {' '.join(args)}: CLI differs\n  python: {py}\n  zig:    {zg}")

    failures.extend(resolution_failures())
    trees, tree_diffs = tree_failures()
    failures.extend(tree_diffs)
    validated, validate_deferred, validate_diffs = validate_failures()
    failures.extend(validate_diffs)

    from xyang.parser.dispatch_registry import dispatch_registry_parity_snapshot

    code, out, err = run([str(RUNNER), "--registry-snapshot"])
    if code != 0 or json.loads(out) != dispatch_registry_parity_snapshot():
        failures.append(f"dispatch registry differs from Python\n  zig: {out or err}")

    for failure in failures:
        print(f"FAIL {failure}")
    print(
        f"{len(files)} files: {same} identical, {deferred} deferred to a pending phase, "
        f"{divergent} meeting a case Python xfails; {len(RESOLUTION_CALLS)} resolution scenarios; "
        f"{trees} resolved case trees identical to Python's unless listed; "
        f"{validated} validate runs identical, {validate_deferred} deferred to a pending phase; "
        f"{len(failures)} failure(s)"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
