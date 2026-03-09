"""Pytest configuration: add src to PYTHONPATH so xyang is importable."""

import sys
from pathlib import Path

# Prepend src so "from xyang import ..." works when running pytest from project root
_root = Path(__file__).resolve().parent.parent
_src = _root / "src"
if _src.exists() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))
