"""
Test that parsing meta-model from JSON and from YANG produces identical ASTs.

Loads examples/meta-model.json (via xyang.json.parse_json_schema) and
examples/meta-model.yang (via parse_yang_file), then normalizes both to a
comparable structure and asserts equality.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from xyang import parse_yang_file
from xyang.json import parse_json_schema


_EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
META_MODEL_JSON = _EXAMPLES_DIR / "meta-model.json"
META_MODEL_YANG = _EXAMPLES_DIR / "meta-model.yang"


def _normalize_type(type_stmt: Any) -> dict[str, Any] | None:
    """Normalize a YangTypeStmt to a comparable dict (no PathNode, no AST)."""
    if type_stmt is None:
        return None
    out = {
        "name": type_stmt.name,
        "pattern": getattr(type_stmt, "pattern", None),
        "length": getattr(type_stmt, "length", None),
        "range": getattr(type_stmt, "range", None),
        "enums": sorted(getattr(type_stmt, "enums", []) or []),
        "require_instance": getattr(type_stmt, "require_instance", True),
    }
    # Leafref path: use string (PathNode.to_string() or raw str from JSON parser)
    path = getattr(type_stmt, "path", None)
    if path is not None and hasattr(path, "to_string"):
        out["path"] = path.to_string()
    elif isinstance(path, str) and path:
        out["path"] = path
    else:
        out["path"] = None
    types = getattr(type_stmt, "types", None) or []
    if types:
        out["types"] = [_normalize_type(t) for t in types]
    else:
        out["types"] = []
    return out


def _normalize_typedef(td: Any) -> dict[str, Any]:
    """Normalize a YangTypedefStmt to a comparable dict."""
    type_sig = _normalize_type(getattr(td, "type", None))
    return {"name": td.name, "type": type_sig}


def _normalize_statement(stmt: Any) -> dict[str, Any] | None:
    """Normalize a YANG statement to a comparable dict. Returns None for non-data nodes we skip."""
    from xyang.ast import (
        YangContainerStmt,
        YangListStmt,
        YangLeafStmt,
        YangLeafListStmt,
        YangUsesStmt,
        YangRefineStmt,
    )
    if stmt is None:
        return None
    kind = type(stmt).__name__
    name = getattr(stmt, "name", "")
    desc = getattr(stmt, "description", "") or ""
    out = {"kind": kind, "name": name, "description": desc}

    if isinstance(stmt, YangContainerStmt):
        out["children"] = []
        for c in getattr(stmt, "statements", []) or []:
            n = _normalize_statement(c)
            if n is not None:
                out["children"].append(n)
        out["children"].sort(key=lambda x: x["name"])
        out["must"] = [m.expression for m in (getattr(stmt, "must_statements", None) or [])]
        return out

    if isinstance(stmt, YangListStmt):
        out["key"] = getattr(stmt, "key", None)
        out["children"] = []
        for c in getattr(stmt, "statements", []) or []:
            if isinstance(c, (YangUsesStmt, YangRefineStmt)):
                out.setdefault("uses_refines", []).append(
                    {"kind": type(c).__name__, "grouping_name": getattr(c, "grouping_name", ""), "target_path": getattr(c, "target_path", "")}
                )
                continue
            n = _normalize_statement(c)
            if n is not None:
                out["children"].append(n)
        out["children"].sort(key=lambda x: x["name"])
        out["must"] = [m.expression for m in (getattr(stmt, "must_statements", None) or [])]
        return out

    if isinstance(stmt, YangLeafStmt):
        out["type"] = _normalize_type(getattr(stmt, "type", None))
        out["mandatory"] = getattr(stmt, "mandatory", False)
        out["default"] = getattr(stmt, "default", None)
        out["must"] = [m.expression for m in (getattr(stmt, "must_statements", None) or [])]
        return out

    if isinstance(stmt, YangLeafListStmt):
        out["type"] = _normalize_type(getattr(stmt, "type", None))
        out["must"] = [m.expression for m in (getattr(stmt, "must_statements", None) or [])]
        return out

    return None


def normalize_module(module: Any) -> dict[str, Any]:
    """Produce a comparable dict from a YangModule for equality assertion."""
    out = {
        "name": module.name,
        "namespace": module.namespace,
        "prefix": module.prefix,
        "yang_version": getattr(module, "yang_version", "1.1"),
        "typedefs": {},
        "statements": [],
    }
    for name, td in (getattr(module, "typedefs", None) or {}).items():
        out["typedefs"][name] = _normalize_typedef(td)
    for stmt in getattr(module, "statements", []) or []:
        n = _normalize_statement(stmt)
        if n is not None:
            out["statements"].append(n)
    out["statements"].sort(key=lambda x: x["name"])
    return out


def test_meta_model_json_and_yang_produce_identical_ast():
    """Load both meta-model examples and assert the produced ASTs are identical."""
    assert META_MODEL_JSON.exists(), f"Missing {META_MODEL_JSON}"
    assert META_MODEL_YANG.exists(), f"Missing {META_MODEL_YANG}"

    json_module = parse_json_schema(META_MODEL_JSON)
    yang_module = parse_yang_file(str(META_MODEL_YANG))

    norm_json = normalize_module(json_module)
    norm_yang = normalize_module(yang_module)

    # Compare module header
    assert norm_json["name"] == norm_yang["name"], "module name"
    assert norm_json["namespace"] == norm_yang["namespace"], "namespace"
    assert norm_json["prefix"] == norm_yang["prefix"], "prefix"
    assert norm_json["yang_version"] == norm_yang["yang_version"], "yang_version"

    # Compare typedefs: every typedef present in both must have identical type signature.
    # (JSON may have fewer $defs than YANG has typedefs; YANG may have extra typedefs.)
    common_typedefs = set(norm_json["typedefs"]) & set(norm_yang["typedefs"])
    for name in common_typedefs:
        j = norm_json["typedefs"][name]
        y = norm_yang["typedefs"][name]
        assert j == y, f"typedef {name}: json {j} != yang {y}"

    # Compare top-level statements (e.g. data-model container and its tree)
    assert len(norm_json["statements"]) == len(norm_yang["statements"]), (
        f"statement count: json {len(norm_json['statements'])} vs yang {len(norm_yang['statements'])}"
    )
    for js, ys in zip(norm_json["statements"], norm_yang["statements"]):
        assert js == ys, f"statement {js.get('name')}: json != yang.\njson: {js}\nyang: {ys}"
