"""Gate package publishing on a merged, measured release README."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from release_bench import BenchmarkError, LANGUAGES, update_readme, validate_results
from workloads import WORKLOADS

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "benchmarks/results/latest.json"
README = ROOT / "README.md"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def check() -> str:
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    validate_results(data)
    metadata = data["environment"]["git"]
    tag = metadata.get("release_tag")
    if not isinstance(tag, str) or not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise BenchmarkError("results must identify a versioned release tag")
    if data["smoke"] or metadata["dirty"]:
        raise BenchmarkError("release measurements must be full and from a clean tree")
    if set(data["results"]) != set(LANGUAGES) or set(data["workloads"]) != set(WORKLOADS):
        raise BenchmarkError("release measurements must include every language and workload")
    if "zig" not in data.get("binary_size", {}):
        raise BenchmarkError("release measurements must include Zig binary size")
    if data.get("zig_cli", {}).get("binary_sha256") != data["binary_size"]["zig"]["sha256"]:
        raise BenchmarkError("release measurements must include Zig CLI results for the measured binary")
    commit = git("rev-parse", f"refs/tags/{tag}^{{commit}}")
    if metadata["commit"] != commit:
        raise BenchmarkError("benchmark commit does not match the release tag")
    subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=ROOT, check=True)
    changed = git("diff", "--name-only", commit, "HEAD").splitlines()
    if set(changed) - {"README.md", "benchmarks/results/latest.json"}:
        raise BenchmarkError("files other than benchmark results and README changed since the release tag")
    version = tag[1:]
    python_version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    ts_version = json.loads((ROOT / "ts/package.json").read_text(encoding="utf-8"))["version"]
    versions = data["environment"]["versions"]
    if any(v != version for v in (python_version, ts_version, versions.get("python_package"), versions.get("ts_package"))):
        raise BenchmarkError("package and measured versions must match the release tag")
    if update_readme(RESULTS, README, check=True, allow_dirty=False):
        raise BenchmarkError("README does not match the measured results")
    release = json.loads(subprocess.check_output(
        ["gh", "release", "view", tag, "--json", "isDraft,isPrerelease"], cwd=ROOT, text=True
    ))
    if release["isDraft"] or release["isPrerelease"]:
        raise BenchmarkError("release must be published and non-prerelease")
    return tag


if __name__ == "__main__":
    try:
        print(f"Release README verified for {check()}")
    except (BenchmarkError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"::error::Cannot publish: {exc}", file=sys.stderr)
        sys.exit(1)
