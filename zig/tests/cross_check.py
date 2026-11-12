"""Run ``xyang`` and ``xyang-zig`` side by side and require the same result.

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
- ``xyang validate`` on every case instance, in text and JSON output, rpc and action
  instances included.
- XPath (phase 4) beyond the cases: load errors from the XPath parser and prefix binder,
  and validate runs over the function library, operators, predicates, evaluation errors,
  leafref and instance-identifier.
- operations and extensions (phase 5) beyond the cases: rpc and action calls through
  ``--rpc`` / ``--action`` / ``--output`` / ``--context`` (api-path and wrapper errors,
  list keys, presence, context errors, encodings), RFC 8791 structure instances, and
  ``sx:augment-structure`` from the same and another module (load errors and the tree).
- the native JSON form (phase 6): ``convert`` on every ``.yang`` file under ``tests/cases``
  and ``examples/meta-model.yang`` (exit code, stdout, stderr and the written file byte
  for byte; a ``TypeError`` Python raises from ``copy_yang_statement`` compares as its
  message) and where ``convert`` writes; then, for every converted form and every
  committed ``.yang.json``, the tree ``parse_json_schema`` rebuilds, the
  ``generate(parse(json))`` text byte for byte, ``generate(parse(json)) == json`` for the
  case goldens, and every case instance validated against the reloaded form.
- the full CLI registry (#153, #156): no-argument help, ``--help`` / ``-h``, ``-V`` /
  ``--version`` (and unambiguous prefixes), and ``parse`` / ``validate`` / ``convert``
  help, plus usage errors, with the program name normalized. Help is compared to
  Python 3.14 argparse (``-o, --output PATH``, not 3.12's ``-o PATH, --output PATH``).
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
    return _module_tree(mod)


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


def operation_args(inst: dict, context_path: Path) -> list[str]:
    """``--rpc`` / ``--action`` / ``--output`` / ``--context`` for an instance, as
    ``tests/test_cases.py`` passes them to a CLI; the context is written to ``context_path``."""
    args: list[str] = []
    if inst.get("rpc") is not None:
        args += ["--rpc", inst["rpc"]]
    if inst.get("action") is not None:
        args += ["--action", inst["action"]]
    if inst.get("direction", "input") == "output":
        args.append("--output")
    if "context" in inst:
        context_path.write_text(json.dumps(inst["context"]))
        args += ["--context", str(context_path)]
    return args


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
                data_path.write_text(json.dumps(inst["data"]))
                operation = operation_args(inst, Path(tmp) / "context.json")
                for fmt in ("text", "json"):
                    args = ["validate", "--format", fmt, "--include-path", str(case_dir)]
                    if "features" in spec:
                        args += ["--features", json.dumps(spec["features"])]
                    if inst.get("encoding") == "native":
                        args.append("--native-json")
                    args += [*operation, str(case_dir / spec["module"]), str(data_path)]
                    py, zg = python_cli(*args), zig_cli(*args)
                    if py == zg:
                        same += 1
                        continue
                    if zg[0] == 2 and any(marker in zg[2] for marker in UNSUPPORTED) and case in pending:
                        deferred += 1
                        continue
                    failures.append(f"{case} / {inst['name']} ({fmt}): validate differs\n  python: {py}\n  zig:    {zg}")
    return same, deferred, failures


XPATH_HEADER = 'module x { yang-version 1.1; namespace "urn:x"; prefix x; %s }'

# XPath that must fail when the module loads, with Python's message (parse command).
XPATH_LOAD_ERRORS = [
    'leaf a { type string; must "a = "; }',
    'leaf a { type string; must "(a"; }',
    'leaf a { type string; must "a ]"; }',
    'leaf a { type string; must "1.2.3"; }',
    "leaf a { type string; must \"a == 'b'\"; }",
    'leaf a { type string; must "not ."; }',
    "leaf a { type string; must \"(1, ../a)\"; }",
    'leaf a { type string; must "Foo:Bar(1)"; }',
    'leaf a { type string; when "q:a"; }',
    'leaf a { type leafref { path "/a[. = 1]/*"; } }',
    'leaf a { type leafref { path "../b c"; } }',
    'leaf a { type leafref { path ""; } }',
    'grouping g { leaf a { type string; must "q:y"; } }',
]

# `refine` and `uses`-`augment` targets are XPath schema paths: these load or fail alike.
XPATH_REFINE_PATHS = [
    'grouping g { container c { leaf b { type string; } } } container t { uses g { refine "c[b = 1]/b" { mandatory true; } } }',
    'grouping g { container c { leaf b { type string; } } } container t { uses g { refine "c/./b" { mandatory true; } } }',
    'grouping g { container c { leaf b { type string; } } } container t { uses g { refine "c/*" { mandatory true; } } }',
    'grouping g { container c { leaf b { type string; } } } container t { uses g { augment "c[b = 1]" { leaf z { type string; } } } }',
    'grouping g { container c { leaf b { type string; } } } container t { uses g { augment "c/*" { leaf z { type string; } } } }',
    'grouping g { container c { leaf b { type string; } } } container t { uses g { augment "c[nope()]" { leaf z { type string; } } } }',
]

# One module whose leaves exercise the function library, operators and predicates; each
# instance sets one of them, so a difference names the expression.
XPATH_MODULE = XPATH_HEADER % """
  identity base; identity mid { base base; } identity leaf { base mid; }
  container top {
    leaf s { type string; }
    leaf n { type int32; }
    leaf d { type decimal64 { fraction-digits 2; } }
    leaf flag { type boolean; default false; }
    leaf kind { type identityref { base base; } }
    leaf-list tags { type string; must "string-length(.) < 4" { error-message "tag too long"; } }
    list item { key id; leaf id { type string; } leaf v { type int32; }
      must "count(../item[v = current()/v]) = 1"; }
    leaf arity { type string; must "contains(.)"; }
    leaf empty-must { type string; must ""; }
    leaf ws { type string; must "translate(., 'abc', 'AB') = 'AB'"; }
    leaf num { type string; must "number(.) > 1.5 and boolean(.) and not(. = 'x')"; }
    leaf pos { type string; must "../item[2]/id = 'b'"; }
    leaf nanpos { type string; must "../item[0 div 0]"; }
    leaf zero { type int32; must "1 div . > 0 or -1 div . < 0 or . mod 0 != . mod 0"; }
    leaf cmp { type string; must ". < 'm' and . >= 'b' and '10' > 9"; }
    leaf list-eq { type string; must ". = ('a', 'b', 3)"; }
    leaf concat { type string; must "concat(../s, '-', ../n, '-', ../d, '-', ../flag) = ."; }
    leaf derived { type string; must "derived-from(../kind, 'x:base') and derived-from-or-self(../kind, 'x:mid')"; }
    leaf dflt { type string; must "../flag = false()"; }
    leaf present-when { type string; when "../n > 5"; }
    leaf ref { type leafref { path "../item/id"; } }
    leaf-list refs { type leafref { path "/top/item/id"; } }
    leaf iid { type instance-identifier; }
  }
