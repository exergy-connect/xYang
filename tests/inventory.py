"""Count test cases from the runners themselves (no hand-maintained registry).

    python tests/inventory.py            # summary
    python tests/inventory.py --by-file  # plus per-file counts
    python tests/inventory.py --json     # machine-readable

Logical cases: a shared conformance instance (tests/cases) counts once even though both runtimes
run it; every other collected Python or TypeScript item counts once for its runtime. Parameterized
items count individually. Collection only: runtime skips (missing optional tools, unset env vars)
show up in the runners' own ``-rs`` output, not here.

The TypeScript count needs ``ts/node_modules`` (``cd ts && npm ci``).

Ontology example tests stay in the logical count. Pull-request CI deselects them
(``pytest -m "not ontology"``, ``npm test`` excludes the TypeScript file) and a published
release runs them; those two execution totals are printed separately.
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
        self.items: list[tuple[str, bool, bool]] = []

    def pytest_collection_finish(self, session) -> None:
        for item in session.items:
            xfail = item.get_closest_marker("xfail") is not None
            ontology = item.get_closest_marker("ontology") is not None
            self.items.append((item.nodeid, xfail, ontology))


def python_items() -> list[tuple[str, bool, bool]]:
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


def _workflow(name: str) -> dict:
    import yaml

    loaded = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text())
    # PyYAML treats the YAML 1.1 key `on` as True.
    if True in loaded and "on" not in loaded:
        loaded["on"] = loaded.pop(True)
    return loaded


def _workflow_matrix_size(name: str, job: str) -> int:
    matrix = _workflow(name)["jobs"][job]["strategy"]["matrix"]
    return len(matrix.get("include") or next(iter(matrix.values())))


def _job_script(name: str, job: str) -> str:
    return "\n".join(step.get("run", "") for step in _workflow(name)["jobs"][job].get("steps") or [])


def _release_runs_ontology() -> bool:
    """True when Ontology example runs on ``release: published`` and executes both suites."""
    wf = _workflow("ontology-example.yml")
    event = wf.get("on") or {}
    types = (event.get("release") or {}).get("types") or []
    if "published" not in types or "pull_request" in event or "push" in event:
        return False
    python = _job_script("ontology-example.yml", "python")
    typescript = _job_script("ontology-example.yml", "typescript")
    return (
        "tests/test_ontology_hypergraph.py" in python
        and "requirements-tools.txt" in python
        and "test:ontology" in typescript
    )


def inventory() -> dict:
    py = python_items()
    ts = ts_items()
    shared = shared_instances()

    py_shared = {nid.split("[", 1)[1][: -1].split(":", 1)[1] for nid, _, _ in py if nid.startswith(SHARED_PY + "::")}
    ts_shared_n = sum(1 for f, _ in ts if f == SHARED_TS)
    py_other = [(nid, x) for nid, x, _ in py if not nid.startswith(SHARED_PY + "::")]
    ts_other = [(f, n) for f, n in ts if f != SHARED_TS]
    ontology_py = sum(1 for _, _, ontology in py if ontology)
    package = json.loads((ROOT / "ts" / "package.json").read_text())
    pr_test_script = package["scripts"]["test"]
    ontology_ts_file = "test/ontology_audit_example.test.ts"
    ontology_ts = sum(1 for f, _ in ts if f == ontology_ts_file)
    pr_excludes_ontology_ts = ontology_ts_file in pr_test_script and "--exclude" in pr_test_script
    pr_excludes_ontology_py = '-m "not ontology"' in _job_script("tests.yml", "pytest")

    if py_shared != shared or ts_shared_n != len(shared):
        raise SystemExit(
            f"shared-case runners disagree with tests/cases: {len(shared)} instances, "
            f"python {len(py_shared)}, typescript {ts_shared_n}"
        )

    if not pr_excludes_ontology_py or not pr_excludes_ontology_ts or not _release_runs_ontology():
        raise SystemExit(
            "ontology routing drifted: "
            f"pytest deselects={pr_excludes_ontology_py}, npm test excludes={pr_excludes_ontology_ts}, "
            f"release runs both={_release_runs_ontology()}"
        )

    py_matrix = _workflow_matrix_size("tests.yml", "pytest")
    ts_matrix = _workflow_matrix_size("tests-ts.yml", "test")
    pr_py = len(py) - ontology_py
    pr_ts = len(ts) - ontology_ts
    return {
        "logical": {
            "total": len(shared) + len(py_other) + len(ts_other),
            "shared_instances": len(shared),
            "python_only": len(py_other),
            "typescript_only": len(ts_other),
        },
        "runner_items": {"python": len(py), "typescript": len(ts)},
        "expected_failures": {
            "python": sum(1 for _, x, _ in py if x),
            "typescript": sum(1 for _, n in ts if "(xfail:" in n),
        },
        "ontology_release_only": {"python": ontology_py, "typescript": ontology_ts},
        "ci_executions_per_pr": {
            "python_matrix": f"{py_matrix} x {pr_py}",
            "node_matrix": f"{ts_matrix} x {pr_ts}",
            "conformance_jobs": f"2 x {len(shared)} (shared cases again, outside the matrices)",
            "ontology_not_included": ontology_py + ontology_ts,
            "total": py_matrix * pr_py + ts_matrix * pr_ts + 2 * len(shared),
        },
        "ci_executions_per_release": {
            "event": "release: published",
            "ontology_python": ontology_py,
            "ontology_typescript": ontology_ts,
            "total": ontology_py + ontology_ts,
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
    lg, ri, xf = inv["logical"], inv["runner_items"], inv["expected_failures"]
    ci, rel, ont = inv["ci_executions_per_pr"], inv["ci_executions_per_release"], inv["ontology_release_only"]
    print(f"logical cases        {lg['total']}")
    print(f"  shared instances   {lg['shared_instances']}  (tests/cases, run by both runtimes)")
    print(f"  python only        {lg['python_only']}")
    print(f"  typescript only    {lg['typescript_only']}")
    print(f"runner items         python {ri['python']}, typescript {ri['typescript']}")
    print(f"expected failures    python {xf['python']}, typescript {xf['typescript']}")
    print(f"ontology, release    python {ont['python']}, typescript {ont['typescript']}  "
          f"(counted above; not run on pull requests)")
    print(f"CI executions per PR {ci['total']}  (python {ci['python_matrix']}, node {ci['node_matrix']}, "
          f"conformance {ci['conformance_jobs']})")
    print(f"CI executions per release ({rel['event']}) {rel['total']}  "
          f"(ontology python {rel['ontology_python']}, typescript {rel['ontology_typescript']})")
    if args.by_file:
        for key in ("python_by_file", "typescript_by_file"):
            print(f"\n{key.replace('_', ' ')}:")
            for name, n in sorted(inv[key].items(), key=lambda kv: (-kv[1], kv[0])):
                print(f"  {n:4d}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
