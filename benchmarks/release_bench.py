"""Release benchmark harness: Python/TypeScript time, memory, source lines, and optional Zig binary size.

Usage from the repository root (TypeScript needs ``cd ts && npm ci`` first)::

    python benchmarks/release_bench.py run --out benchmarks/results/latest.json
    python benchmarks/release_bench.py update-readme benchmarks/results/latest.json
    python benchmarks/release_bench.py update-readme benchmarks/results/latest.json --check
    python benchmarks/release_bench.py run --smoke --out /tmp/smoke.json   # CI smoke, 1 iteration

Each (language, workload, phase) runs in fresh child processes: warm repeated
timing processes, and separate memory processes that run the operation once and
report their own peak RSS (Linux ``VmHWM`` from /proc/self/status), so memory
does not depend on the timing iteration count. See benchmarks/README.md for the methodology.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import loc  # noqa: E402
from workloads import WORKLOADS, materialize  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 2
LANGUAGES = ("python", "typescript")
PHASES = ("parse", "validate")
README_START = "<!-- xyang-benchmark:start -->"
README_END = "<!-- xyang-benchmark:end -->"
REPRODUCE = (
    "python benchmarks/release_bench.py run --out benchmarks/results/latest.json && "
    "python benchmarks/release_bench.py update-readme benchmarks/results/latest.json"
)

# (warmup, iterations per process); processes come from --processes.
PLAN: dict[tuple[str, str], tuple[int, int]] = {
    ("small", "parse"): (5, 30),
    ("small", "validate"): (10, 50),
    ("large", "parse"): (2, 10),
    ("large", "validate"): (1, 5),
}
STARTUP_PROCESSES = 10
MEMORY_OPERATION = {
    "parse": "import + parse workload modules once",
    "validate": "import + parse schema + decode JSON + build validator + validate once",
}
MEMORY_PROCESSES = 5


class BenchmarkError(RuntimeError):
    pass


# --------------------------------------------------------------------------- measurement


def _spawn(cmd: list[str]) -> dict[str, Any]:
    """Run one child to completion; return its JSON output and wall time (spawn to exit)."""
    with tempfile.TemporaryFile() as out_f, tempfile.TemporaryFile() as err_f:
        start = time.perf_counter()
        proc = subprocess.Popen(cmd, stdout=out_f, stderr=err_f, cwd=ROOT)
        code = proc.wait()
        wall_ms = (time.perf_counter() - start) * 1000
        out_f.seek(0)
        err_f.seek(0)
        out, err = out_f.read(), err_f.read()
    if code != 0:
        raise BenchmarkError(f"{' '.join(cmd[:2])} exited {code}: {err.decode(errors='replace')[-2000:]}")
    lines = out.decode().strip().splitlines()
    if not lines:
        raise BenchmarkError(f"{' '.join(cmd[:2])} printed no result")
    result = json.loads(lines[-1])
    if not isinstance(result.get("peak_rss_bytes"), int) or result["peak_rss_bytes"] <= 0:
        raise BenchmarkError(f"{' '.join(cmd[:2])} reported no peak RSS")
    return {"result": result, "wall_ms": wall_ms}


def _worker_cmd(lang: str, ts_bundle: Path | None, spec: dict[str, Any]) -> list[str]:
    payload = json.dumps(spec)
    if lang == "python":
        return [sys.executable, str(ROOT / "benchmarks" / "worker.py"), payload]
    assert ts_bundle is not None
    return [_node(), str(ts_bundle), payload]


def _node() -> str:
    node = shutil.which("node")
    if not node:
        raise BenchmarkError("node not found on PATH")
    return node


def _build_ts_bundle(out_dir: Path) -> Path:
    bundle = out_dir / "xyang-bench-worker.mjs"
    if not (ROOT / "ts" / "node_modules" / "esbuild").is_dir():
        raise BenchmarkError("ts/node_modules missing: run `cd ts && npm ci` first")
    subprocess.run([_node(), "scripts/build-bench-worker.mjs", str(bundle)], cwd=ROOT / "ts", check=True)
    return bundle


def _summary(values: list[float]) -> dict[str, float]:
    return {"median": statistics.median(values), "min": min(values), "max": max(values)}


def measure_timing(
    lang: str, ts_bundle: Path | None, spec: dict[str, Any], phase: str, warmup: int, iterations: int, processes: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Warm repeated timing. These processes' memory is not reported (it grows with the iteration count)."""
    samples: list[float] = []
    check: dict[str, Any] = {}
    for _ in range(processes):
        run = _spawn(_worker_cmd(lang, ts_bundle, {**spec, "phase": phase, "warmup": warmup, "iterations": iterations}))
        got = run["result"]["samples_ms"]
        if len(got) != iterations:
            raise BenchmarkError(f"{lang} {phase}: expected {iterations} samples, got {len(got)}")
        samples.extend(got)
        check = run["result"]["check"]
    timing = {
        "processes": processes,
        "warmup_per_process": warmup,
        "iterations_per_process": iterations,
        "iterations": len(samples),
        "time_ms": _summary(samples),
    }
    return timing, check


