"""Count test cases from the runners themselves (no hand-maintained registry).

    python tests/inventory.py            # summary
    python tests/inventory.py --by-file  # plus per-file counts
    python tests/inventory.py --json     # machine-readable

Logical cases: a shared conformance instance (tests/cases) counts once even though both runtimes
run it; every other collected Python or TypeScript item counts once for its runtime. Parameterized
items count individually. Collection only: runtime skips (missing optional tools, unset env vars)
show up in the runners' own ``-rs`` output, not here.

The TypeScript count needs ``ts/node_modules`` (``cd ts && npm ci``).
"""

from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "tests" / "cases"
SHARED_PY = "tests/test_cases.py"
SHARED_TS = "test/cases.test.ts"


class _Collector:
    def __init__(self) -> None:
        self.items: list[tuple[str, bool]] = []

    def pytest_collection_finish(self, session) -> None:
        for item in session.items:
            xfail = item.get_closest_marker("xfail") is not None
            self.items.append((item.nodeid, xfail))


def python_items() -> list[tuple[str, bool]]:
    collector = _Collector()
    args = ["--collect-only", "-p", "no:cacheprovider", "-p", "no:terminal", str(ROOT / "tests")]
    code = pytest.main(args, plugins=[collector])
    if code != 0:
        raise SystemExit(f"pytest collection failed with exit code {code}")
    return collector.items


def ts_items() -> list[tuple[str, str]]:
    proc = subprocess.run(
        ["npx", "vitest", "list", "--json"], cwd=ROOT / "ts", capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise SystemExit(f"vitest list failed ({proc.returncode}):\n{proc.stderr}")
    return [(Path(e["file"]).relative_to(ROOT / "ts").as_posix(), e["name"]) for e in json.loads(proc.stdout)]


def shared_instances() -> set[str]:
    out = set()
    for f in sorted(CASES.rglob("case.json")):
        cid = f.parent.relative_to(CASES).as_posix()
        for inst in json.loads(f.read_text()).get("instances") or [{"name": "schema error"}]:
            out.add(f"{cid}:{inst['name']}")
    return out


def _workflow_matrix_size(name: str, job: str) -> int:
    import yaml

    wf = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text())
    matrix = wf["jobs"][job]["strategy"]["matrix"]
    return len(matrix.get("include") or next(iter(matrix.values())))


def inventory() -> dict:
    py = python_items()
    ts = ts_items()
    shared = shared_instances()

    py_shared = {nid.split("[", 1)[1][: -1].split(":", 1)[1] for nid, _ in py if nid.startswith(SHARED_PY + "::")}
    ts_shared_n = sum(1 for f, _ in ts if f == SHARED_TS)
    py_other = [(nid, x) for nid, x in py if not nid.startswith(SHARED_PY + "::")]
    ts_other = [(f, n) for f, n in ts if f != SHARED_TS]

    if py_shared != shared or ts_shared_n != len(shared):
        raise SystemExit(
            f"shared-case runners disagree with tests/cases: {len(shared)} instances, "
            f"python {len(py_shared)}, typescript {ts_shared_n}"
        )

    py_matrix = _workflow_matrix_size("tests.yml", "pytest")
    ts_matrix = _workflow_matrix_size("tests-ts.yml", "test")
    return {
        "logical": {
            "total": len(shared) + len(py_other) + len(ts_other),
            "shared_instances": len(shared),
            "python_only": len(py_other),
            "typescript_only": len(ts_other),
        },
        "runner_items": {"python": len(py), "typescript": len(ts)},
        "expected_failures": {
            "python": sum(1 for _, x in py if x),
            "typescript": sum(1 for _, n in ts if "(xfail:" in n),
        },
        "ci_executions_per_pr": {
            "python_matrix": f"{py_matrix} x {len(py)}",
            "node_matrix": f"{ts_matrix} x {len(ts)}",
            "conformance_jobs": f"2 x {len(shared)} (shared cases again, outside the matrices)",
            "total": py_matrix * len(py) + ts_matrix * len(ts) + 2 * len(shared),
        },
        "python_by_file": collections.Counter(nid.split("::", 1)[0] for nid, _ in py_other),
        "typescript_by_file": collections.Counter(f for f, _ in ts_other),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--by-file", action="store_true", help="list runtime-specific counts per file")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args(argv)
    inv = inventory()
    if args.json:
        print(json.dumps(inv, indent=2))
        return 0
    lg, ri, xf, ci = inv["logical"], inv["runner_items"], inv["expected_failures"], inv["ci_executions_per_pr"]
    print(f"logical cases        {lg['total']}")
    print(f"  shared instances   {lg['shared_instances']}  (tests/cases, run by both runtimes)")
    print(f"  python only        {lg['python_only']}")
    print(f"  typescript only    {lg['typescript_only']}")
    print(f"runner items         python {ri['python']}, typescript {ri['typescript']}")
    print(f"expected failures    python {xf['python']}, typescript {xf['typescript']}")
    print(f"CI executions per PR {ci['total']}  (python {ci['python_matrix']}, node {ci['node_matrix']}, "
          f"conformance {ci['conformance_jobs']})")
    if args.by_file:
        for key in ("python_by_file", "typescript_by_file"):
            print(f"\n{key.replace('_', ' ')}:")
            for name, n in sorted(inv[key].items(), key=lambda kv: (-kv[1], kv[0])):
                print(f"  {n:4d}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