"""

XPATH_INSTANCES = [
    {"tags": ["ab", "abcd"]},
    {"item": [{"id": "a", "v": 1}, {"id": "b", "v": 1}]},
    {"arity": "z"},
    {"empty-must": "z"},
    {"ws": "abc"},
    {"ws": "cab"},
    {"num": "2"},
    {"num": "1"},
    {"pos": "p", "item": [{"id": "a"}, {"id": "b"}]},
    {"pos": "p", "item": [{"id": "b"}, {"id": "a"}]},
    {"nanpos": "p", "item": [{"id": "a"}]},
    {"zero": 0},
    {"cmp": "c"},
    {"cmp": "z"},
    {"list-eq": "b"},
    {"list-eq": "3"},
    {"list-eq": "c"},
    {"s": "q", "n": 7, "d": "1.5", "flag": True, "concat": "q-7-1.5-True"},
    {"s": "q", "n": 7, "concat": "q-7--False"},
    {"kind": "x:leaf", "derived": "y"},
    {"kind": "x:base", "derived": "y"},
    {"dflt": "y"},
    {"dflt": "y", "flag": True},
    {"n": 3, "present-when": "y"},
    {"n": 9, "present-when": "y"},
    {"ref": "a", "item": [{"id": "a"}]},
    {"ref": "b", "item": [{"id": "a"}]},
    {"refs": ["a", "c"], "item": [{"id": "a"}]},
    {"iid": "/x:top/x:s", "s": "v"},
    {"iid": "/x:top/x:n"},
    {"iid": "top/s"},
    {"iid": "1 + 2"},
    {"iid": "/top["},
    {"iid": "/top[nope(1)]"},
]


def xpath_failures() -> tuple[int, list[str]]:
    """Phase 4 (XPath) beyond the shared cases: load errors from the XPath parser and
    binder, and validate runs over the function library, operators, predicates,
    evaluation errors and references. Exit code, stdout and stderr must be identical."""
    failures: list[str] = []
    same = 0
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp).resolve()
        yang = base / "x.yang"
        for body in XPATH_LOAD_ERRORS:
            yang.write_text(XPATH_HEADER % body)
            py, zg = python_cli("parse", str(yang)), zig_cli("parse", str(yang))
            if py[0] == 0:
                failures.append(f"xpath load error {body!r}: Python loads the module")
            elif py == zg:
                same += 1
            else:
                failures.append(f"xpath load error {body!r}: parse differs\n  python: {py}\n  zig:    {zg}")
        for body in XPATH_REFINE_PATHS:
            yang.write_text(XPATH_HEADER % body)
            py, zg = python_cli("parse", str(yang)), zig_cli("parse", str(yang))
            if py == zg:
                same += 1
            else:
                failures.append(f"refine/augment path {body!r}: parse differs\n  python: {py}\n  zig:    {zg}")
        yang.write_text(XPATH_MODULE)
        data_path = base / "data.json"
        for inst in XPATH_INSTANCES:
            data_path.write_text(json.dumps({"top": inst}))
            for fmt in ("text", "json"):
                args = ["validate", "--format", fmt, str(yang), str(data_path)]
                py, zg = python_cli(*args), zig_cli(*args)
                if py == zg:
                    same += 1
                else:
                    failures.append(f"xpath validate {json.dumps(inst)} ({fmt}): validate differs\n  python: {py}\n  zig:    {zg}")
    return same, failures


STRUCTURE_EXT = (CASES / "encoding" / "structure" / "ietf-yang-structure-ext@2020-06-17.yang").read_text()

# RFC 8791 (phase 5): sx:structure instances and sx:augment-structure, in this module and
# from another one. ``s.yang`` is validated; ``aug.yang`` augments it from outside.
STRUCTURE_FILES = {
    "ietf-yang-structure-ext.yang": STRUCTURE_EXT,
    "s.yang": """module s { %s
  import ietf-yang-structure-ext { prefix sx; }
  feature f;
  identity base; identity one { base base; }
  typedef small { type uint8 { range "0..10"; } }
  sx:structure msg {
    leaf n { type small; default 5; }
    leaf kind { type identityref { base base; } }
    leaf gated { if-feature f; type string; }
    leaf when-n { when "../n > 3"; type string; }
    list items { key id; leaf id { type string; } leaf ref { type leafref { path "../../n"; } } }
    container c { leaf x { type string; mandatory true; } }
    choice ch { leaf a { type string; } leaf b { type string; } }
  }
  sx:structure other { leaf z { type int64; } }
  sx:augment-structure "/s:msg/s:c" { leaf added { type string { length "1..3"; } } }
  sx:augment-structure "/s:other" { if-feature f; when "z > 1"; leaf w { type string; } }
}""" % HEADER.format(name="s", prefix="s"),
    "aug.yang": """module aug { %s
  import ietf-yang-structure-ext { prefix sx; }
  import s { prefix s; }
  sx:augment-structure "/s:msg/s:c" { leaf from-aug { type int8; mandatory true; } }
}""" % HEADER.format(name="aug", prefix="aug"),
    "bad-target.yang": """module bad-target { %s
  import ietf-yang-structure-ext { prefix sx; }
  import s { prefix s; }
  sx:augment-structure "/s:nope" { leaf l { type string; } }
}""" % HEADER.format(name="bt", prefix="bt"),
    "bad-prefix.yang": """module bad-prefix { %s
  import ietf-yang-structure-ext { prefix sx; }
  sx:augment-structure "/q:msg" { leaf l { type string; } }
}""" % HEADER.format(name="bp", prefix="bp"),
    "bad-child.yang": """module bad-child { %s
  import ietf-yang-structure-ext { prefix sx; }
  import s { prefix s; }
  sx:augment-structure "/s:msg/s:zzz" { leaf l { type string; } }
}""" % HEADER.format(name="bc", prefix="bc"),
    "before.yang": """module before { %s
  import ietf-yang-structure-ext { prefix sx; }
  sx:augment-structure "/b:late" { leaf l { type string; } }
  sx:structure late { leaf k { type string; } }
}""" % HEADER.format(name="b", prefix="b"),
}

STRUCTURE_PARSE = ["s.yang", "aug.yang", "bad-target.yang", "bad-prefix.yang", "bad-child.yang", "before.yang"]

STRUCTURE_INSTANCES = [
    {"s:msg": {"n": 11}},
    {"msg": {"n": 3}},
    {"msg": {"kind": "s:one"}},
    {"msg": {"gated": "x"}},
    {"msg": {"c": {}}},
    {"msg": {"n": 2, "when-n": "y"}},
    {"msg": {"n": 4, "when-n": "y"}},
    {"msg": {"a": "1", "b": "2"}},
    {"msg": {"items": [{"id": "a", "ref": "5"}, {"id": "a"}]}},
    {"msg": {"items": [{"id": "a", "ref": "4"}]}},
    {"msg": {"c": {"x": "1", "added": "toolong"}}},
    {"msg": {"c": {"x": "1", "added": "ok"}}},
    {"other": {"z": 5}},
    {"s:other": {"z": "1", "w": "x"}},
    {"other": {"z": "2", "w": "x"}},
    {"msg": {}, "x": 1},
    {"s:msg": 1},
    {"t:msg": {}},
    {"msg": {"bogus": 1}},
]

OPERATION_MODULE = """module op { %s
  identity reason; identity crash { base reason; }
  container sys {
    leaf ver { type decimal64 { fraction-digits 2; } default "1.5"; }
    list slot {
      key "id ok";
      leaf id { type decimal64 { fraction-digits 1; } }
      leaf ok { type boolean; }
      action eject {
        input {
          leaf why { type identityref { base reason; } }
          leaf count { type int64; must ". < ../../id * 10" { error-message "too many"; } }
        }
        output { leaf done { type empty; } }
      }
    }
    choice where { case here { container box { action open; } } }
    container locked { presence "locked"; action unlock { input { leaf code { type string; mandatory true; } } } }
  }
  rpc reboot {
    input {
      leaf delay { type int64; }
      leaf at { type leafref { path "/op:sys/op:slot/op:id"; } }
      must "not(delay) or ../reboot/delay != '0'" { error-message "no zero delay"; }
    }
    output { leaf ok { type empty; } leaf ver { type decimal64 { fraction-digits 2; } must ". >= /sys/ver"; } }
  }
  rpc ping;
}""" % HEADER.format(name="op", prefix="op")

OPERATION_CONTEXT = {"op:sys": {"slot": [{"id": "1.5", "ok": True}, {"id": "2.0", "ok": False}]}}

# (operation options, data, context or None) for ``xyang validate`` on OPERATION_MODULE.
OPERATION_CALLS = [
    (["--rpc", "nope"], {"op:input": {}}, None),
    (["--rpc", "reboot"], {"op:input": {"delay": "5"}}, None),
    (["--rpc", "reboot"], {"op:input": {"delay": 5}}, None),
    (["--rpc", "reboot"], {"op:input": {"delay": "0"}}, None),
    (["--rpc", "reboot"], {"op:input": {"at": "1.5"}}, OPERATION_CONTEXT),
    (["--rpc", "reboot"], {"op:input": {"at": "9.5"}}, OPERATION_CONTEXT),
    (["--rpc", "reboot"], [], None),
    (["--rpc", "reboot"], {}, None),
    (["--rpc", "reboot"], "text", None),
    (["--rpc", "reboot"], {"op:input": {}, "x": 1}, None),
    (["--rpc", "reboot"], {"op:input": "s"}, None),
    (["--rpc", "reboot", "--native-json"], [], None),
    (["--rpc", "reboot", "--native-json"], {"delay": 5}, None),
    (["--rpc", "reboot", "--output"], {"op:output": {"ok": [None]}}, None),
    (["--rpc", "reboot", "--output"], {"op:output": {"ok": None}}, None),
    (["--rpc", "reboot", "--output"], {"op:output": {"ver": "1.25"}}, None),
    (["--rpc", "reboot", "--output"], {"op:output": {"ver": "1.75"}}, None),
    (["--rpc", "ping"], {"op:input": {}}, None),
    (["--rpc", "ping", "--output"], {"op:output": {"x": 1}}, None),
    (["--rpc", "reboot"], {"op:input": {}}, {"op:sys": {"slot": [{"id": "x", "ok": True}]}}),
    (["--rpc", "reboot"], {"op:input": {}}, {"op:sys": {"slot": [{"id": "1.5", "ok": True}, {"id": "1.5", "ok": True}]}}),
    (["--action", "/op:sys/slot=1.5,true/eject"], {"op:input": {"why": "op:crash", "count": "14"}}, OPERATION_CONTEXT),
    (["--action", "/op:sys/slot=1.5,true/eject"], {"op:input": {"count": "15"}}, OPERATION_CONTEXT),
    (["--action", "/op:sys/slot=2.0,false/eject"], {"op:input": {"count": "15"}}, OPERATION_CONTEXT),
    (["--action", "/op:sys/slot=1.50,true/eject"], {"op:input": {}}, OPERATION_CONTEXT),
    (["--action", "/op:sys/slot=1.5,True/eject"], {"op:input": {}}, OPERATION_CONTEXT),
    (["--action", "/op:sys/slot=1.5,true/eject", "--output"], {"op:output": {"done": [None]}}, OPERATION_CONTEXT),
    (["--action", "/op:sys/slot=1.5,true/eject"], {"op:output": {}}, OPERATION_CONTEXT),
    (["--action", "/op:sys/slot=1.5,true/eject", "--native-json"], {"count": 15}, {"sys": {"slot": [{"id": 1.5, "ok": True}]}}),
    (["--action", "/op:sys/box/open"], {"op:input": {}}, {}),
    (["--action", "/op:sys/box/open"], {"op:input": {}}, {"op:sys": {"box": {}}}),
    (["--action", "/op:sys/locked/unlock"], {"op:input": {}}, {"op:sys": {"locked": {}}}),
    (["--action", "/op:sys/locked/unlock"], {"op:input": {"code": "1"}}, {}),
    (["--action", "/op:sys/slot=1.5,true/eject"], {"op:input": {}}, {"op:sys": {"slot": "x"}}),
    (["--action", "/"], {"op:input": {}}, {}),
    (["--action", "op:sys/box/open"], {"op:input": {}}, {}),
    (["--action", "/other:sys/box/open"], {"op:input": {}}, {}),
    (["--action", "/op:sys"], {"op:input": {}}, {}),
    (["--action", "/op:nope/x"], {"op:input": {}}, {}),
    (["--action", "/op:sys/nope/x"], {"op:input": {}}, {}),
    (["--action", "/op:sys/a b"], {"op:input": {}}, {}),
    (["--action", "/op:sys/:x"], {"op:input": {}}, {}),
    (["--action", "/op:sys/slot=1/eject"], {"op:input": {}}, {}),
    (["--action", "/op:sys/slot/eject"], {"op:input": {}}, {}),
    (["--action", "/op:sys=1/box/open"], {"op:input": {}}, {}),
    (["--action", "/op:sys/ver/x"], {"op:input": {}}, {}),
    (["--action", "/op:sys/slot=1.5,true/op:nope"], {"op:input": {}}, {}),
    (["--action", "/op:sys/slot=1.5,true/eject=1"], {"op:input": {}}, {}),
    (["--action", "/op:sys/slot=1.5%2C,true/eject"], {"op:input": {}}, OPERATION_CONTEXT),
    (["--action", "/op:sys/box/open"], {"op:input": {}}, None),
    (["--action", ""], {"op:input": {}}, {}),
    (["--rpc", ""], {"op:input": {}}, None),
    (["--rpc", "reboot"], {"op:input": {}}, []),
]


def operation_failures() -> tuple[int, list[str]]:
    """Phase 5 beyond the shared cases: RFC 8791 structures and augment-structure (load
    errors and instances), and rpc and action calls: api-path errors, wrappers, keys,
    presence, context errors, encodings. Exit code, stdout and stderr must be identical."""
    failures: list[str] = []
    same = 0
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp).resolve()
        for rel, text in STRUCTURE_FILES.items():
            (base / rel).write_text(text)
        for rel in STRUCTURE_PARSE:
            py, zg = python_cli("parse", str(base / rel)), zig_cli("parse", str(base / rel))
            if py == zg:
                same += 1
            else:
                failures.append(f"structure parse {rel}: parse differs\n  python: {py}\n  zig:    {zg}")
        data_path = base / "data.json"
        context_path = base / "context.json"
        for inst in STRUCTURE_INSTANCES:
            data_path.write_text(json.dumps(inst))
            for features in (None, "{}"):
                for fmt in ("text", "json"):
                    args = ["validate", "--format", fmt]
                    if features is not None:
                        args += ["--features", features]
                    args += [str(base / "s.yang"), str(data_path)]
                    py, zg = python_cli(*args), zig_cli(*args)
                    if py == zg:
                        same += 1
                    else:
                        failures.append(f"structure validate {json.dumps(inst)} ({fmt}): validate differs\n  python: {py}\n  zig:    {zg}")
        yang = base / "op.yang"
        yang.write_text(OPERATION_MODULE)
        for options, data, context in OPERATION_CALLS:
            data_path.write_text(json.dumps(data))
            extra = ["--context", str(context_path)] if context is not None else []
            if context is not None:
                context_path.write_text(json.dumps(context))
            for fmt in ("text", "json"):
                args = ["validate", "--format", fmt, *options, *extra, str(yang), str(data_path)]
                py, zg = python_cli(*args), zig_cli(*args)
                if py == zg:
                    same += 1
                else:
                    failures.append(f"operation {options} {json.dumps(data)} context {json.dumps(context)} ({fmt}): validate differs\n  python: {py}\n  zig:    {zg}")
    with tempfile.TemporaryDirectory() as tmp:
        # A case directory as the case runners load it: aug.yang is a sibling of s.yang,
        # so its augment-structure lands in the tree of s.
        case_dir = Path(tmp).resolve() / "structure-augment"
        case_dir.mkdir()
        for rel in ("ietf-yang-structure-ext.yang", "s.yang", "aug.yang"):
            (case_dir / rel).write_text(STRUCTURE_FILES[rel])
        (case_dir / "case.json").write_text(json.dumps({"module": "s.yang", "instances": []}))
        code, out, err = run([str(RUNNER), "--cases", str(case_dir.parent), "--dump-case", "structure-augment"])
        py_tree = python_case_tree(case_dir, "s.yang")
        if code == 0 and json.loads(out) == py_tree and "error" not in py_tree:
            same += 1
        else:
            failures.append(f"augment-structure tree differs from Python\n  python: {json.dumps(py_tree)[:2000]}\n  zig:    {(out or err)[:2000]}")
    return same, failures


def normalized_python(result: tuple[int, str, str]) -> tuple[int, str, str]:
    """A ``TypeError`` Python raises from ``copy_yang_statement`` (a statement class it has
    no copier for) as the ``Error: message`` line xyang-zig prints; warnings before it stay."""
    code, out, err = result
    marker = "Traceback (most recent call last):"
    if marker not in err:
        return result
    head, _, tail = err.partition(marker)
    last = tail.strip().splitlines()[-1]
    kind, _, message = last.partition(": ")
    if kind != "TypeError" or not message.startswith("Unsupported statement type for copy: "):
        return result
    return 1, out, f"{head}Error: {message}\n"


def convert_pair(args: list[str], out_path: Path) -> tuple[tuple[int, str, str, bytes | None], tuple[int, str, str, bytes | None]]:
    """``xyang convert`` then ``xyang-zig convert`` writing the same ``out_path``; each result
    is ``(exit code, stdout, stderr, bytes written or None)``."""
    results = []
    for cli in (python_cli, zig_cli):
        if out_path.exists():
            out_path.unlink()
        code, out, err = cli("convert", *args)
        if cli is python_cli:
            code, out, err = normalized_python((code, out, err))
        results.append((code, out, err, out_path.read_bytes() if out_path.exists() else None))
    return results[0], results[1]


def convert_failures(form_dir: Path) -> tuple[int, int, dict[Path, Path], list[str]]:
    """``xyang convert`` and ``xyang-zig convert`` on every case module and the meta-model,
    with the module's directory on the include path: exit code, stdout, stderr and the
    written ``.yang.json`` must be byte-identical. Each written form is kept in
    ``form_dir`` (module path -> form path) for the reload checks."""
    failures: list[str] = []
    same = divergent = 0
    forms: dict[Path, Path] = {}
    files = sorted(CASES.rglob("*.yang")) + [ROOT / "examples" / "meta-model.yang"]
    for index, path in enumerate(files):
        out_path = form_dir / f"{index:04d}-{path.stem}.yang.json"
        py, zg = convert_pair(["--include-path", str(path.parent), str(path), "-o", str(out_path)], out_path)
        rel = path.relative_to(ROOT).as_posix()
        if py == zg:
            same += 1
            if py[3] is not None:
                out_path.write_bytes(py[3])
                forms[path] = out_path
            continue
        case = path.parent.relative_to(CASES).as_posix() if CASES in path.parents else None
        if case is not None and python_xfail_met(case, path, zg[:3]):
            divergent += 1
            continue
        failures.append(f"{rel}: convert differs\n  python: {py[:3]}\n  zig:    {zg[:3]}")
    return same, divergent, forms, failures


CONVERT_MODULE = """module paths { %s
  container top { leaf a { type string; } }
}""" % HEADER.format(name="paths", prefix="p")


def convert_path_failures() -> tuple[int, list[str]]:
    """Where ``convert`` writes: ``<stem>.yang.json`` beside the input, ``-o`` with the
    suffix added, in a directory it creates, and ``-oPATH``."""
    failures: list[str] = []
    same = 0
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp).resolve()
        yang = base / "src" / "paths.yang"
        yang.parent.mkdir()
        yang.write_text(CONVERT_MODULE)
        calls = [
            ([str(yang)], base / "src" / "paths.yang.json"),
            ([str(yang), "-o", str(base / "out")], base / "out.yang.json"),
            ([str(yang), "-o", str(base / "deep" / "er" / "x.json")], base / "deep" / "er" / "x.yang.json"),
            ([str(yang), f"-o{base / 'attached.yang.json'}"], base / "attached.yang.json"),
            ([str(yang), "--output", str(base / "long.yang.json")], base / "long.yang.json"),
            ([str(base / "missing.yang")], base / "missing.yang.json"),
        ]
        for args, out_path in calls:
            py, zg = convert_pair(args, out_path)
            if py == zg:
                same += 1
            else:
                failures.append(f"xyang convert {' '.join(args)}: differs\n  python: {py[:3]}\n  zig:    {zg[:3]}")
    return same, failures


def _module_tree(mod) -> dict:
    return {
        "name": mod.name,
        "typedefs": sorted(mod.typedefs),
        "identities": sorted(mod.identities),
        "groupings": sorted(mod.groupings),
        "features": sorted(mod.features),
        "imports": {p: m.name for p, m in mod.import_prefixes.items()},
        "statements": [_dump_node(s) for s in mod.statements],
    }


def python_reload(form: Path):
    from xyang.json import parse_json_schema

    return parse_json_schema(form)


def native_json_files() -> list[Path]:
    """The committed native JSON forms: the case goldens and the examples."""
    found = sorted(ROOT.glob("tests/cases/**/expected.yang.json")) + sorted(ROOT.glob("tests/json/data/**/*.yang.json"))
    found += sorted(ROOT.glob("examples/**/*.yang.json")) + sorted(ROOT.glob("skills/**/*.yang.json"))
    return found


def reload_failures(forms: list[Path]) -> tuple[int, int, list[str]]:
    """``parse_json_schema`` (reload) and ``generate(parse(json))`` on every native JSON
    form: the rebuilt tree must equal Python's, the regenerated text must be
    byte-identical to Python's, and it must equal the form as JSON (Python's ``==``) for
    every committed golden. Returns (scenarios identical, round trips equal, failures)."""
    from xyang.json import schema_to_yang_json

    failures: list[str] = []
    same = round_trips = 0
    goldens = set(native_json_files())
    for form in forms:
        rel = form.relative_to(ROOT).as_posix() if ROOT in form.parents else form.name
        code, out, err = run([str(RUNNER), "--reload-tree", str(form)])
        try:
            py_tree = _module_tree(python_reload(form))
        except Exception as exc:  # noqa: BLE001 - a load failure is compared as an error
            py_tree = {"error": str(exc)}
        zig_tree = json.loads(out) if code == 0 and out.strip() else {"runner": err}
        if py_tree == zig_tree:
            same += 1
        else:
            failures.append(f"{rel}: reloaded tree differs from Python\n  python: {json.dumps(py_tree)[:2000]}\n  zig:    {json.dumps(zig_tree)[:2000]}")
        try:
            py_regen = (0, schema_to_yang_json(python_reload(form)))
        except Exception as exc:  # noqa: BLE001 - a failure is compared as its message
            py_regen = (2, f"Error: {exc}\n")
        code, out, err = run([str(RUNNER), "--regenerate", str(form)])
        if (code, out) == py_regen:
            same += 1
        else:
            failures.append(f"{rel}: generate(parse(json)) differs from Python\n  python: {py_regen[1][:2000]}\n  zig:    {(out or err)[:2000]}")
            continue
        if code == 0 and json.loads(out) == json.loads(form.read_text()):
            round_trips += 1
        elif form in goldens and "tests/cases" in rel:
            failures.append(f"{rel}: generate(parse(json)) != json")
    return same, round_trips, failures


def reloaded_validate_failures(forms: dict[Path, Path]) -> tuple[int, list[str]]:
    """Every data instance of a case whose module converts, validated against the module
    reloaded from its native JSON form: ``valid`` and each ``(path, code, message)`` must
    equal Python's ``validate_detailed`` on ``parse_json_schema`` of the same form.
    Operation instances, native encoding and feature sets are covered by the YANG runs."""
    from xyang import YangValidator

    failures: list[str] = []
    same = 0
    with tempfile.TemporaryDirectory() as tmp:
        data_path = Path(tmp) / "data.json"
        for case_json in sorted(CASES.rglob("case.json")):
            spec = json.loads(case_json.read_text())
            form = forms.get(case_json.parent / spec["module"])
            if form is None or "features" in spec:
                continue
            case = case_json.parent.relative_to(CASES).as_posix()
            for inst in spec.get("instances") or []:
                if any(k in inst for k in ("rpc", "action", "context", "encoding")) or "data" not in inst:
                    continue
                data_path.write_text(json.dumps(inst["data"]))
                try:
                    result = YangValidator(python_reload(form)).validate_detailed(inst["data"])
                    expected = {
                        "valid": result["valid"],
                        "errors": [{"path": e["path"], "code": e["code"], "message": e["message"]} for e in result["errors"]],
                    }
                except Exception as exc:  # noqa: BLE001 - compared as an error
                    expected = {"error": str(exc)}
                code, out, err = run([str(RUNNER), "--validate-reloaded", str(form), str(data_path)])
                got = json.loads(out) if code == 0 and out.strip() else {"runner": err}
                if got == expected:
                    same += 1
                else:
                    failures.append(f"{case} / {inst['name']}: validate against the reloaded form differs\n  python: {expected}\n  zig:    {got}")
    return same, failures


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
        [],
        ["--help"],
        ["-h"],
        ["-V"],
        ["--version"],
        ["--ver"],
        ["--v"],
        ["--h"],
        ["--help=1"],
        ["--version=1"],
        ["-h=1"],
        ["-V=1"],
        ["-hV"],
        ["-Vh"],
        ["-help"],
        ["-version"],
        ["-hV=1"],
        ["-Vh=1"],
        ["--=x"],
        ["-x"],
        ["-1"],
        ["--"],
        ["--", "parse"],
        ["-h", "parse"],
        ["-V", "parse"],
        ["--bogus"],
        ["--bogus", "parse"],
        ["--include-path", "x"],
        ["nonesuch"],
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
        ["validate", "missing-file.yang"],
        ["validate", "--rpc", "r", "--action", "/m:a", "examples/meta-model.yang"],
        ["validate", "--output", "examples/meta-model.yang"],
        ["validate", "--features", "[1]", "examples/meta-model.yang"],
        ["validate", "examples/meta-model.yang", "missing-data.json"],
        ["validate", "--help"],
        ["validate", "-h"],
        ["convert"],
        ["convert", "-o"],
        ["convert", "--output"],
        ["convert", "a.yang", "b.yang"],
        ["convert", "--bogus", "x.yang"],
        ["convert", "missing-file.yang"],
        ["convert", "--help"],
        ["convert", "-h"],
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
    xpath_same, xpath_diffs = xpath_failures()
    failures.extend(xpath_diffs)
    operation_same, operation_diffs = operation_failures()
    failures.extend(operation_diffs)
    with tempfile.TemporaryDirectory() as tmp:
        converted, convert_divergent, forms, convert_diffs = convert_failures(Path(tmp))
        failures.extend(convert_diffs)
        path_same, path_diffs = convert_path_failures()
        failures.extend(path_diffs)
        reload_same, round_trips, reload_diffs = reload_failures([*forms.values(), *native_json_files()])
        failures.extend(reload_diffs)
        reloaded_same, reloaded_diffs = reloaded_validate_failures(forms)
        failures.extend(reloaded_diffs)

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
        f"{xpath_same} XPath scenarios identical; "
        f"{operation_same} operation and structure scenarios identical; "
        f"{converted} conversions byte-identical, {convert_divergent} meeting a case Python xfails, "
        f"{path_same} output path scenarios identical; "
        f"{reload_same} reload and regenerate scenarios identical, {round_trips} forms with "
        f"generate(parse(json)) == json; {reloaded_same} validate runs against reloaded forms identical; "
        f"{len(failures)} failure(s)"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