def measure_memory(lang: str, ts_bundle: Path | None, spec: dict[str, Any], phase: str, processes: int) -> dict[str, Any]:
    """Peak RSS of fresh processes that each do the setup and exactly one operation (no warmup)."""
    rss: list[int] = []
    sources: set[str] = set()
    for _ in range(processes):
        run = _spawn(_worker_cmd(lang, ts_bundle, {**spec, "phase": phase, "warmup": 0, "iterations": 1}))
        if len(run["result"]["samples_ms"]) != 1:
            raise BenchmarkError(f"{lang} {phase}: memory process must run exactly one operation")
        rss.append(run["result"]["peak_rss_bytes"])
        sources.add(run["result"]["rss_source"])
    return {
        "processes": processes,
        "operations_per_process": 1,
        "warmup_per_process": 0,
        "peak_rss_mib": _summary([b / 2**20 for b in rss]),
        "rss_source": ",".join(sorted(sources)),
    }


def measure_phase(
    lang: str,
    ts_bundle: Path | None,
    spec: dict[str, Any],
    phase: str,
    warmup: int,
    iterations: int,
    processes: int,
    memory_processes: int,
) -> dict[str, Any]:
    timing, check = measure_timing(lang, ts_bundle, spec, phase, warmup, iterations, processes)
    return {"timing": timing, "memory": measure_memory(lang, ts_bundle, spec, phase, memory_processes), "check": check}


def measure_startup(lang: str, ts_bundle: Path | None, spec: dict[str, Any], processes: int) -> dict[str, Any]:
    walls: list[float] = []
    rss: list[int] = []
    sources: set[str] = set()
    for _ in range(processes):
        run = _spawn(_worker_cmd(lang, ts_bundle, {**spec, "phase": "startup", "warmup": 0, "iterations": 0}))
        walls.append(run["wall_ms"])
        rss.append(run["result"]["peak_rss_bytes"])
        sources.add(run["result"]["rss_source"])
    return {
        "processes": processes,
        "wall_ms": _summary(walls),
        "peak_rss_mib": _summary([b / 2**20 for b in rss]),
        "rss_source": ",".join(sorted(sources)),
    }


def _zig_cli_commands(binary: Path, spec: dict[str, Any], phase: str) -> list[list[str]]:
    if phase == "startup":
        return [[str(binary), "--version"]]
    if phase == "parse":
        return [[str(binary), "parse", *sum((["--include-path", p] for p in m["include"]), []), m["path"]]
                for m in spec["parse"]]
    target = spec["validate"]
    module = target["module"]
    return [[str(binary), "validate", "--format", "json",
             *sum((["--include-path", p] for p in module["include"]), []), module["path"], target["instance"]]]


def _zig_cli_run(commands: list[list[str]], phase: str, *, measure_rss: bool = False) -> tuple[float, int]:
    """Time whole CLI invocations; optionally measure each child's peak RSS with GNU time."""
    clock_ms = 0.0
    peak = 0
    time_binary = shutil.which("time") if measure_rss else None
    if measure_rss and not time_binary:
        raise BenchmarkError("Zig CLI memory measurement requires GNU time on PATH")
    for command in commands:
        with tempfile.TemporaryFile(mode="w+") as rss_file:
            cmd = [time_binary, "-f", "%M", "-o", f"/proc/self/fd/{rss_file.fileno()}", *command] if measure_rss else command
            start = time.perf_counter_ns()
            result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                                    pass_fds=(rss_file.fileno(),) if measure_rss else ())
            clock_ms += (time.perf_counter_ns() - start) / 1e6
            if result.returncode:
                raise BenchmarkError(f"Zig CLI {phase} failed ({result.returncode}): {result.stderr[-2000:]}")
            if phase == "validate":
                try:
                    valid = json.loads(result.stdout).get("valid") is True
                except (ValueError, AttributeError) as exc:
                    raise BenchmarkError("Zig CLI validation did not return JSON") from exc
                if not valid:
                    raise BenchmarkError(f"Zig CLI rejected workload: {result.stdout[:2000]}")
            if measure_rss:
                rss_file.seek(0)
                try:
                    peak = max(peak, int(rss_file.read().strip()))
                except ValueError as exc:
                    raise BenchmarkError("GNU time did not report Zig peak RSS") from exc
    return clock_ms, peak


