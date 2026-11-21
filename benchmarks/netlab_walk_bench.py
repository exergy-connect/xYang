"""Measure warm Python validation of a synthetic Netlab ring.

Run from the repository root: python benchmarks/netlab_walk_bench.py
Module parsing and validator construction are excluded from the measurements.
"""

from statistics import median
from time import perf_counter

from xyang import YangValidator, parse_yang_file


def main() -> None:
    validator = YangValidator(parse_yang_file("examples/netlab/netlab.yang"))
    for count in (100, 1000):
        data = {
            "groups": {"lab": {"members": ["n0"]}},
            "nodes": {f"n{i}": None for i in range(count)},
            "links": [f"n{i}-n{(i + 1) % count}" for i in range(count)],
        }
        result = validator.validate_detailed(data, native_json=True)
        if result["errors"]:
            raise ValueError(result["errors"])
        samples = []
        for _ in range(5):
            start = perf_counter()
            result = validator.validate_detailed(data, native_json=True)
            samples.append((perf_counter() - start) * 1000)
            if result["errors"]:
                raise ValueError(result["errors"])
        print(f"{count}: {median(samples):.1f} ms")


if __name__ == "__main__":
    main()
