#!/usr/bin/env python3
"""
Analyze cProfile output to find which evaluator methods are called.
"""

import pstats
import sys
from pathlib import Path
import inspect
from xYang.xpath.evaluator import XPathEvaluator


def analyze_profile(profile_file: str):
    """Analyze profile stats to find evaluator method calls."""
    stats = pstats.Stats(profile_file)
    
    # Get all methods in evaluator
    all_methods = set()
    for name in dir(XPathEvaluator):
        if name.startswith('__') and name.endswith('__'):
            continue
        attr = getattr(XPathEvaluator, name)
        if inspect.isfunction(attr) or inspect.ismethod(attr):
            all_methods.add(name)
    
    # Extract evaluator method calls from stats
    called_methods = set()
    method_counts = {}
    
    # Get all function names from stats
    for func_name, (cc, nc, tt, ct, callers) in stats.stats.items():
        filename, line_num, func = func_name
        if 'evaluator.py' in filename:
            # Extract method name - func can be like "method_name" or "<genexpr>"
            # Remove any trailing parentheses content
            if '(' in func:
                method_name = func.split('(')[0].strip()
            else:
                method_name = func.strip()
            
            # Skip special names like <genexpr>, <lambda>, <module>
            if method_name and not (method_name.startswith('<') and method_name.endswith('>')):
                called_methods.add(method_name)
                if method_name not in method_counts:
                    method_counts[method_name] = 0
                method_counts[method_name] += nc
    
    # Print results
    print("=" * 80)
    print("XPathEvaluator Method Usage Analysis")
    print("=" * 80)
    print()
    
    print(f"Total methods in XPathEvaluator: {len(all_methods)}")
    print(f"Methods called: {len(called_methods)}")
    print()
    
    if called_methods:
        print("Called methods:")
        for method in sorted(called_methods):
            count = method_counts.get(method, 0)
            print(f"  ✓ {method:50s} ({count:6d} calls)")
        print()
    
    # Dead code
    dead_methods = all_methods - called_methods
    if dead_methods:
        print(f"Dead code - methods never called ({len(dead_methods)}):")
        for method in sorted(dead_methods):
            print(f"  ✗ {method}")
    else:
        print("No dead code found!")
    
    print()
    print("=" * 80)
    
    # Also print a detailed view of evaluator.py calls
    print("\nDetailed evaluator.py function calls:")
    print("-" * 80)
    evaluator_calls = []
    for func_name, (cc, nc, tt, ct, callers) in stats.stats.items():
        filename, line_num, func = func_name
        if 'evaluator.py' in filename:
            evaluator_calls.append((func, nc, tt, ct))
    
    evaluator_calls.sort(key=lambda x: x[1], reverse=True)  # Sort by call count
    for func, nc, tt, ct in evaluator_calls[:30]:  # Top 30
        print(f"  {func:60s} {nc:8d} calls  {tt:8.4f}s total  {ct:8.4f}s cumulative")


if __name__ == "__main__":
    profile_file = sys.argv[1] if len(sys.argv) > 1 else "profile.stats"
    if not Path(profile_file).exists():
        print(f"Profile file not found: {profile_file}")
        print("Run: python3 -m cProfile -o profile.stats -m pytest tests/meta-model/ -q")
        sys.exit(1)
    
    analyze_profile(profile_file)
