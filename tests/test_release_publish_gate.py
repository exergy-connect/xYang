"""Package publication requires benchmark results and README from the release."""

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benchmarks"))
import check_release_readme as gate
import release_bench as bench


@pytest.fixture
def release_tree(tmp_path, monkeypatch):
    results = json.loads((ROOT / "benchmarks/results/latest.json").read_text())
    sample = {"wall_ms": {"median": 1, "min": 1, "max": 1},
              "peak_rss_mib": {"median": 1, "min": 1, "max": 1}}
    results["zig_cli"] = {"samples": 1, "binary_sha256": results["binary_size"]["zig"]["sha256"],
                           "startup": sample, "workloads": {
                               name: {"parse": sample, "validate": sample} for name in results["workloads"]}}
    tag = results["environment"]["git"]["release_tag"]
    commit = results["environment"]["git"]["commit"]
    (tmp_path / "benchmarks/results").mkdir(parents=True)
    (tmp_path / "ts").mkdir()
    (tmp_path / "pyproject.toml").write_text(f'[project]\nversion = "{tag[1:]}"\n')
    (tmp_path / "ts/package.json").write_text(json.dumps({"version": tag[1:]}))
    readme = bench.replace_section('head\n<!-- xyang-benchmark:start -->\n<!-- xyang-benchmark:end -->\ntail\n', bench.render_markdown(results))
    (tmp_path / "README.md").write_text(readme)
    result_path = tmp_path / "benchmarks/results/latest.json"
    result_path.write_text(json.dumps(results))
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "RESULTS", result_path)
    monkeypatch.setattr(gate, "README", tmp_path / "README.md")
    monkeypatch.setattr(gate, "git", lambda *args: commit if args[0] == "rev-parse" else "README.md\nbenchmarks/results/latest.json")
    monkeypatch.setattr(gate.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(gate.subprocess, "check_output", lambda *args, **kwargs: '{"isDraft":false,"isPrerelease":false}')
    return results, result_path


def test_verified_release_readme_allows_publish(release_tree):
    results, _ = release_tree
    assert gate.check() == results["environment"]["git"]["release_tag"]


@pytest.mark.parametrize("change", ["tag", "commit", "dirty", "smoke", "language", "version", "readme", "source", "draft", "prerelease", "ancestor", "binary", "workload", "zig_cli", "zig_hash"])
def test_unverified_release_is_rejected(release_tree, monkeypatch, change):
    results, result_path = release_tree
    results = copy.deepcopy(results)
    if change == "tag":
        results["environment"]["git"]["release_tag"] = None
    elif change == "commit":
        results["environment"]["git"]["commit"] = "0" * 40
    elif change == "dirty":
        results["environment"]["git"]["dirty"] = True
    elif change == "smoke":
        results["smoke"] = True
    elif change == "language":
        results["results"].pop("typescript")
    elif change == "version":
        results["environment"]["versions"]["ts_package"] = "0.0.0"
    elif change == "readme":
        gate.README.write_text(gate.README.read_text().replace("<!-- xyang-benchmark:end -->", "wrong\n<!-- xyang-benchmark:end -->"))
    elif change == "binary":
        results.pop("binary_size")
    elif change == "zig_cli":
        results.pop("zig_cli")
    elif change == "zig_hash":
        results["zig_cli"]["binary_sha256"] = "0" * 64
    elif change == "workload":
        results["workloads"].pop("large")
        for language in results["results"].values():
            language["workloads"].pop("large")
    elif change in {"draft", "prerelease"}:
        release = {"isDraft": change == "draft", "isPrerelease": change == "prerelease"}
        monkeypatch.setattr(gate.subprocess, "check_output", lambda *args, **kwargs: json.dumps(release))
    elif change == "ancestor":
        def fail(*args, **kwargs):
            raise gate.subprocess.CalledProcessError(1, "git")
        monkeypatch.setattr(gate.subprocess, "run", fail)
    elif change == "source":
        commit = results["environment"]["git"]["commit"]
        monkeypatch.setattr(gate, "git", lambda *args: commit if args[0] == "rev-parse" else "src/xyang/__init__.py")
    result_path.write_text(json.dumps(results))
    with pytest.raises((bench.BenchmarkError, gate.subprocess.CalledProcessError)):
        gate.check()
