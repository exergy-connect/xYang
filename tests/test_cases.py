"""Shared conformance cases (tests/cases, see README there) run against the Python implementation."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from xyang import YangValidator
from xyang.parser.yang_parser import YangParser

CASES = Path(__file__).parent / "cases"
IMPLS = ["python"] + (["cli"] if os.environ.get("XYANG_CLI") else [])


def _cli_follows_typescript() -> bool:
    """The TypeScript CLI is a ``.js`` program or an ``xyang-ts`` binary."""
    name = Path(os.environ.get("XYANG_CLI", "")).name
    return name.endswith(".js") or name.startswith("xyang-ts")


def _xfail_reason(case, inst, impl):
    """``cli`` keys mirror Python. The TypeScript CLI uses the ``ts`` keys."""
    merged = {**case.get("xfail", {}), **(inst.get("xfail") or {})}
    if impl == "cli" and _cli_follows_typescript():
        return merged.get("ts")
    return merged.get(impl)


def _params():
    for f in sorted(CASES.rglob("case.json")):
        case, cid = json.loads(f.read_text()), f.parent.relative_to(CASES).as_posix()
        for impl in IMPLS:
            for inst in case.get("instances") or [{"name": "schema error"}]:
                reason = _xfail_reason(case, inst, impl)
                marks = [pytest.mark.xfail(reason=reason, strict=True)] if reason else []
                yield pytest.param(f.parent, case, inst, impl, id=f"{impl}:{cid}:{inst['name']}", marks=marks)


def _load_case_module(case_dir: Path, module: Path):
    """Parse the case module. Other ``module`` files in the directory are loaded
    afterwards so their ``augment`` statements merge into the cached primary module.
    """
    parser = YangParser(include_path=(case_dir,))
    primary = module.resolve()
    parsed = parser.parse_file(primary)
    parser._module_cache[primary] = parsed
    for sibling in sorted(case_dir.glob("*.yang")):
        if sibling.resolve() == primary:
            continue
        if sibling.read_text(encoding="utf-8").lstrip().startswith("submodule"):
            continue
        parser.parse_file(sibling)
    return parsed


class UsageError(Exception):
    """The implementation rejected the call itself (the CLI exits 2)."""


def _write_json(value):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(value, fh)
        return fh.name


def _validate(impl, case_dir, case, data, *, native_json=False, operation=None):
    """Returns [(json_pointer, code, message)]; raises if the schema is rejected.

    ``operation`` is ``{"rpc", "action", "direction", "context"}`` (each optional, absent keys unset).
    A rejected call raises ``UsageError``.
    """
    module = case_dir / case["module"]
    operation = operation or {}
    if impl == "cli":
        data_path = _write_json(data)
        context_path = _write_json(operation["context"]) if "context" in operation else None
        cmd = [os.environ["XYANG_CLI"], "validate", "--format", "json", str(module), data_path]
        if native_json:
            cmd.insert(2, "--native-json")
        if operation.get("rpc") is not None:
            cmd += ["--rpc", operation["rpc"]]
        if operation.get("action") is not None:
            cmd += ["--action", operation["action"]]
        if operation.get("direction", "input") == "output":
            cmd.append("--output")
        if context_path:
            cmd += ["--context", context_path]
        cmd += ["--include-path", str(case_dir), "--features", json.dumps(case.get("features"))]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        finally:
            os.unlink(data_path)
            if context_path:
                os.unlink(context_path)
        if proc.returncode == 2 and not proc.stdout.strip():
            raise UsageError(proc.stderr.strip())
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            out = None
        if not isinstance(out, dict) or not isinstance(out.get("errors"), list):
            detail = (proc.stderr or proc.stdout).strip() or f"CLI exited {proc.returncode} without a validation result"
            raise RuntimeError(detail)
        return [(_where(e), e["code"], e.get("message", "")) for e in out["errors"]]
    parsed = _load_case_module(case_dir, module)
    if data is None:
        return []
    options = {key: operation[key] for key in ("rpc", "action", "direction", "context") if key in operation}
    try:
        result = YangValidator(parsed, enabled_features_by_module=case.get("features")).validate_detailed(
            data, native_json=native_json, **options
        )
    except ValueError as exc:
        if operation:
            raise UsageError(str(exc)) from exc
        raise
    return [(_where(e), e["code"], e.get("message", "")) for e in result["errors"]]


def _where(issue):
    """``path`` for the instance; ``context:path`` for an issue about the server data context."""
    document = issue.get("document", "data")
    return issue["path"] if document == "data" else f"{document}:{issue['path']}"


@pytest.mark.parametrize("case_dir,case,inst,impl", list(_params()))
def test_case(case_dir, case, inst, impl):
    if case.get("schema_error"):
        with pytest.raises(Exception) as excinfo:
            _validate(impl, case_dir, case, None)
        if case.get("code"):
            assert case["code"] in str(excinfo.value)
        return
    expected = inst.get("errors", [])
    operation = {key: inst[key] for key in ("rpc", "action", "direction", "context") if key in inst}
    native = inst.get("encoding") == "native"
    if inst.get("usage_error"):
        with pytest.raises(UsageError) as excinfo:
            _validate(impl, case_dir, case, inst["data"], native_json=native, operation=operation)
        if impl != "cli":
            assert inst["usage_error"] in str(excinfo.value)
        return
    raw = _validate(impl, case_dir, case, inst["data"], native_json=native, operation=operation)
    got = sorted({(p, c) for p, c, _m in raw})
    assert got == sorted({(_where(e), e["code"]) for e in expected}), f"raw errors: {raw}"
    for exp in expected:
        if exp.get("message"):
            assert any(exp["message"] in m for _p, c, m in raw if c == exp["code"]), f"raw errors: {raw}"
    assert inst["valid"] == (not raw)