def measure_zig_cli(binary: Path, resolved: dict[str, Any], samples: int) -> dict[str, Any]:
    time_path = shutil.which("time")
    if not time_path or "gnu time" not in _cmd([time_path, "--version"]).lower():
        raise BenchmarkError("Zig CLI memory measurement requires GNU time")
    result: dict[str, Any] = {"samples": samples, "binary_sha256": measure_binary_size(binary)["sha256"], "workloads": {}}
    any_spec = next(iter(resolved.values()))["spec"]
    for name, spec, phase in [("", any_spec, "startup"), *(
        (name, wl["spec"], phase) for name, wl in resolved.items() for phase in PHASES
    )]:
        commands = _zig_cli_commands(binary, spec, phase)
        walls = [_zig_cli_run(commands, phase)[0] for _ in range(samples)]
        rss = [_zig_cli_run(commands, phase, measure_rss=True)[1] / 1024 for _ in range(samples)]
        measurement = {"wall_ms": _summary(walls), "peak_rss_mib": _summary(rss)}
        if phase == "startup":
            result["startup"] = measurement
        else:
            result["workloads"].setdefault(name, {})[phase] = measurement
    return result


# --------------------------------------------------------------------------- environment


def _cmd(args: list[str]) -> str:
    try:
        return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def _mem_total_gib() -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 2**20, 1)
    except OSError:
        pass
    return None


def _versions() -> dict[str, str]:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    ts_pkg = json.loads((ROOT / "ts" / "package.json").read_text(encoding="utf-8"))
    return {"python_package": match.group(1) if match else "unknown", "ts_package": ts_pkg["version"]}


def environment(release_tag: str | None) -> dict[str, Any]:
    gha = os.environ.get("GITHUB_ACTIONS") == "true"
    runner = (
        f"GitHub Actions {os.environ.get('ImageOS', os.environ.get('RUNNER_OS', ''))} "
        f"image {os.environ.get('ImageVersion', '?')} ({os.environ.get('RUNNER_ARCH', platform.machine())})"
        if gha
        else "local"
    )
    return {
        "git": {
            "commit": _cmd(["git", "rev-parse", "HEAD"]) or "unknown",
            "describe": _cmd(["git", "describe", "--tags", "--always", "--dirty"]),
            "dirty": bool(_cmd(["git", "status", "--porcelain", "--untracked-files=no"])),
            "release_tag": release_tag,
        },
        "versions": _versions(),
        "runtimes": {
            "python": f"{platform.python_implementation()} {platform.python_version()}",
            "node": _cmd([_node(), "--version"]) if shutil.which("node") else None,
        },
        "machine": {
            "runner": runner,
            "os": f"{platform.system()} {platform.release()}",
            "arch": platform.machine(),
            "cpu": _cpu_model(),
            "cpu_count": os.cpu_count(),
            "mem_total_gib": _mem_total_gib(),
        },
    }


# --------------------------------------------------------------------------- run


