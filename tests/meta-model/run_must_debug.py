#!/usr/bin/env python3
"""Run failing computed must tests with xpath evaluator debug trace.

Usage:
  PYTHONPATH=src python3 tests/meta-model/run_must_debug.py
  # or from repo root:
  python3 tests/meta-model/run_must_debug.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure src is on path
repo = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo / "src"))

# Enable debug for the xpath evaluator only
logging.basicConfig(level=logging.WARNING, format="%(message)s")
log = logging.getLogger("xyang.xpath.evaluator")
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler(sys.stderr))

import pytest  # noqa: E402

if __name__ == "__main__":
    args = [
        "tests/meta-model/test_must.py::test_computed_reference_exists_valid",
        "tests/meta-model/test_must.py::test_computed_cross_entity_fk_valid",
        "-v",
    ]
    sys.exit(pytest.main(args))
