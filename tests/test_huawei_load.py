"""Opt-in load of every module in a Huawei YANG directory.

Set ``XYANG_HUAWEI_DIR`` to the directory (for example
``network-router/8.22.0/ne8000-m4m8m14``). Prints the Python load rate.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

import pytest

from xyang import parse_yang_file


def _kind(exc: BaseException) -> str:
    line = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    return re.sub(r"^.*?:\s*\d+:\s*", "", line)


@pytest.mark.slow
def test_huawei_directory_load_rate(capsys: pytest.CaptureFixture[str]) -> None:
    raw = os.environ.get("XYANG_HUAWEI_DIR")
    if not raw:
        pytest.skip("set XYANG_HUAWEI_DIR to a directory of YANG modules")
    root = Path(raw)
    files = sorted(root.glob("*.yang"))
    if not files:
        pytest.fail(f"no .yang files in {root}")
    ok = 0
    errors: Counter[str] = Counter()
    for path in files:
        try:
            parse_yang_file(path, include_path=(str(root),))
            ok += 1
        except Exception as exc:
            errors[_kind(exc)] += 1
    rate = f"Python load rate: {ok}/{len(files)}"
    with capsys.disabled():
        print(rate)
        for message, count in errors.most_common(5):
            print(f"{count}\t{message}")
    assert ok <= len(files)