def run(
    languages: list[str],
    workload_names: list[str],
    processes: int,
    smoke: bool,
    release_tag: str | None,
    memory_processes: int = MEMORY_PROCESSES,
    zig_binary: Path | None = None,
    zig_cli: Path | None = None,
) -> dict[str, Any]:
    binary_size = measure_binary_size(zig_binary) if zig_binary is not None else None
    zig_cli_argument = zig_cli
    if zig_cli is not None:
        zig_cli = zig_cli.resolve()
        if not zig_cli.is_file() or not os.access(zig_cli, os.X_OK):
            raise BenchmarkError(f"Zig CLI is not executable: {zig_cli}")
    with tempfile.TemporaryDirectory(prefix="xyang-bench-") as tmp:
        tmpdir = Path(tmp)
        ts_bundle = _build_ts_bundle(tmpdir) if "typescript" in languages else None
        resolved = {name: materialize(WORKLOADS[name], tmpdir) for name in workload_names}
        startup_procs = 1 if smoke else STARTUP_PROCESSES
        procs = 1 if smoke else processes
        mem_procs = 1 if smoke else memory_processes
        results: dict[str, Any] = {}
        any_spec = next(iter(resolved.values()))["spec"]
        for lang in languages:
            entry: dict[str, Any] = {"startup": measure_startup(lang, ts_bundle, any_spec, startup_procs), "workloads": {}}
            for name, wl in resolved.items():
                entry["workloads"][name] = {}
                for phase in PHASES:
                    warmup, iterations = (0, 1) if smoke else PLAN[(name, phase)]
                    print(f"[bench] {lang} {name} {phase}", file=sys.stderr, flush=True)
                    entry["workloads"][name][phase] = measure_phase(
                        lang, ts_bundle, wl["spec"], phase, warmup, iterations, procs, mem_procs
                    )
            results[lang] = entry
        zig_results = measure_zig_cli(zig_cli, resolved, 1 if smoke else 5) if zig_cli is not None else None
    data = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "smoke": smoke,
        "environment": environment(release_tag),
        "workloads": {name: wl["description"] for name, wl in resolved.items()},
        "results": results,
        "code_size": loc.count_all(),
        "reproduce": REPRODUCE,
    }
    if binary_size is not None:
        data["binary_size"] = {"zig": binary_size}
        data["reproduce"] = REPRODUCE.replace("run --out", f"run --zig-binary {shlex.quote(str(zig_binary))} --out", 1)
    if zig_results is not None:
        data["zig_cli"] = zig_results
        data["reproduce"] = data["reproduce"].replace("run --", f"run --zig-cli {shlex.quote(str(zig_cli_argument))} --", 1)
    return data


