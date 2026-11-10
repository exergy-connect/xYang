"""Import revision-date must not fall back silently (#66)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from xyang import parse_yang_file
from xyang.errors import YangSyntaxError


def _write_module(directory: Path, filename: str, name: str, prefix: str, body: str = "") -> None:
    (directory / filename).write_text(
        f"""module {name} {{
  yang-version 1.1;
  namespace "urn:{name}";
  prefix {prefix};
{body}
}}
""",
        encoding="utf-8",
    )


def test_revision_date_fallback_warns(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    _write_module(tmp_path, "base@2019-01-01.yang", "base", "b", '  description "2019";')
    _write_module(
        tmp_path,
        "m.yang",
        "m",
        "m",
        "  import base { prefix b; revision-date 2020-01-01; }",
    )
    with caplog.at_level(logging.WARNING, logger="xyang.parser.yang_parser"):
        module = parse_yang_file(tmp_path / "m.yang")
    assert module.import_prefixes["b"].description == "2019"
    assert any(
        r.getMessage() == "import 'base' revision-date 2020-01-01 not found; using base@2019-01-01.yang"
        for r in caplog.records
    )


def test_exact_revision_wins_over_newer(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    _write_module(tmp_path, "base@2020-01-01.yang", "base", "b", '  description "2020";')
    _write_module(tmp_path, "base@2021-01-01.yang", "base", "b", '  description "2021";')
    _write_module(
        tmp_path,
        "m.yang",
        "m",
        "m",
        "  import base { prefix b; revision-date 2020-01-01; }",
    )
    with caplog.at_level(logging.WARNING, logger="xyang.parser.yang_parser"):
        module = parse_yang_file(tmp_path / "m.yang")
    assert module.import_prefixes["b"].description == "2020"
    assert not any("revision-date" in r.getMessage() for r in caplog.records)


def test_missing_import_says_module(tmp_path: Path) -> None:
    _write_module(tmp_path, "m.yang", "m", "m", "  import base { prefix b; }")
    with pytest.raises(YangSyntaxError) as excinfo:
        parse_yang_file(tmp_path / "m.yang")
    message = str(excinfo.value)
    assert "Could not find module 'base'" in message
    assert "submodule" not in message
