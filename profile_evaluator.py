#!/usr/bin/env python3
"""
Profile XPathEvaluator usage across all meta-model tests using native Python profiling.

This script:
1. Uses cProfile to track all function calls
2. Runs all meta-model tests
3. Analyzes which evaluator methods are called and which are dead code
"""

import sys
import cProfile
import pstats
import io
from pathlib import Path
import pytest
import re


def run_meta_model_tests_with_profiling():
    """Run all meta-model tests with profiling."""
    # Find all meta-model test files
    test_dir = Path(__file__).parent / "tests" / "meta-model"
    
    print("=" * 80)
    print("XPathEvaluator Method Profiling (using cProfile)")
    print("=" * 80)
    print()
    print(f"Running tests in: {test_dir}")
    print()
    
    # Create profiler
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Run pytest on meta-model tests
    pytest_args = [
        str(test_dir),
        "-v",
        "--tb=short",
    ]
    
    exit_code = pytest.main(pytest_args)
    
    profiler.disable()
    
    # Analyze results
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s)
    ps.sort_stats('cumulative')
    ps.print_stats()
    
    profile_output = s.getvalue()
    
    # Extract evaluator method calls
    evaluator_methods = extract_evaluator_methods(profile_output)
    
    # Get all methods in evaluator
    all_methods = get_all_evaluator_methods()
    
    # Report results
    print()
    print("=" * 80)
    print("Profiling Results")
    print("=" * 80)
    print()
    
    called_methods = set(evaluator_methods.keys())
    
    if called_methods:
        print(f"Called methods ({len(called_methods)}):")
        for method in sorted(called_methods):
            count = evaluator_methods.get(method, 0)
            print(f"  ✓ {method:50s} ({count:6d} calls)")
        print()
    
    # Report dead code (methods never called)
    dead_methods = all_methods - called_methods
    if dead_methods:
        print(f"Dead code - methods never called ({len(dead_methods)}):")
        for method in sorted(dead_methods):
            print(f"  ✗ {method}")
    else:
        print("No dead code found - all methods were called!")
    
    print()
    print("=" * 80)
    
    return exit_code == 0


def extract_evaluator_methods(profile_output: str) -> dict:
    """Extract evaluator method calls from profile output."""
    methods = {}
    
    # Pattern to match evaluator method calls
    # Lines look like: "   12345    0.123    0.456  evaluator.py:123(method_name)"
    # Or: "   12345    0.123    0.456  {method} (evaluator.py:123)"
    pattern1 = r'evaluator\.py:\d+\(([^)]+)\)'
    pattern2 = r'\{method\}.*evaluator\.py:\d+'
    pattern3 = r'([a-zA-Z_][a-zA-Z0-9_]+).*evaluator\.py'
    
    for line in profile_output.split('\n'):
        # Look for lines containing evaluator.py
        if 'evaluator.py' in line:
            # Try pattern 1: evaluator.py:123(method_name)
            matches = re.findall(pattern1, line)
            for method_name in matches:
                # Extract call count from the line
                parts = line.split()
                if parts and parts[0].isdigit():
                    count = int(parts[0])
                    if method_name not in methods:
                        methods[method_name] = 0
                    methods[method_name] += count
            
            # Also try to extract from function names in the line
            # Look for method names before evaluator.py
            parts = line.split()
            for i, part in enumerate(parts):
                if 'evaluator.py' in part and i > 0:
                    # Previous part might be the method name
                    prev_part = parts[i-1]
                    if prev_part and not prev_part[0].isdigit():
                        # Extract method name (might be in parentheses or brackets)
                        method_match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]+)', prev_part)
                        if method_match:
                            method_name = method_match.group(1)
                            if parts[0].isdigit():
                                count = int(parts[0])
                                if method_name not in methods:
                                    methods[method_name] = 0
                                methods[method_name] += count
    
    return methods


def get_all_evaluator_methods() -> set:
    """Get all methods defined in XPathEvaluator."""
    import inspect
    from xYang.xpath.evaluator import XPathEvaluator
    
    methods = set()
    
    for name in dir(XPathEvaluator):
        if name.startswith('__') and name.endswith('__'):
            continue
        attr = getattr(XPathEvaluator, name)
        if inspect.isfunction(attr) or inspect.ismethod(attr):
            methods.add(name)
    
    return methods


def main():
    """Main profiling entry point."""
    success = run_meta_model_tests_with_profiling()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
