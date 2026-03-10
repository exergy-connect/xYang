"""
Performance benchmarks for xYang library.
"""

import time
import statistics
from pathlib import Path
from typing import List, Dict, Any

from xyang import parse_yang_file, parse_yang_string, YangValidator
from xyang.xpath import Context, Node, XPathEvaluator, XPathParser


def _xpath_context(data: Dict[str, Any], context_path: List[str]):
    """Build root Node, context node at path, and Context for XPath evaluation."""
    root = Node(data, None, None)
    node = root
    for key in context_path:
        val = node.data.get(key) if isinstance(node.data, dict) else None
        node = node.step(val, None)
    ctx = Context(current=node, root=root, path_cache={})
    return root, node, ctx


class Benchmark:
    """Benchmark runner."""

    def __init__(self):
        self.results: Dict[str, List[float]] = {}

    def time_function(self, func, *args, **kwargs):
        """Time a function execution."""
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        return (end - start) * 1000, result  # Return time in milliseconds

    def run_benchmark(self, name: str, func, iterations: int = 10, *args, **kwargs):
        """Run a benchmark multiple times and collect statistics."""
        times = []
        for _ in range(iterations):
            elapsed, _ = self.time_function(func, *args, **kwargs)
            times.append(elapsed)

        self.results[name] = times
        mean = statistics.mean(times)
        median = statistics.median(times)
        stdev = statistics.stdev(times) if len(times) > 1 else 0
        min_time = min(times)
        max_time = max(times)

        print(f"{name}:")
        print(f"  Mean:   {mean:.3f} ms")
        print(f"  Median: {median:.3f} ms")
        print(f"  StdDev: {stdev:.3f} ms")
        print(f"  Min:    {min_time:.3f} ms")
        print(f"  Max:    {max_time:.3f} ms")
        print()

    def compare(self, name1: str, name2: str):
        """Compare two benchmark results."""
        if name1 not in self.results or name2 not in self.results:
            print("Cannot compare - one or both benchmarks not found")
            return

        mean1 = statistics.mean(self.results[name1])
        mean2 = statistics.mean(self.results[name2])
        improvement = ((mean1 - mean2) / mean1) * 100

        print(f"Comparison: {name1} vs {name2}")
        print(f"  {name1}: {mean1:.3f} ms")
        print(f"  {name2}: {mean2:.3f} ms")
        print(f"  Improvement: {improvement:+.1f}%")
        print()


def benchmark_parse_file():
    """Benchmark parsing YANG file."""
    file_path = Path("examples/meta-model.yang")
    def parse():
        return parse_yang_file(str(file_path))
    return parse


def benchmark_parse_string():
    """Benchmark parsing YANG from string."""
    file_path = Path("examples/meta-model.yang")
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    def parse():
        return parse_yang_string(content)
    return parse


def benchmark_validation():
    """Benchmark data validation. Returns (validate_callable, validator) for cache stats."""
    file_path = Path("examples/meta-model.yang")
    module = parse_yang_file(str(file_path))
    validator = YangValidator(module)

    # Create test data
    data = {
        "data-model": {
            "name": "test",
            "version": "26.01.15.1",
            "entities": [
                {
                    "name": "server",
                    "primary_key": ["id"],
                    "fields": [
                        {"name": "id", "type": "string"},
                        {"name": "name", "type": "string"},
                        {"name": "status", "type": "string"}
                    ]
                }
            ]
        }
    }

    def validate():
        return validator.validate(data)

    return validate, validator


def print_path_cache_stats(validator: YangValidator) -> None:
    """Print XPath path cache hit ratio and efficiency stats."""
    stats = validator._doc_validator._evaluator.get_cache_stats()
    if stats["lookups"] == 0:
        print("  Path cache: no lookups (no path evaluation)")
        return
    print(f"  Path cache: {stats['hits']}/{stats['lookups']} hits ({stats['hit_ratio']:.1%})")


def benchmark_xpath_simple():
    """Benchmark simple XPath expressions."""
    data = {"name": "test_value_with_underscores"}
    root, node, ctx = _xpath_context(data, ["name"])
    evaluator = XPathEvaluator()
    ast = XPathParser("string-length(.)").parse()

    def evaluate():
        return evaluator.eval(ast, ctx, node)
    return evaluate


def benchmark_xpath_complex():
    """Benchmark complex XPath expressions."""
    data = {
        "entity": {
            "name": "server",
            "fields": [
                {"name": "id", "type": "string"},
                {"name": "name", "type": "string"},
                {"name": "items", "type": "array"}
            ]
        }
    }
    root, node, ctx = _xpath_context(data, ["entity", "name"])
    evaluator = XPathEvaluator()
    ast = XPathParser(
        'string-length(.) - string-length(translate(., "_", "")) <= ../../max_underscores'
    ).parse()

    def evaluate():
        return evaluator.eval(ast, ctx, node)
    return evaluate


def benchmark_xpath_count():
    """Benchmark XPath count() function."""
    data = {
        "fields": [
            {"name": "id", "type": "string"},
            {"name": "name", "type": "string"},
            {"name": "items", "type": "array"},
            {"name": "status", "type": "string"},
            {"name": "tags", "type": "array"}
        ]
    }
    # Context at root (container) so path "fields" resolves
    root, node, ctx = _xpath_context(data, [])
    evaluator = XPathEvaluator()
    ast = XPathParser('count(fields[type != "array"])').parse()

    def evaluate():
        return evaluator.eval(ast, ctx, node)
    return evaluate


def benchmark_type_validation():
    """Benchmark type validation."""
    from xyang import TypeSystem
    from xyang.types import TypeConstraint

    type_system = TypeSystem()
    constraint = TypeConstraint(
        pattern=r'[a-z_][a-z0-9_]*',
        length="1..64"
    )
    type_system.register_typedef("entity-name", "string", constraint)

    def validate():
        is_valid, _ = type_system.validate("server_name", "entity-name")
        return is_valid
    return validate


def main():
    """Run all benchmarks."""
    print("=" * 60)
    print("xYang Performance Benchmarks")
    print("=" * 60)
    print()

    bench = Benchmark()

    # Parsing benchmarks
    print("Parsing Benchmarks:")
    print("-" * 60)
    bench.run_benchmark("Parse File", benchmark_parse_file(), iterations=5)
    bench.run_benchmark("Parse String", benchmark_parse_string(), iterations=5)

    # Validation benchmarks
    print("Validation Benchmarks:")
    print("-" * 60)
    validate, validator = benchmark_validation()
    bench.run_benchmark("Validate Data", validate, iterations=20)
    print_path_cache_stats(validator)

    # XPath benchmarks
    print("XPath Evaluation Benchmarks:")
    print("-" * 60)
    bench.run_benchmark("XPath Simple", benchmark_xpath_simple(), iterations=1000)
    bench.run_benchmark("XPath Complex", benchmark_xpath_complex(), iterations=500)
    bench.run_benchmark("XPath Count", benchmark_xpath_count(), iterations=500)

    # Type validation benchmarks
    print("Type Validation Benchmarks:")
    print("-" * 60)
    bench.run_benchmark("Type Validation", benchmark_type_validation(), iterations=1000)

    print("=" * 60)
    print("Benchmark Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
