#!/usr/bin/env python3
"""
Progressive parsing test - parses meta-model.yang line by line to find where it hangs.
"""

import sys
import signal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from xYang.parser import YangParser
from xYang.errors import YangSyntaxError


class TimeoutError(Exception):
    """Timeout exception."""
    pass


def timeout_handler(signum, frame):
    """Handle timeout signal."""
    raise TimeoutError("Parsing timed out")


def test_progressive_parse(yang_file_path: str, timeout_seconds: int = 5):
    """
    Progressively parse YANG file line by line until it hangs.
    
    Args:
        yang_file_path: Path to YANG file to parse
        timeout_seconds: Timeout in seconds for each parse attempt
    """
    yang_path = Path(yang_file_path)
    if not yang_path.exists():
        print(f"Error: File not found: {yang_file_path}")
        return
    
    # Read the file
    with open(yang_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print(f"Testing progressive parse of {yang_path.name}")
    print(f"Total lines: {len(lines)}")
    print(f"Timeout: {timeout_seconds} seconds per attempt")
    print("-" * 80)
    
    # Binary search approach: find the smallest number of lines that causes hang
    low = 1
    high = len(lines)
    last_working = 0
    
    while low <= high:
        mid = (low + high) // 2
        test_lines = lines[:mid]
        test_content = ''.join(test_lines)
        
        print(f"Testing with {mid} lines (range: {low}-{high})...", end=' ', flush=True)
        
        parser = YangParser()
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout_seconds)
        
        try:
            module = parser.parse_string(test_content)
            signal.alarm(0)  # Cancel alarm
            print(f"✓ SUCCESS - Parsed {mid} lines")
            print(f"  Module: {module.name}, Statements: {len(module.statements)}")
            last_working = mid
            low = mid + 1
        except TimeoutError:
            signal.alarm(0)  # Cancel alarm
            print(f"✗ TIMEOUT - Hangs at {mid} lines")
            high = mid - 1
        except YangSyntaxError as e:
            signal.alarm(0)  # Cancel alarm
            print(f"✗ SYNTAX ERROR - {str(e)[:100]}")
            # Syntax errors are expected for incomplete files, continue
            last_working = mid
            low = mid + 1
        except Exception as e:
            signal.alarm(0)  # Cancel alarm
            print(f"✗ ERROR - {type(e).__name__}: {str(e)[:100]}")
            # Other errors might indicate the problem, but continue
            last_working = mid
            low = mid + 1
    
    print("-" * 80)
    print(f"\nResult: Parsing works up to line {last_working}")
    print(f"Problem likely starts around line {last_working + 1}")
    
    if last_working < len(lines):
        print(f"\nLines {last_working} to {min(last_working + 10, len(lines))}:")
        for i in range(last_working, min(last_working + 10, len(lines))):
            line_num = i + 1
            line_content = lines[i].rstrip()
            print(f"  {line_num:4d}: {line_content[:70]}")
    
    # Now test the exact problematic section by testing from start of file
    print("\n" + "=" * 80)
    print("Testing exact problematic section (from start of file)...")
    print("=" * 80)
    
    # Test progressively from the start, focusing on the problematic area
    test_points = [
        last_working,
        last_working + 1,
        last_working + 2,
        last_working + 3,
        last_working + 5,
        last_working + 10,
    ]
    
    for test_line_count in test_points:
        if test_line_count > len(lines):
            break
            
        test_lines = lines[:test_line_count]
        test_content = ''.join(test_lines)
        
        print(f"\nTesting first {test_line_count} lines...", end=' ', flush=True)
        
        parser = YangParser()
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout_seconds)
        
        try:
            module = parser.parse_string(test_content)
            signal.alarm(0)
            print(f"✓ SUCCESS")
        except TimeoutError:
            signal.alarm(0)
            print(f"✗ HANGS")
            print(f"\n  Problematic line {test_line_count}:")
            print("  " + "-" * 76)
            if test_line_count <= len(lines):
                print(f"  {test_line_count:4d}: {lines[test_line_count-1].rstrip()}")
            print("  " + "-" * 76)
            print(f"\n  Context (lines {max(1, test_line_count-5)} to {test_line_count}):")
            print("  " + "-" * 76)
            for i in range(max(0, test_line_count-6), test_line_count):
                marker = " >>>" if i == test_line_count - 1 else "    "
                print(f"  {i+1:4d}{marker}: {lines[i].rstrip()}")
            print("  " + "-" * 76)
            break
        except YangSyntaxError as e:
            signal.alarm(0)
            # Syntax errors are expected for incomplete files
            print(f"✗ Syntax error (expected for incomplete file)")
        except Exception as e:
            signal.alarm(0)
            print(f"✗ Error: {type(e).__name__}: {str(e)[:100]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Default to meta-model.yang in xTract
        default_path = Path(__file__).parent.parent / "xTract" / "src" / "xtract" / "yang" / "meta-model.yang"
        if default_path.exists():
            yang_file = str(default_path)
        else:
            print("Usage: python test_progressive_parse.py <path-to-yang-file>")
            sys.exit(1)
    else:
        yang_file = sys.argv[1]
    
    timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    test_progressive_parse(yang_file, timeout)
