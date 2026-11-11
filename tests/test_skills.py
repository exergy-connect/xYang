"""Repository agent skills: frontmatter, links, discovery, and the runnable examples they cite."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS = sorted((ROOT / "skills").glob("*/SKILL.md"))
ASSETS = ROOT / "skills" / "xyang-model" / "assets"


def _frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, "SKILL.md must start with --- frontmatter ---"
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def test_skills_exist():
    assert {p.parent.name for p in SKILLS} >= {"xyang-model", "xyang-validate"}


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_frontmatter_names_the_directory(skill: Path):
    fields = _frontmatter(skill.read_text(encoding="utf-8"))
    assert fields.get("name") == skill.parent.name
    assert len(fields.get("description", "")) > 40


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_relative_links_and_repo_paths_exist(skill: Path):
    text = skill.read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)#]+)\)", text):
        if "://" in target:
            continue
        assert (skill.parent / target).exists(), target
    for path in re.findall(r"`((?:examples|design|tests|skills|src|ts/src)/[\w./@-]+)`", text):
        assert (ROOT / path).exists(), path
    for name in re.findall(r"`assets/([\w.-]+)`", text):
        assert (skill.parent / "assets" / name).exists(), name


@pytest.mark.parametrize("index", ["llms.txt", "AGENTS.md"])
def test_every_skill_is_discoverable(index: str):
    text = (ROOT / index).read_text(encoding="utf-8")
    for skill in SKILLS:
        assert skill.relative_to(ROOT).as_posix() in text


def _cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "xyang", *args],
        cwd=ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
    )


@pytest.mark.parametrize("stem", ["minimal-module", "netlab-topology"])
def test_asset_json_schema_is_current_convert_output(stem: str, tmp_path: Path):
    out = tmp_path / f"{stem}.yang.json"
    assert _cli("convert", str(ASSETS / f"{stem}.yang"), "-o", str(out)).returncode == 0
    checked_in = json.loads((ASSETS / f"{stem}.yang.json").read_text(encoding="utf-8"))
    assert json.loads(out.read_text(encoding="utf-8")) == checked_in


def test_netlab_examples_from_the_skills():
    module = str(ASSETS / "netlab-topology.yang")
    instance = json.loads((ASSETS / "netlab-topology-instance.json").read_text(encoding="utf-8"))

    ok = _cli("validate", "--format", "json", module, "-", stdin=json.dumps(instance))
    assert ok.returncode == 0
    assert json.loads(ok.stdout) == {"valid": True, "errors": []}

    loop = json.loads(json.dumps(instance))
    loop["topology"]["links"][0]["target"] = loop["topology"]["links"][0]["source"]
    bad = _cli("validate", "--format", "json", module, "-", stdin=json.dumps(loop))
    assert bad.returncode == 1
    assert [(e["path"], e["code"]) for e in json.loads(bad.stdout)["errors"]] == [("/topology/links/0", "must")]

    ref = json.loads(json.dumps(instance))
    ref["topology"]["services"][0]["runs-on"] = "/topology/nodes[name='r9']"
    bad = _cli("validate", "--format", "json", module, "-", stdin=json.dumps(ref))
    assert bad.returncode == 1
    assert [(e["path"], e["code"]) for e in json.loads(bad.stdout)["errors"]] == [
        ("/topology/services/0/runs-on", "instance-identifier")
    ]


def test_validate_skill_encoding_and_exit_codes(tmp_path: Path):
    module = tmp_path / "enc.yang"
    module.write_text(
        'module enc { yang-version 1.1; namespace "urn:enc"; prefix e;\n'
        "  container top { list item { key name; min-elements 1; leaf name { type string; } }\n"
        "    leaf big { type int64; } leaf flag { type empty; } } }\n",
        encoding="utf-8",
    )

    def run(data: object, *flags: str) -> tuple[int, dict]:
        proc = _cli("validate", "--format", "json", *flags, str(module), "-", stdin=json.dumps(data))
        return proc.returncode, json.loads(proc.stdout)

    item = [{"name": "a"}]
    assert run({"top": {"item": item, "big": "9007199254740993", "flag": [None]}})[0] == 0
    code, out = run({"top": {"item": item, "big": 5}})
    assert code == 1 and out["errors"][0]["code"] == "type"
    assert run({"top": {"item": {"a": {}}, "big": 5, "flag": None}}, "--native-json")[0] == 0
    for absent_or_empty in ({"top": {}}, {"top": {"item": []}}):
        code, out = run(absent_or_empty)
        assert code == 1 and out["errors"][0]["code"] == "min-elements"

    broken = tmp_path / "broken.yang"
    broken.write_text('module b { yang-version 2; namespace "u"; prefix b; }\n', encoding="utf-8")
    proc = _cli("validate", "--format", "json", str(broken), "-", stdin="{}")
    assert proc.returncode == 2 and proc.stdout == "" and "yang-version" in proc.stderr


def test_registry_import_named_in_the_validate_skill():
    from xyang.types.registry import YANG_INTEGER_BOUNDS

    assert YANG_INTEGER_BOUNDS["uint8"] == (0, 255)
    with pytest.raises(ModuleNotFoundError):
        __import__("xyang.json.integer_bounds")
