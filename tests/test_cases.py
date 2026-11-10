"""Shared conformance cases (tests/cases, see README there) run against the Python implementation."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from xyang import YangValidator, parse_yang_file

CASES = Path(__file__).parent / "cases"
# TODO: the CLI does not implement `validate --format json` yet; see tests/cases/README.md for the protocol.
IMPLS = ["python"] + (["cli"] if os.environ.get("XYANG_CLI") else [])


def _params():
    for f in sorted(CASES.rglob("case.json")):
        case, cid = json.loads(f.read_text()), f.parent.relative_to(CASES).as_posix()
        for impl in IMPLS:
            for inst in case.get("instances") or [{"name": "schema error"}]:
                reason = {**case.get("xfail", {}), **inst.get("xfail", {})}.get(impl)
                marks = [pytest.mark.xfail(reason=reason, strict=True)] if reason else []
                yield pytest.param(f.parent, case, inst, impl, id=f"{impl}:{cid}:{inst['name']}", marks=marks)


def _validate(impl, case_dir, case, data):
    """Returns [(json_pointer, code, message)]; raises if the schema is rejected."""
    module = case_dir / case["module"]
    if impl == "cli":
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(data, fh)
        cmd = [os.environ["XYANG_CLI"], "validate", "--format", "json", str(module), fh.name]
        cmd += ["--include-path", str(case_dir), "--features", json.dumps(case.get("features"))]
        out = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=False).stdout)
        return [(e["path"], e["code"], e.get("message", "")) for e in out["errors"]]
    parsed = parse_yang_file(module, include_path=(str(case_dir),))
    if data is None:
        return []
    result = YangValidator(parsed, enabled_features_by_module=case.get("features")).validate_detailed(data)
    return [(e["path"], e["code"], e.get("message", "")) for e in result["errors"]]


@pytest.mark.parametrize("case_dir,case,inst,impl", list(_params()))
def test_case(case_dir, case, inst, impl):
    if case.get("schema_error"):
        with pytest.raises(Exception) as excinfo:
            _validate(impl, case_dir, case, None)
        if case.get("code"):
            assert case["code"] in str(excinfo.value)
        return
    expected = inst.get("errors", [])
    raw = _validate(impl, case_dir, case, inst["data"])
    got = sorted({(p, c) for p, c, _m in raw})
    assert got == sorted({(e["path"], e["code"]) for e in expected}), f"raw errors: {raw}"
    for exp in expected:
        if exp.get("message"):
            assert any(exp["message"] in m for _p, c, m in raw if c == exp["code"]), f"raw errors: {raw}"
    assert inst["valid"] == (not raw)
