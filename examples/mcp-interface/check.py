"""Check the MCP interface example end to end.

1. The checked-in out/tools-list*.json match a fresh compile (no drift).
2. Each tool is a well-formed MCP tool whose schemas are valid JSON Schema 2020-12.
3. Every call in session/valid.json passes the compiled standard interface.
4. xYang (Python, and TypeScript when ts/dist is built) gives exactly the
   errors in session/expected-errors.json for every session fixture.
5. Reports how many invalid sessions a plain JSON Schema check accepts.
6. rpc validation (xYang #149): each case in calls/cases.json, an rpc input
   or output checked with the session as context, gives exactly its errors,
   through the CLI's --rpc / --output / --context flags. Skipped, with a
   message, while xYang lacks rpc validation.

Usage: python check.py [--write]   (--write regenerates expected-errors.json)
Needs: pip install jsonschema
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import jsonschema

from compile_mcp import compile_tools

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MODELS = HERE / "models"
MODULE = MODELS / "example-topology-tools@2026-11-11.yang"
ROOT = "example-topology-tools:session"
TOOL_PREFIX = "example-topology-tools:"
TS_CLI = REPO / "ts" / "dist" / "cli.js"
# MCP 2025-11-25: names SHOULD be 1 to 128 characters of A-Z, a-z, 0-9, "_", "-" and ".".
TOOL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def fixtures() -> list[Path]:
    return [HERE / "session" / "valid.json", *sorted((HERE / "session" / "invalid").glob("*.json"))]


def run(cmd: list[str]) -> list[dict[str, str]]:
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
    if proc.returncode not in (0, 1):
        raise SystemExit(f"{cmd[0]} failed ({proc.returncode}): {proc.stderr.strip()}")
    errors = json.loads(proc.stdout)["errors"]
    return sorted(({k: e[k] for k in ("path", "code", "message")} for e in errors),
                  key=lambda e: (e["path"], e["code"], e["message"]))


def validate_py(path: Path) -> list[dict[str, str]]:
    return run([sys.executable, "-m", "xyang", "validate", "--format", "json",
                "--include-path", str(MODELS), str(MODULE), str(path)])


def validate_ts(path: Path) -> list[dict[str, str]]:
    return run(["node", str(TS_CLI), "validate", "--format", "json",
                "--include-path", str(MODELS), str(MODULE), str(path)])


def rpc_supported(cli: list[str]) -> bool:
    proc = subprocess.run([*cli, "validate", "--help"], capture_output=True, text=True, cwd=HERE)
    return "--rpc" in proc.stdout


def validate_rpc(cli: list[str], case: dict, tmp: Path) -> list[dict[str, str]]:
    data = tmp / "data.json"
    data.write_text(json.dumps(case["data"]))
    cmd = [*cli, "validate", "--format", "json", "--include-path", str(MODELS), "--rpc", case["rpc"]]
    if case["direction"] == "output":
        cmd.append("--output")
    if case["context"]:
        cmd += ["--context", str(HERE / case["context"])]
    return run([*cmd, str(MODULE), str(data)])


def plain_errors(session: dict, tools: dict[str, dict]) -> list[str]:
    """What a generic MCP server sees: each call checked alone against the standard interface."""
    found = []
    for i, call in enumerate(session[ROOT]["call"]):
        name = call["tool"].removeprefix(TOOL_PREFIX)
        tool = tools.get(name)
        if tool is None:
            found.append(f"call/{i}: unknown tool {name}")
            continue
        args = call.get("arguments", {})
        for err in jsonschema.Draft202012Validator(tool["inputSchema"]).iter_errors(args.get(name, {})):
            found.append(f"call/{i}/arguments: {err.message}")
        out = call.get("result", {}).get(name)
        if out is not None and "outputSchema" in tool:
            for err in jsonschema.Draft202012Validator(tool["outputSchema"]).iter_errors(out):
                found.append(f"call/{i}/result: {err.message}")
    return found


def main() -> int:
    write = "--write" in sys.argv[1:]

    # 1. No drift between the model and the checked-in interface.
    for profile, name in (("standard", "tools-list.json"), ("xyang", "tools-list.xyang.json")):
        fresh = compile_tools(MODULE, (MODELS,), profile)
        checked_in = json.loads((HERE / "out" / name).read_text())
        assert fresh == checked_in, f"out/{name} is stale: rerun compile_mcp.py"
    standard = json.loads((HERE / "out" / "tools-list.json").read_text())
    tools = {t["name"]: t for t in standard["tools"]}
    print(f"ok  out/ matches a fresh compile ({len(tools)} tools)")

    # 2. Well-formed MCP tools.
    for t in standard["tools"]:
        assert TOOL_NAME.match(t["name"]), t["name"]
        for key in ("inputSchema", "outputSchema"):
            if key in t:
                assert t[key].get("type") == "object", (t["name"], key)
                jsonschema.Draft202012Validator.check_schema(t[key])
    print("ok  every tool schema is JSON Schema 2020-12 with type object")

    # 3. The valid session agrees with the standard interface.
    valid = json.loads((HERE / "session" / "valid.json").read_text())
    assert plain_errors(valid, tools) == [], plain_errors(valid, tools)
    print("ok  every call in session/valid.json passes the standard interface")

    # 4. xYang verdicts, both runtimes.
    expected_path = HERE / "session" / "expected-errors.json"
    actual = {p.stem if p.parent.name == "invalid" else "valid": validate_py(p) for p in fixtures()}
    if write:
        expected_path.write_text(json.dumps(actual, indent=2) + "\n")
        print(f"wrote {expected_path.name}")
    expected = json.loads(expected_path.read_text())
    assert actual == expected, "Python verdicts differ from expected-errors.json"
    assert expected["valid"] == [] and all(expected[k] for k in expected if k != "valid")
    print(f"ok  Python: valid session passes, {len(expected) - 1} invalid sessions fail as expected")

    if TS_CLI.exists() and shutil.which("node"):
        for p in fixtures():
            key = p.stem if p.parent.name == "invalid" else "valid"
            ts = validate_ts(p)
            # Same verdict and same rules; TypeScript may word built-in type errors differently.
            assert [(e["path"], e["code"]) for e in ts] == [(e["path"], e["code"]) for e in expected[key]], key
        print("ok  TypeScript: same paths and codes for every fixture")
    else:
        print("--  TypeScript skipped (build ts/ first: cd ts && npm ci && npm run build)")

    # 6. rpc input and output, with the session as context.
    cases = json.loads((HERE / "calls" / "cases.json").read_text())
    clis = {"Python": [sys.executable, "-m", "xyang"]}
    if TS_CLI.exists() and shutil.which("node"):
        clis["TypeScript"] = ["node", str(TS_CLI)]
    for label, cli in clis.items():
        if not rpc_supported(cli):
            print(f"--  {label}: rpc cases skipped, needs rpc validation "
                  "(https://github.com/exergy-connect/xYang/issues/149)")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            for name, case in cases.items():
                got = validate_rpc(cli, case, Path(tmp))
                want = sorted(case["errors"], key=lambda e: (e["path"], e["code"], e["message"]))
                if label == "TypeScript":  # built-in type messages may be worded differently
                    got, want = [(e["path"], e["code"]) for e in got], [(e["path"], e["code"]) for e in want]
                assert got == want, f"{label} rpc case {name}: {got}"
        print(f"ok  {label}: {len(cases)} rpc cases give their expected errors")

    # 5. What plain JSON Schema misses.
    missed = [p.stem for p in fixtures()[1:]
              if not plain_errors(json.loads(p.read_text()), tools)]
    print(f"\n{len(missed)} of {len(fixtures()) - 1} invalid sessions pass a plain JSON Schema check of each call:")
    for name in missed:
        print(f"    {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
