"""CLI tests for --include-path."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def _run_xyang(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    return subprocess.run(
        [sys.executable, "-m", "xyang", *args],
        capture_output=True,
        text=True,
        cwd=cwd or ROOT,
        env=env,
        check=False,
    )


def test_cli_include_path_resolves_import(tmp_path: Path) -> None:
    inc = tmp_path / "include"
    inc.mkdir()
    (inc / "dep.yang").write_text(
        """module dep {
  yang-version 1.1;
  namespace "urn:example:dep";
  prefix d;
}
""",
        encoding="utf-8",
    )
    main = tmp_path / "main.yang"
    main.write_text(
        """module main {
  yang-version 1.1;
  namespace "urn:example:main";
  prefix m;
  import dep { prefix d; }
}
""",
        encoding="utf-8",
    )
    result = _run_xyang("parse", "--include-path", str(inc), str(main))
    assert result.returncode == 0, result.stderr
    assert "Module: main" in result.stdout


def test_cli_include_path_missing_import_fails(tmp_path: Path) -> None:
    main = tmp_path / "main.yang"
    main.write_text(
        """module main {
  yang-version 1.1;
  namespace "urn:example:main";
  prefix m;
  import dep { prefix d; }
}
""",
        encoding="utf-8",
    )
    result = _run_xyang("parse", str(main))
    assert result.returncode == 1
    assert "dep" in result.stderr


@pytest.mark.parametrize("cmd", ["parse", "validate", "convert"])
def test_cli_help_lists_include_path(cmd: str) -> None:
    result = _run_xyang(cmd, "--help")
    assert result.returncode == 0
    assert "--include-path" in result.stdout