def measure_binary_size(path: Path) -> dict[str, Any]:
    """Record the supplied executable's actual file size; do not run it."""
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise BenchmarkError(f"cannot read Zig binary {path}: {exc}") from exc
    if not content:
        raise BenchmarkError(f"Zig binary is empty: {path}")
    return {"file": path.name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


# --------------------------------------------------------------------------- schema


def _require(obj: Any, path: str, kind: type | tuple[type, ...]) -> Any:
    if not isinstance(obj, kind):
        raise BenchmarkError(f"results: {path} must be {kind}, got {type(obj).__name__}")
    return obj


def _require_stats(obj: Any, path: str) -> None:
    _require(obj, path, dict)
    for key in ("median", "min", "max"):
        value = _require(obj.get(key), f"{path}.{key}", (int, float))
        if value < 0:
            raise BenchmarkError(f"results: {path}.{key} is negative")


def validate_results(data: Any) -> None:
    """Raise BenchmarkError unless ``data`` matches the results schema."""
    _require(data, "$", dict)
    if data.get("schema_version") != SCHEMA_VERSION:
        raise BenchmarkError(f"results: schema_version must be {SCHEMA_VERSION}")
    _require(data.get("generated_at"), "generated_at", str)
    _require(data.get("smoke"), "smoke", bool)
    env = _require(data.get("environment"), "environment", dict)
    git = _require(env.get("git"), "environment.git", dict)
    _require(git.get("commit"), "environment.git.commit", str)
    _require(git.get("dirty"), "environment.git.dirty", bool)
    _require(env.get("versions"), "environment.versions", dict)
    _require(env.get("runtimes"), "environment.runtimes", dict)
    _require(env.get("machine"), "environment.machine", dict)
    workloads = _require(data.get("workloads"), "workloads", dict)
    for name, desc in workloads.items():
        _require(desc, f"workloads.{name}", dict)
        for key in ("title", "instance_sha256"):
            _require(desc.get(key), f"workloads.{name}.{key}", str)
        _require(desc.get("instance_bytes"), f"workloads.{name}.instance_bytes", int)
    results = _require(data.get("results"), "results", dict)
    if not results:
        raise BenchmarkError("results: no languages measured")
    for lang, entry in results.items():
        if lang not in LANGUAGES:
            raise BenchmarkError(f"results: unknown language {lang!r}")
        startup = _require(entry.get("startup"), f"results.{lang}.startup", dict)
        _require_stats(startup.get("wall_ms"), f"results.{lang}.startup.wall_ms")
        _require_stats(startup.get("peak_rss_mib"), f"results.{lang}.startup.peak_rss_mib")
        _require(startup.get("rss_source"), f"results.{lang}.startup.rss_source", str)
        measured = _require(entry.get("workloads"), f"results.{lang}.workloads", dict)
        if set(measured) != set(workloads):
            raise BenchmarkError(f"results: {lang} workloads {sorted(measured)} != {sorted(workloads)}")
        for name, phases in measured.items():
            for phase in PHASES:
                p = _require(phases.get(phase), f"results.{lang}.workloads.{name}.{phase}", dict)
                base = f"results.{lang}.workloads.{name}.{phase}"
                t = _require(p.get("timing"), f"{base}.timing", dict)
                iterations = _require(t.get("iterations"), f"{base}.timing.iterations", int)
                if iterations < 1 or iterations != t.get("processes", 0) * t.get("iterations_per_process", 0):
                    raise BenchmarkError(f"results: {base}.timing.iterations inconsistent")
                _require_stats(t.get("time_ms"), f"{base}.timing.time_ms")
                if "peak_rss_mib" in t:
                    raise BenchmarkError(f"results: {base}.timing must not report memory")
                m = _require(p.get("memory"), f"{base}.memory", dict)
                if _require(m.get("processes"), f"{base}.memory.processes", int) < 1:
                    raise BenchmarkError(f"results: {base}.memory.processes must be at least 1")
                if m.get("operations_per_process") != 1 or m.get("warmup_per_process") != 0:
                    raise BenchmarkError(f"results: {base}.memory must be one operation per process, no warmup")
                _require_stats(m.get("peak_rss_mib"), f"{base}.memory.peak_rss_mib")
                _require(m.get("rss_source"), f"{base}.memory.rss_source", str)
    code = _require(data.get("code_size"), "code_size", dict)
    langs = _require(code.get("languages"), "code_size.languages", dict)
    for lang in LANGUAGES:
        info = _require(langs.get(lang), f"code_size.languages.{lang}", dict)
        _require(info.get("code_lines"), f"code_size.languages.{lang}.code_lines", int)

    if "binary_size" in data:
        binaries = _require(data["binary_size"], "binary_size", dict)
        zig = _require(binaries.get("zig"), "binary_size.zig", dict)
        _require(zig.get("file"), "binary_size.zig.file", str)
        if _require(zig.get("bytes"), "binary_size.zig.bytes", int) <= 0:
            raise BenchmarkError("binary_size.zig.bytes must be positive")
        digest = _require(zig.get("sha256"), "binary_size.zig.sha256", str)
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise BenchmarkError("binary_size.zig.sha256 must be a SHA-256 digest")

    if "zig_cli" in data:
        zig_cli = _require(data["zig_cli"], "zig_cli", dict)
        digest = _require(zig_cli.get("binary_sha256"), "zig_cli.binary_sha256", str)
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise BenchmarkError("zig_cli.binary_sha256 must be a SHA-256 digest")
        if _require(zig_cli.get("samples"), "zig_cli.samples", int) < 1:
            raise BenchmarkError("zig_cli.samples must be positive")
        measurements = _require(zig_cli.get("workloads"), "zig_cli.workloads", dict)
        if set(measurements) != set(workloads):
            raise BenchmarkError("Zig CLI workloads do not match the measured workloads")
        for path, row in [("startup", zig_cli.get("startup")), *(
            (f"{name}.{phase}", measurements[name].get(phase)) for name in measurements for phase in PHASES
        )]:
            _require(row, f"zig_cli.{path}", dict)
            _require_stats(row.get("wall_ms"), f"zig_cli.{path}.wall_ms")
            _require_stats(row.get("peak_rss_mib"), f"zig_cli.{path}.peak_rss_mib")

    if "previous_release" in data:
        previous = _require(data["previous_release"], "previous_release", dict)
        if "previous_release" in previous:
            raise BenchmarkError("previous_release must not contain another comparison")
        validate_results(previous)
        git = previous["environment"]["git"]
        if previous["smoke"] or git["dirty"] or not git.get("release_tag"):
            raise BenchmarkError("previous release must be a clean release measurement")


# --------------------------------------------------------------------------- markdown


def _ms(value: float) -> str:
    if value >= 100:
        return f"{value:,.0f} ms"
    if value >= 10:
        return f"{value:.1f} ms"
    return f"{value:.2f} ms"


def _mib(value: float) -> str:
    return f"{value:.1f} MiB"


def _with_delta(value: float, previous: float | None, format_value: Any) -> str:
    rendered = format_value(value)
    if previous is None or previous <= 0:
        return rendered + " (n/a)"
    return rendered + f" ({(value / previous - 1) * 100:+.1f}%)"


def _comparable_workload(current: dict[str, Any], previous: dict[str, Any], name: str) -> bool:
    now = current["workloads"].get(name)
    before = previous["workloads"].get(name)
    if not now or not before:
        return False
    return all(now.get(key) == before.get(key) for key in (
        "parse_modules", "parse_size", "validate_module", "instance_sha256", "instance_bytes"
    ))


def render_markdown(data: dict[str, Any]) -> str:
    validate_results(data)
    env = data["environment"]
    git, ver, rt, mach = env["git"], env["versions"], env["runtimes"], env["machine"]
    langs = [lang for lang in LANGUAGES if lang in data["results"]]
    label = {"python": "Python", "typescript": "TypeScript"}
    previous = data.get("previous_release")

    def measured(lang: str, name: str | None, phase: str, metric: str, formatter: Any) -> str:
        def value(result: dict[str, Any]) -> float:
            row = result["results"][lang]
            return (row["startup"][metric]["median"] if name is None else
                    row["workloads"][name][phase]["timing" if metric == "time_ms" else "memory"][metric]["median"])
        current = value(data)
        if previous is None:
            return formatter(current)
        old = None
        if lang in previous["results"] and (name is None or _comparable_workload(data, previous, name)):
            old = value(previous)
        return _with_delta(current, old, formatter)
    tag = f" (release `{git['release_tag']}`)" if git.get("release_tag") else ""
    mem = f", {mach['mem_total_gib']} GiB RAM" if mach.get("mem_total_gib") else ""
    lines = [
        "_Generated by `benchmarks/release_bench.py`; do not edit by hand. "
        "Methodology and limitations: [benchmarks/README.md](benchmarks/README.md)._",
        "",
        f"- **Version:** xyang {ver['python_package']} (PyPI), @exergy-connect/xyang {ver['ts_package']} (npm){tag}",
        f"- **Commit:** `{git['commit'][:12]}`, measured {data['generated_at']}",
        f"- **Runtimes:** {rt['python']}, Node.js {rt.get('node') or 'n/a'}",
        f"- **Machine:** {mach['runner']}; {mach['os']} {mach['arch']}; {mach['cpu']} "
        f"({mach['cpu_count']} logical CPUs{mem})",
        "",
    ]
    if previous is not None:
        previous_tag = previous["environment"]["git"]["release_tag"]
        lines += [f"Percentage changes compare with `{previous_tag}`; positive means more time or memory. "
                  "Different runners can affect results; `n/a` means the workload or baseline is not comparable.", ""]
    first = data["results"][langs[0]]
    header = "| Workload | Phase | " + " | ".join(f"{label[lang]} median" for lang in langs) + " | Timed iterations |"
    lines += ["Time (warm, in-process, measured call only):", "", header, "|" + "---|" * (3 + len(langs))]
    for name in data["workloads"]:
        for phase in PHASES:
            ref = first["workloads"][name][phase]["timing"]
            cells = [measured(lang, name, phase, "time_ms", _ms) for lang in langs]
            iters = (
                f"{ref['iterations']} ({ref['processes']} processes × {ref['iterations_per_process']}, "
                f"{ref['warmup_per_process']} warmup each)"
            )
            lines.append(f"| {name} | {phase} | " + " | ".join(cells) + f" | {iters} |")
    cells = [measured(lang, None, "", "wall_ms", _ms) + " wall" for lang in langs]
    lines.append(f"| none | process startup | " + " | ".join(cells) + f" | {first['startup']['processes']} processes |")

    header = "| Workload | Operation | " + " | ".join(f"{label[lang]} peak RSS" for lang in langs) + " | Processes |"
    lines += [
        "",
        "Peak process memory (fresh process, one operation, no warmup; total process peak):",
        "",
        header,
        "|" + "---|" * (3 + len(langs)),
    ]
    for name in data["workloads"]:
        for phase in PHASES:
            ref = first["workloads"][name][phase]["memory"]
            cells = [measured(lang, name, phase, "peak_rss_mib", _mib) for lang in langs]
            lines.append(
                f"| {name} | {MEMORY_OPERATION[phase]} | " + " | ".join(cells)
                + f" | {ref['processes']} × {ref['operations_per_process']} operation |"
            )
    cells = [measured(lang, None, "", "peak_rss_mib", _mib) for lang in langs]
    lines.append(f"| none | process startup (library loaded) | " + " | ".join(cells) + f" | {first['startup']['processes']} |")
    rss_sources = ", ".join(
        sorted(
            {
                p["memory"]["rss_source"]
                for lang in langs
                for phases in data["results"][lang]["workloads"].values()
                for p in phases.values()
            }
            | {data["results"][lang]["startup"]["rss_source"] for lang in langs}
        )
    )
    rss_sources = rss_sources.replace("VmHWM", "Linux `VmHWM`").replace("ru_maxrss", "`getrusage` maxrss")
    if "zig_cli" in data:
        zig = data["zig_cli"]
        old_zig = previous.get("zig_cli") if previous else None
        lines += ["", "Zig CLI (end-to-end process time; not comparable with the in-process timings above):", "",
                  "| Workload | Command | Median wall time | Peak RSS |", "|---|---|---:|---:|"]
        for name in data["workloads"]:
            for phase in PHASES:
                entry = zig["workloads"][name][phase]
                old = (old_zig["workloads"].get(name, {}).get(phase)
                       if old_zig and _comparable_workload(data, previous, name) else None)
                wall = entry["wall_ms"]["median"]
                memory = entry["peak_rss_mib"]["median"]
                wall_text = _with_delta(wall, old["wall_ms"]["median"] if old else None, _ms) if previous else _ms(wall)
                mem_text = _with_delta(memory, old["peak_rss_mib"]["median"] if old else None, _mib) if previous else _mib(memory)
                lines.append(f"| {name} | {phase} | {wall_text} | {mem_text} |")
        start = zig["startup"]
        old_start = old_zig["startup"] if old_zig else None
        wall = start["wall_ms"]["median"]
        memory = start["peak_rss_mib"]["median"]
        wall_text = _with_delta(wall, old_start["wall_ms"]["median"] if old_start else None, _ms) if previous else _ms(wall)
        mem_text = _with_delta(memory, old_start["peak_rss_mib"]["median"] if old_start else None, _mib) if previous else _mib(memory)
        lines.append(f"| none | --version | {wall_text} | {mem_text} |")
        lines += ["", f"Medians of {zig['samples']} fresh-process samples. Parse runs one CLI process per module "
                  "and sums their wall times; its RSS is the largest individual process peak. Validation includes "
                  "startup, file I/O, schema loading and JSON decoding. RSS comes from separate GNU time runs."]
    lines += ["", "Workloads:", ""]
    for name, desc in data["workloads"].items():
        size = desc["parse_size"]
        entries = f", {desc['list_entries']:,} list entries" if desc.get("list_entries") else ""
        lines.append(
            f"- **{name}** ({desc['title']}): parse {size['files']} module(s), {size['lines']:,} YANG lines; "
            f"validate `{desc['validate_module']}` against {desc['instance_bytes']:,} bytes of JSON{entries} "
            f"({desc['instance_note']})."
        )
    lines += [
        "",
        "Time is the median over all timed iterations of the measured call only (no startup, imports, file "
        "reads, or setup). Memory comes from separate fresh processes, not the timing processes: each loads the "
        "runtime and library, does the setup, runs the operation once, and reports its own high-water resident "
        f"set size ({rss_sources}). The figure is the median over processes in MiB (2^20 bytes) and is the whole "
        "process peak: runtime, library, setup, inputs, the operation, and garbage not yet collected. No startup "
        "baseline is subtracted, no garbage collection is forced, and no runtime flags are set. The startup rows "
        "are processes that only load the library.",
        "",
        "Code size (separate from performance; nonblank, noncomment lines, docstrings excluded):",
        "",
        "| Language | Counted | Files | Code lines |",
        "|---|---|---|---|",
    ]
    for lang in LANGUAGES:
        info = data["code_size"]["languages"][lang]
        lines.append(f"| {label[lang]} | `{info['root']}/{info['pattern']}` | {info['files']} | {info['code_lines']:,} |")
    if "binary_size" in data:
        zig = data["binary_size"]["zig"]
        lines += [
            "", "Executable size:", "",
            "| Binary | Bytes | KiB |",
            "|---|---:|---:|",
            f"| Zig CLI (`{zig['file']}`) | {zig['bytes']:,} | {zig['bytes'] / 1024:,.1f} |",
        ]
    lines += ["", f"Reproduce: `{data['reproduce']}`"]
    return "\n".join(lines) + "\n"


def replace_section(readme: str, body: str) -> str:
    if readme.count(README_START) != 1 or readme.count(README_END) != 1:
        raise BenchmarkError(f"README must contain exactly one {README_START} and one {README_END}")
    head, rest = readme.split(README_START, 1)
    _, tail = rest.split(README_END, 1)
    return f"{head}{README_START}\n{body.rstrip()}\n{README_END}{tail}"


def update_readme(results_path: Path, readme_path: Path, check: bool, allow_dirty: bool) -> int:
    data = json.loads(results_path.read_text(encoding="utf-8"))
    validate_results(data)
    if data["smoke"]:
        raise BenchmarkError("refusing to put smoke-run numbers in the README")
    if data["environment"]["git"]["dirty"] and not allow_dirty:
        raise BenchmarkError("results were measured on a dirty tree; rerun on a clean commit or pass --allow-dirty")
    current = readme_path.read_text(encoding="utf-8")
    updated = replace_section(current, render_markdown(data))
    if check:
        if updated != current:
            print(f"{readme_path} benchmark section is out of date with {results_path}", file=sys.stderr)
            return 1
        return 0
    if updated != current:
        readme_path.write_text(updated, encoding="utf-8")
    return 0


# --------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run", help="measure and write results JSON")
    p_run.add_argument("--out", type=Path, required=True)
    p_run.add_argument("--languages", default=",".join(LANGUAGES))
    p_run.add_argument("--workloads", default=",".join(WORKLOADS))
    p_run.add_argument("--processes", type=int, default=3, help="timing processes per phase")
    p_run.add_argument("--memory-processes", type=int, default=MEMORY_PROCESSES, help="one-operation memory processes per phase")
    p_run.add_argument("--smoke", action="store_true", help="1 process, 1 iteration, no warmup (not for README)")
    p_run.add_argument("--release-tag", default=None)
    p_run.add_argument("--zig-binary", type=Path, help="include this Zig executable's size and SHA-256")
    p_run.add_argument("--zig-cli", type=Path, help="benchmark this Zig CLI end to end (requires GNU time on Linux)")
    p_render = sub.add_parser("render", help="print the Markdown section for a results file")
    p_render.add_argument("results", type=Path)
    p_readme = sub.add_parser("update-readme", help="rewrite the marked README section from a results file")
    p_readme.add_argument("results", type=Path)
    p_readme.add_argument("--readme", type=Path, default=ROOT / "README.md")
    p_readme.add_argument("--check", action="store_true", help="exit 1 if the README section is out of date")
    p_readme.add_argument("--allow-dirty", action="store_true")
    p_validate = sub.add_parser("validate", help="check a results file against the schema")
    p_validate.add_argument("results", type=Path)
    p_compare = sub.add_parser("compare", help="embed the previous release measurement in a results file")
    p_compare.add_argument("results", type=Path)
    p_compare.add_argument("previous", type=Path)
    p_compare.add_argument("--previous-tag", required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "run":
            languages = [x for x in args.languages.split(",") if x]
            names = [x for x in args.workloads.split(",") if x]
            for x in languages:
                if x not in LANGUAGES:
                    raise BenchmarkError(f"unknown language {x!r}")
            for x in names:
                if x not in WORKLOADS:
                    raise BenchmarkError(f"unknown workload {x!r}")
            data = run(languages, names, args.processes, args.smoke, args.release_tag, args.memory_processes, args.zig_binary, args.zig_cli)
            validate_results(data)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            return 0
        if args.command == "render":
            sys.stdout.write(render_markdown(json.loads(args.results.read_text(encoding="utf-8"))))
            return 0
        if args.command == "update-readme":
            return update_readme(args.results, args.readme, args.check, args.allow_dirty)
        if args.command == "compare":
            data = json.loads(args.results.read_text(encoding="utf-8"))
            previous = json.loads(args.previous.read_text(encoding="utf-8"))
            previous.pop("previous_release", None)
            validate_results(data)
            validate_results(previous)
            if previous["environment"]["git"].get("release_tag") != args.previous_tag:
                raise BenchmarkError("previous results do not match the requested release tag")
            data["previous_release"] = previous
            validate_results(data)
            args.results.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            return 0
        validate_results(json.loads(args.results.read_text(encoding="utf-8")))
        return 0
    except BenchmarkError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
