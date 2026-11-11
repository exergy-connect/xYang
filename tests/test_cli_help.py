"""--help/-h is generated from the argparse registry and does no file I/O."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from xyang.__main__ import build_parser, command_parsers  # noqa: E402

DOC_PATHS = (
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    ROOT / "llms.txt",
    ROOT / "skills" / "xyang-validate" / "SKILL.md",
    ROOT / "skills" / "xyang-model" / "SKILL.md",
)
_LONG_OPTION = re.compile(r"--[A-Za-z0-9][\w-]*")
_SHORT_OPTION = re.compile(r"(?<![A-Za-z0-9])-[A-Za-z]\b")


def _run(*args: str, cwd: Path, stdin: str = "") -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["COLUMNS"] = "88"
    return subprocess.run(
        [sys.executable, "-m", "xyang", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        input=stdin,
        check=False,
    )


def _option_strings(parser: argparse.ArgumentParser) -> set[str]:
    found: set[str] = set()
    for action in parser._actions:
        found.update(action.option_strings)
    return found


def _takes_value(action: argparse.Action) -> bool:
    if not action.option_strings:
        return False
    if isinstance(action, (argparse._HelpAction, argparse._VersionAction, argparse._StoreTrueAction)):
        return False
    return action.nargs not in (0, "?", "*")


def test_help_lists_registered_commands_and_options(tmp_path: Path) -> None:
    parser = build_parser()
    commands = command_parsers(parser)
    assert commands, "parser registered no commands"
    registered = set().union(*(_option_strings(sub) for sub in commands.values()), _option_strings(parser))

    for flag in ("--help", "-h"):
        result = _run(flag, cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        assert result.stdout == parser.format_help()
        for name in commands:
            assert name in result.stdout
        for option in _option_strings(parser):
            assert option in result.stdout
        extra_long = set(_LONG_OPTION.findall(result.stdout)) - registered
        extra_short = set(_SHORT_OPTION.findall(result.stdout)) - registered
        assert not extra_long, extra_long
        assert not extra_short, extra_short

    bare = _run(cwd=tmp_path)
    assert bare.returncode == 0 and bare.stdout == parser.format_help() and bare.stderr == ""

    for name, sub in commands.items():
        own = _option_strings(sub)
        assert "default" in sub.format_help().lower()
        assert "examples:" in sub.format_help()
        for flag in ("--help", "-h"):
            result = _run(name, flag, cwd=tmp_path, stdin="")
            assert result.returncode == 0, (name, flag, result.stderr)
            assert result.stderr == ""
            assert result.stdout == sub.format_help()
            for option in own:
                assert option in result.stdout
            extra_long = set(_LONG_OPTION.findall(result.stdout)) - own
            extra_short = set(_SHORT_OPTION.findall(result.stdout)) - own
            assert not extra_long, (name, extra_long)
            assert not extra_short, (name, extra_short)

    assert list(tmp_path.iterdir()) == []


def test_malformed_invocation_exits_2(tmp_path: Path) -> None:
    unknown_command = _run("no-such-command", cwd=tmp_path, stdin="")
    assert unknown_command.returncode == 2
    assert unknown_command.stdout == ""
    assert "invalid choice" in unknown_command.stderr

    unknown_global = _run("--not-a-registered-flag", cwd=tmp_path, stdin="")
    assert unknown_global.returncode == 2 and unknown_global.stdout == ""
    assert unknown_global.stderr.strip()

    commands = command_parsers()
    for name, sub in commands.items():
        unknown = _run(name, "--not-a-registered-flag", "module.yang", cwd=tmp_path, stdin="")
        assert unknown.returncode == 2, (name, unknown.stderr)
        assert unknown.stdout == ""
        assert "unrecognized arguments" in unknown.stderr
        assert "file not found" not in unknown.stderr
        for action in sub._actions:
            if not _takes_value(action):
                continue
            missing = _run(name, action.option_strings[-1], cwd=tmp_path, stdin="")
            assert missing.returncode == 2, (name, action.option_strings, missing.stderr)
            assert missing.stdout == ""
            assert missing.stderr.strip()

    assert list(tmp_path.iterdir()) == []


def test_docs_point_agents_at_help_without_invented_flags() -> None:
    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8")
        assert "--help" in text, path
        assert "xyang-ts --version" not in text, path
        assert "xyang-ts -V" not in text, path
        assert "xyang-ts convert -o" not in text, path
        assert "xyang-ts convert --output" not in text, path
    for path in (ROOT / "CHANGELOG.md", ROOT / "ts" / "CHANGELOG.md"):
        text = path.read_text(encoding="utf-8")
        assert "#153" in text
        assert "--help" in text
