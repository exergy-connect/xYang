"""CLI --version matches the installed package version."""

from __future__ import annotations

import importlib.metadata
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def test_cli_version_matches_package_version() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    result = subprocess.run(
        [sys.executable, "-m", "xyang", "--version"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
        check=False,
    )
    expected = f"xyang {importlib.metadata.version('xyang')}"
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected
