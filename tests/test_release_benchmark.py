"""Release benchmark harness (benchmarks/release_bench.py): schema, README section, line counts."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benchmarks"))

import loc  # noqa: E402
import release_bench as rb  # noqa: E402
import workloads  # noqa: E402


@pytest.fixture(scope="module")
def smoke_results() -> dict:
    data = rb.run(["python"], ["small"], processes=1, smoke=True, release_tag=None)
    data["environment"]["git"]["dirty"] = False
    return data


def test_count_python_skips_blank_comments_and_docstrings() -> None:
    src = '"""Module doc."""\n\n# comment\nx = 1  # trailing\n\n\ndef f():\n    """Doc\n    more."""\n    s = """a\nb"""\n    return s\n'
    # x = 1; def f(); s = """a / b"""  (2 lines); return s
    assert loc.count_python(src) == 5


def test_count_typescript_handles_comments_strings_templates_and_regex() -> None:
    src = (
        "// line comment\n"
        "/* block\n   comment */\n"
        "const a = '// not a comment';\n"
        "\n"
        "const r = /\\/\\*[a-z/]+/g; // regex with slashes\n"
        "const t = `x ${a + `y ${1}`} \n"
        "z`;\n"
        "const d = 4 / 2 / 1;\n"
        "/** doc */\n"
        "export { a };\n"
    )
    assert loc.count_typescript(src) == 6


def test_count_typescript_rejects_unterminated_input() -> None:
    with pytest.raises(ValueError):
        loc.count_typescript("const s = `open\n")


def test_count_all_lists_scopes_and_exclusions() -> None:
    counts = loc.count_all()
    assert set(counts["languages"]) == {"python", "typescript"}
    assert counts["languages"]["python"]["root"] == "src/xyang"
    assert counts["languages"]["typescript"]["root"] == "ts/src"
    assert any("tests" in e for e in counts["excluded"])
    for info in counts["languages"].values():
        assert 0 < info["code_lines"] < info["physical_lines"]


def test_generated_instance_matches_pinned_hash(tmp_path: Path) -> None:
    resolved = workloads.materialize(workloads.WORKLOADS["large"], tmp_path)
    assert resolved["description"]["instance_sha256"] == workloads.INVENTORY_SHA256
    assert Path(resolved["spec"]["validate"]["instance"]).is_file()


def test_changed_generator_is_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wl = workloads.WORKLOADS["large"]
    changed = workloads.Workload(**{**wl.__dict__, "generator": lambda: b"{}\n"})
    with pytest.raises(workloads.WorkloadError, match="SHA-256"):
        workloads.materialize(changed, tmp_path)


def test_smoke_results_match_schema(smoke_results: dict) -> None:
    rb.validate_results(smoke_results)
    phase = smoke_results["results"]["python"]["workloads"]["small"]["validate"]
    assert phase["timing"]["iterations"] == 1
    assert "peak_rss_mib" not in phase["timing"]
    assert phase["check"] == {"valid": True}
    memory = phase["memory"]
    assert memory["operations_per_process"] == 1 and memory["warmup_per_process"] == 0
    assert memory["rss_source"] in {"VmHWM", "ru_maxrss"}
    assert memory["peak_rss_mib"]["median"] > 1
    json.dumps(smoke_results)


def test_memory_processes_are_separate_from_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    specs: list[dict] = []

    def fake_spawn(cmd: list[str]) -> dict:
        spec = json.loads(cmd[-1])
        specs.append(spec)
        return {
            "result": {"samples_ms": [1.0] * spec["iterations"], "check": {}, "peak_rss_bytes": 2**20, "rss_source": "VmHWM"},
            "wall_ms": 1.0,
        }

    monkeypatch.setattr(rb, "_spawn", fake_spawn)
    out = rb.measure_phase("python", None, {"parse": [], "validate": {}}, "parse", 3, 40, 2, 5)
    timing_runs = [s for s in specs if s["iterations"] == 40]
    memory_runs = [s for s in specs if s["iterations"] == 1]
    assert len(timing_runs) == 2 and all(s["warmup"] == 3 for s in timing_runs)
    assert len(memory_runs) == 5 and all(s["warmup"] == 0 for s in memory_runs)
    assert out["timing"]["iterations"] == 80
    assert out["memory"]["processes"] == 5


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("code_size"),
        lambda d: d.__setitem__("schema_version", 99),
        lambda d: d["results"]["python"]["workloads"]["small"]["parse"]["timing"].__setitem__("iterations", 7),
        lambda d: d["results"]["python"]["workloads"]["small"]["validate"]["timing"]["time_ms"].__setitem__("median", -1),
        lambda d: d["results"]["python"]["workloads"]["small"]["parse"]["memory"].__setitem__("operations_per_process", 30),
        lambda d: d["results"]["python"]["workloads"]["small"]["parse"]["memory"].__setitem__("warmup_per_process", 5),
        lambda d: d["results"]["python"]["workloads"]["small"]["parse"]["timing"].__setitem__("peak_rss_mib", {}),
        lambda d: d["results"]["python"]["workloads"]["small"]["parse"].pop("memory"),
        lambda d: d["results"]["python"]["workloads"].pop("small"),
        lambda d: d["results"].__setitem__("rust", {}),
    ],
)
def test_schema_rejects_broken_results(smoke_results: dict, mutate) -> None:
    broken = copy.deepcopy(smoke_results)
    mutate(broken)
    with pytest.raises(rb.BenchmarkError):
        rb.validate_results(broken)


def test_invalid_instance_fails_the_run(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"interface-inventory:inventory": {"interface": [{"name": "eth0", "mtu": 1}]}}))
    module = str(ROOT / "benchmarks" / "workloads" / "interface-inventory.yang")
    spec = {"parse": [], "validate": {"module": {"path": module, "include": []}, "instance": str(bad)}}
    with pytest.raises(rb.BenchmarkError, match="invalid"):
        rb.measure_phase("python", None, spec, "validate", 0, 1, 1, 1)


def test_replace_section_is_idempotent() -> None:
    readme = f"# T\n\nintro\n\n{rb.README_START}\nold\n{rb.README_END}\n\n## Next\n"
    once = rb.replace_section(readme, "new body\n")
    assert rb.replace_section(once, "new body\n") == once
    assert once == f"# T\n\nintro\n\n{rb.README_START}\nnew body\n{rb.README_END}\n\n## Next\n"


@pytest.mark.parametrize("readme", ["no markers\n", f"{rb.README_START}\n{rb.README_START}\n{rb.README_END}\n"])
def test_replace_section_requires_one_marker_pair(readme: str) -> None:
    with pytest.raises(rb.BenchmarkError):
        rb.replace_section(readme, "x")


def test_update_readme_writes_then_is_stable(smoke_results: dict, tmp_path: Path) -> None:
    data = {**smoke_results, "smoke": False}
    results = tmp_path / "results.json"
    results.write_text(json.dumps(data))
    readme = tmp_path / "README.md"
    readme.write_text(f"# T\n{rb.README_START}\n{rb.README_END}\n")
    assert rb.update_readme(results, readme, check=True, allow_dirty=False) == 1
    assert rb.update_readme(results, readme, check=False, allow_dirty=False) == 0
    first = readme.read_text()
    assert data["environment"]["git"]["commit"][:12] in first
    assert "| small | validate |" in first
    assert "one operation, no warmup" in first
    assert rb.update_readme(results, readme, check=False, allow_dirty=False) == 0
    assert readme.read_text() == first
    assert rb.update_readme(results, readme, check=True, allow_dirty=False) == 0


def test_update_readme_refuses_smoke_and_dirty(smoke_results: dict, tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(f"{rb.README_START}\n{rb.README_END}\n")
    results = tmp_path / "results.json"
    results.write_text(json.dumps(smoke_results))
    with pytest.raises(rb.BenchmarkError, match="smoke"):
        rb.update_readme(results, readme, check=False, allow_dirty=False)
    dirty = copy.deepcopy(smoke_results)
    dirty["smoke"] = False
    dirty["environment"]["git"]["dirty"] = True
    results.write_text(json.dumps(dirty))
    with pytest.raises(rb.BenchmarkError, match="dirty"):
        rb.update_readme(results, readme, check=False, allow_dirty=False)


def test_checked_in_results_match_readme() -> None:
    latest = ROOT / "benchmarks" / "results" / "latest.json"
    rb.validate_results(json.loads(latest.read_text(encoding="utf-8")))
    assert rb.update_readme(latest, ROOT / "README.md", check=True, allow_dirty=False) == 0
