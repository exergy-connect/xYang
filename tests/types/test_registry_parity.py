"""Python and TypeScript built-in registries agree on encoding, bounds, and pattern."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from xyang.types.registry import REGISTRY, registry_parity_snapshot

_ROOT = Path(__file__).resolve().parents[2]


def test_every_builtin_is_in_the_registry():
    expected = {
        "int8",
        "int16",
        "int32",
        "int64",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
        "decimal64",
        "string",
        "boolean",
        "empty",
        "enumeration",
        "bits",
        "binary",
        "union",
        "leafref",
        "identityref",
        "instance-identifier",
    }
    assert set(REGISTRY) == expected
    for spec in REGISTRY.values():
        assert spec.json_encoding in {"number", "string-number", "string", "boolean", "empty"}
        assert callable(spec.to_schema)
        assert callable(spec.from_schema)
        assert callable(spec.check_value)


def test_python_and_typescript_registries_agree():
    python = registry_parity_snapshot()
    completed = subprocess.run(
        ["node", "scripts/dump-builtin-registry.mjs"],
        cwd=_ROOT / "ts",
        check=True,
        capture_output=True,
        text=True,
    )
    typescript = json.loads(completed.stdout)
    assert list(python) == list(typescript)
    for name, row in python.items():
        assert typescript[name] == row
