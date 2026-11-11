"""Compile a YANG module's rpcs into an MCP tools/list result.

Each module-level rpc becomes one MCP tool:

    rpc name         -> tool.name
    rpc description  -> tool.description
    rpc input        -> tool.inputSchema   (JSON Schema 2020-12, type object)
    rpc output       -> tool.outputSchema  (when the rpc has an output)

Two profiles share the same source:

    standard  plain JSON Schema; every "x-yang" keyword is removed
    xyang     the same schemas with "x-yang" kept (must, when, leafref, ...).
              A generic validator ignores x-yang; an xYang-aware client or
              server enforces it.

Usage:
    python compile_mcp.py MODULE.yang [--include-path DIR]... [--profile standard|xyang] [-o OUT.json]
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from xyang.json import generate_json_schema
from xyang.parser import YangParser

XYANG = "x-yang"


def _strip_xyang(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _strip_xyang(v) for k, v in node.items() if k != XYANG}
    if isinstance(node, list):
        return [_strip_xyang(v) for v in node]
    return node


def _refs(node: Any, found: set[str]) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            found.add(ref[len("#/$defs/"):])
        for v in node.values():
            _refs(v, found)
    elif isinstance(node, list):
        for v in node:
            _refs(v, found)


def _self_contained(body: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """Copy the rpc input/output body and attach the $defs it references.

    The body's "#/$defs/..." references then resolve against the tool schema itself.
    """
    out = copy.deepcopy(body)
    out["type"] = "object"
    out.pop(XYANG, None)  # the rpc input/output marker, not a constraint
    needed: set[str] = set()
    pending = [out]
    while pending:
        found: set[str] = set()
        _refs(pending.pop(), found)
        for name in sorted(found - needed):
            if name not in defs:
                raise ValueError(f"$ref to unknown definition {name!r}")
            needed.add(name)
            pending.append(defs[name])
    if needed:
        out["$defs"] = {name: copy.deepcopy(defs[name]) for name in sorted(needed)}
    return out


def compile_tools(module_path: Path, include_path: tuple[Path, ...], profile: str) -> dict[str, Any]:
    module = YangParser(expand_uses=False, include_path=include_path).parse_file(module_path)
    schema = generate_json_schema(module)
    rpcs: dict[str, Any] = schema.get(XYANG, {}).get("rpcs", {})
    defs: dict[str, Any] = schema.get("$defs", {})
    descriptions = {
        s.name: s.description
        for s in module.statements
        if type(s).__name__ == "YangRpcStmt"
    }

    tools = []
    for name, rpc in rpcs.items():
        tool: dict[str, Any] = {"name": name}
        if descriptions.get(name):
            tool["description"] = " ".join(descriptions[name].split())
        tool["inputSchema"] = _self_contained(rpc.get("input") or {"properties": {}}, defs)
        if rpc.get("output"):
            tool["outputSchema"] = _self_contained(rpc["output"], defs)
        tools.append(tool)

    result: dict[str, Any] = {"tools": tools}
    if profile == "standard":
        result = _strip_xyang(result)
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("module", type=Path)
    ap.add_argument("--include-path", type=Path, action="append", default=[])
    ap.add_argument("--profile", choices=("standard", "xyang"), default="standard")
    ap.add_argument("-o", "--output", type=Path)
    args = ap.parse_args(argv)

    result = compile_tools(args.module, tuple(args.include_path), args.profile)
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
        print(f"Wrote {args.output} ({len(result['tools'])} tools, profile {args.profile})")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
