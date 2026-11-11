"""Python and TypeScript keyword-dispatch registries agree."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from xyang.parser.dispatch_registry import DISPATCH_REGISTRY, dispatch_registry_parity_snapshot

_ROOT = Path(__file__).resolve().parents[2]

# Every parent the parser dispatches. Adding one in a single language fails this set
# and the snapshot comparison.
_PARENTS = {
    "module",
    "submodule",
    "belongs-to",
    "import",
    "include",
    "typedef",
    "type",
    "pattern",
    "enum",
    "bit",
    "identity",
    "leaf",
    "leaf-list",
    "list",
    "container",
    "grouping",
    "notification",
    "rpc",
    "input",
    "output",
    "choice",
    "case",
    "augment",
    "uses",
    "refine",
    "anydata",
    "anyxml",
    "must",
    "when",
    "feature",
    "if-feature",
    "extension",
    "argument",
    "deviation",
    "revision",
    "extension-invocation",
    "length",
    "range",
}


def test_every_parent_is_in_the_registry():
    assert set(DISPATCH_REGISTRY) == _PARENTS
    for spec in DISPATCH_REGISTRY.values():
        assert spec.rfc
        assert all(isinstance(keyword, str) and keyword for keyword in spec.keywords)


def test_python_and_typescript_dispatch_registries_agree():
    python = dispatch_registry_parity_snapshot()
    completed = subprocess.run(
        ["node", "scripts/dump-dispatch-registry.mjs"],
        cwd=_ROOT / "ts",
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    typescript = json.loads(completed.stdout)
    assert list(python) == list(typescript)
    for name, row in python.items():
        assert typescript[name] == row
