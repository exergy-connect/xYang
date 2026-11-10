"""Parse and validation timings for the Python implementation.

Not run in CI. Usage from the repository root::

    python benchmarks/parse_bench.py            # timings
    python benchmarks/parse_bench.py --profile  # cProfile top functions per phase
"""

from __future__ import annotations

import argparse
import cProfile
import io
import logging
import pstats
import statistics
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xyang import YangValidator, parse_yang_file, parse_yang_string  # noqa: E402
from xyang.encoding.instance import iter_instance  # noqa: E402

PARSE_FILES = [
    "examples/ietf/ietf-alarms@2019-09-11.yang",
    "examples/ietf-yang-push/modules/ietf-subscribed-notifications@2019-09-09.yang",
    "examples/ietf-yang-push/modules/ietf-interfaces@2018-02-20.yang",
    "examples/meta-model.yang",
]

INSTANCE_MODULE = """
module bench {
  yang-version 1.1;
  namespace "urn:bench";
  prefix b;
  container top {
    list interface {
      key name;
      leaf name { type string; }
      leaf mtu { type int64 { range "0..9000"; } }
      leaf speed { type uint64; }
      leaf enabled { type boolean; }
      leaf descr { type string { length "0..64"; } }
      leaf-list tags { type string; }
    }
    leaf marker { type empty; }
  }
}
"""

ENTRIES = 10_000


def rfc_instance(n: int) -> dict[str, Any]:
    rows = [
        {
            "name": f"eth{i}",
            "mtu": str(1500),
            "speed": str(1000 * i),
            "enabled": i % 2 == 0,
            "descr": f"port {i}",
            "tags": ["a", "b"],
        }
        for i in range(n)
    ]
    return {"bench:top": {"interface": rows, "marker": [None]}}


def native_instance(n: int) -> dict[str, Any]:
    rows = {
        f"eth{i}": {
            "mtu": 1500,
            "speed": 1000 * i,
            "enabled": i % 2 == 0,
            "descr": f"port {i}",
            "tags": ["a", "b"],
        }
        for i in range(n)
    }
    return {"top": {"interface": rows, "marker": None}}


def _time(fn: Callable[[], Any], repeat: int) -> float:
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples)


def _parse_all() -> None:
    for rel in PARSE_FILES:
        path = ROOT / rel
        parse_yang_file(str(path), include_path=(str(path.parent),))


def phases() -> dict[str, Callable[[], Any]]:
    module = parse_yang_string(INSTANCE_MODULE)
    rfc = rfc_instance(ENTRIES)
    native = native_instance(ENTRIES)
    validator = YangValidator(module)

    def iterate_rfc() -> None:
        list(iter_instance(rfc, module, native_json=False))

    def iterate_native() -> None:
        list(iter_instance(native, module, native_json=True))

    def validate_rfc() -> None:
        result = validator.validate_detailed(rfc)
        assert result["valid"], result["errors"][:3]

    def validate_native() -> None:
        result = validator.validate_detailed(native, native_json=True)
        assert result["valid"], result["errors"][:3]

    return {
        "parse (4 largest common modules, cold)": _parse_all,
        f"iter_instance RFC ({ENTRIES} entries)": iterate_rfc,
        f"iter_instance native ({ENTRIES} entries)": iterate_native,
        f"validate RFC ({ENTRIES} entries)": validate_rfc,
        f"validate native ({ENTRIES} entries)": validate_native,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="store_true", help="print cProfile top functions per phase")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)

    for name, fn in phases().items():
        if args.profile:
            profiler = cProfile.Profile()
            profiler.enable()
            fn()
            profiler.disable()
            out = io.StringIO()
            pstats.Stats(profiler, stream=out).sort_stats("cumulative").print_stats(args.top)
            print(f"== {name}\n{out.getvalue()}")
        else:
            fn()
            print(f"{name:45s} {_time(fn, args.repeat) * 1000:9.1f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
