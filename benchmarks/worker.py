"""Python benchmark worker: one phase per process, spawned by release_bench.py.

argv[1] is a JSON spec: {"phase", "warmup", "iterations", "parse", "validate"}.
Prints one JSON line: {"samples_ms", "check", "peak_rss_bytes", "rss_source"}. Timing covers only
the measured call; interpreter startup, imports, file reads, JSON decoding, and
validator construction happen before the timed loop.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _timed(fn: Callable[[], Any], warmup: int, iterations: int) -> list[float]:
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        fn()
        samples.append((time.perf_counter_ns() - start) / 1e6)
    return samples


def peak_rss() -> tuple[int, str]:
    """Peak resident set size of this process in bytes, and where it came from."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) * 1024, "VmHWM"
    except OSError:
        pass
    import resource

    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return (maxrss if sys.platform == "darwin" else maxrss * 1024), "ru_maxrss"


def emit(samples: list[float], check: dict[str, Any]) -> None:
    rss, source = peak_rss()
    print(json.dumps({"samples_ms": samples, "check": check, "peak_rss_bytes": rss, "rss_source": source}))


def main() -> int:
    spec = json.loads(sys.argv[1])
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)

    from xyang import YangValidator, parse_yang_file

    phase = spec["phase"]
    if phase == "startup":
        emit([], {})
        return 0

    if phase == "parse":
        modules = spec["parse"]

        def run() -> int:
            for m in modules:
                parse_yang_file(m["path"], include_path=tuple(m["include"]))
            return len(modules)

        check = {"modules": len(modules)}
    elif phase == "validate":
        target = spec["validate"]
        module = parse_yang_file(target["module"]["path"], include_path=tuple(target["module"]["include"]))
        data = json.loads(Path(target["instance"]).read_text(encoding="utf-8"))
        validator = YangValidator(module)

        def run() -> None:
            result = validator.validate_detailed(data)
            if not result["valid"]:
                raise SystemExit(f"workload instance is invalid: {result['errors'][:3]}")

        check = {"valid": True}
    else:
        raise SystemExit(f"unknown phase {phase!r}")

    samples = _timed(run, int(spec["warmup"]), int(spec["iterations"]))
    emit(samples, check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
