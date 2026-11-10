"""Shared conformance cases (tests/cases, see README there) run against the Python implementation."""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

from xyang import YangValidator, parse_yang_file

CASES = Path(__file__).parent / "cases"
CODES = [(code, re.compile(rx)) for code, rx in json.loads((CASES / "error-codes.json").read_text())["codes"]]
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


def _split(err):
    """'<path>: <message>' -> (path, message); the path may contain ': ' inside [...] predicates."""
    depth = 0
    for i, ch in enumerate(err):
        depth += {"[": 1, "]": -1}.get(ch, 0)
        if depth == 0 and err.startswith(": ", i) and " " not in err[:i]:
            return err[:i], err[i + 2 :]
    return "", err


def _pointer(path, data):
    """Python path (/top/items[id='a']/tags[0]) -> JSON Pointer into data (/top/items/0/tags/0)."""
    out, node = [], data
    for seg in [s for s in re.split(r"/(?![^\[]*\])", path) if s]:
        name, pred = re.match(r"([^\[]+)(?:\[(.*)\])?$", seg).groups()
        node = node.get(name) if isinstance(node, dict) else None
        out.append(name)
        if pred is not None:
            keys = dict(re.findall(r"([^\s=,]+)='([^']*)'", pred))
            idx = (
                int(pred)
                if pred.isdigit()
                else next(
                    (i for i, e in enumerate(node or []) if all(str(e.get(k)) == v for k, v in keys.items())), pred
                )
            )
            node = node[idx] if isinstance(idx, int) and isinstance(node, list) else None
            out.append(str(idx))
    return "".join("/" + s for s in out)


def _code(message, expected):
    hint = next((e["code"] for e in expected if e.get("message") and e["message"] in message), None)
    return hint or next((code for code, rx in CODES if rx.search(message)), "unclassified")


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
    _ok, errors, _warnings = YangValidator(parsed, enabled_features_by_module=case.get("features")).validate(data)
    return [(_pointer(p, data), None, m) for p, m in map(_split, errors)]


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
    got = sorted({(p, c or _code(m, expected)) for p, c, m in raw})
    assert got == sorted({(e["path"], e["code"]) for e in expected}), f"raw errors: {raw}"
    assert inst["valid"] == (not raw)
