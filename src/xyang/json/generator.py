"""
Generate a JSON Schema file (schema.yang.json) from a YANG AST (YangModule).

Produces JSON Schema with x-yang annotations compatible with the json/parser
so that parse_json_schema(generate_json_schema(module)) round-trips where supported.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..ast import (
    YangCaseStmt,
    YangChoiceStmt,
    YangContainerStmt,
    YangLeafListStmt,
    YangLeafStmt,
    YangListStmt,
    YangMustStmt,
    YangRefineStmt,
    YangStatement,
    YangTypeStmt,
    YangTypedefStmt,
    YangUsesStmt,
)
from ..module import YangModule


def _leafref_path_string(path: Any) -> str:
    """Return leafref path as string (PathNode.to_string() or raw str)."""
    if path is None:
        return ""
    if hasattr(path, "to_string") and callable(path.to_string):
        return path.to_string()
    return str(path)


def _type_to_schema(
    type_stmt: YangTypeStmt | None,
    typedef_names: set[str],
) -> dict[str, Any]:
    """Build JSON Schema for a type. Uses $ref for typedef names when in typedef_names."""
    if type_stmt is None:
        return {"type": "string"}

    name = type_stmt.name
    if name in typedef_names:
        return {"$ref": f"#/$defs/{name}"}

    if name == "leafref":
        path = _leafref_path_string(type_stmt.path)
        require = getattr(type_stmt, "require_instance", True)
        return {
            "type": "string",
            "x-yang": {
                "type": "leafref",
                "path": path,
                "require-instance": require,
            },
        }
    if name == "string":
        out: dict[str, Any] = {"type": "string"}
        if type_stmt.pattern:
            p = type_stmt.pattern
            if not (p.startswith("^") and p.endswith("$")):
                p = f"^{p}$"
            # Use pattern as-is; json.dumps will escape backslashes for JSON
            out["pattern"] = p
        if type_stmt.length:
            parts = type_stmt.length.split("..")
            min_len = None
            max_len = None
            if len(parts) >= 1 and parts[0].strip():
                try:
                    min_len = int(parts[0].strip())
                except ValueError:
                    pass
            if len(parts) >= 2 and parts[1].strip() and parts[1].strip().lower() != "max":
                try:
                    max_len = int(parts[1].strip())
                except ValueError:
                    pass
            if min_len is not None:
                out["minLength"] = min_len
            if max_len is not None:
                out["maxLength"] = max_len
        return out
    if name == "enumeration" and type_stmt.enums:
        return {"type": "string", "enum": list(type_stmt.enums)}
    if name == "boolean":
        return {"type": "boolean"}
    if name in ("int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64"):
        out = {"type": "integer"}
        if name == "uint8":
            out["minimum"] = 0
            out["maximum"] = 255
        elif type_stmt.range:
            parts = type_stmt.range.split("..")
            if len(parts) >= 1 and parts[0].strip():
                try:
                    out["minimum"] = int(parts[0].strip())
                except ValueError:
                    pass
            if len(parts) >= 2 and parts[1].strip().lower() != "max":
                try:
                    out["maximum"] = int(parts[1].strip())
                except ValueError:
                    pass
        return out
    if name == "decimal64":
        out = {"type": "number"}
        if type_stmt.fraction_digits is not None:
            out["x-fraction-digits"] = type_stmt.fraction_digits
        return out
    if name == "empty":
        return {"type": "object", "maxProperties": 0}
    if name == "union" and type_stmt.types:
        return {
            "oneOf": [_type_to_schema(t, typedef_names) for t in type_stmt.types],
        }
    # Default: string
    return {"type": "string"}


def _must_to_json(must: YangMustStmt) -> dict[str, Any]:
    """Convert YangMustStmt to x-yang must entry."""
    return {
        "must": must.expression,
        "error-message": must.error_message or "",
        "description": must.description or "",
    }


def _build_xyang(
    node_type: str,
    key: str | None = None,
    must_list: list[YangMustStmt] | None = None,
    when_condition: str | None = None,
) -> dict[str, Any]:
    """Build x-yang object for a node."""
    xyang: dict[str, Any] = {"type": node_type}
    if key:
        xyang["key"] = key
    if must_list:
        xyang["must"] = [_must_to_json(m) for m in must_list]
    if when_condition:
        xyang["when"] = when_condition
    return xyang


def _copy_statement(stmt: YangStatement) -> YangStatement:
    """Shallow-copy a statement for use when expanding uses (so refines don't mutate grouping)."""
    if isinstance(stmt, YangContainerStmt):
        return YangContainerStmt(
            name=stmt.name,
            description=stmt.description,
            statements=[_copy_statement(s) for s in stmt.statements],
            presence=getattr(stmt, "presence", None),
            when=getattr(stmt, "when", None),
            must_statements=list(getattr(stmt, "must_statements", None) or []),
        )
    if isinstance(stmt, YangListStmt):
        return YangListStmt(
            name=stmt.name,
            description=stmt.description,
            statements=[_copy_statement(s) for s in stmt.statements],
            key=stmt.key,
            min_elements=getattr(stmt, "min_elements", None),
            max_elements=getattr(stmt, "max_elements", None),
            when=getattr(stmt, "when", None),
            must_statements=list(getattr(stmt, "must_statements", None) or []),
        )
    if isinstance(stmt, YangLeafStmt):
        return YangLeafStmt(
            name=stmt.name,
            description=stmt.description,
            statements=[],
            type=stmt.type,
            mandatory=stmt.mandatory,
            default=stmt.default,
            when=getattr(stmt, "when", None),
            must_statements=list(getattr(stmt, "must_statements", None) or []),
        )
    if isinstance(stmt, YangLeafListStmt):
        return YangLeafListStmt(
            name=stmt.name,
            description=stmt.description,
            statements=[],
            type=stmt.type,
            min_elements=getattr(stmt, "min_elements", None),
            max_elements=getattr(stmt, "max_elements", None),
            when=getattr(stmt, "when", None),
            must_statements=list(getattr(stmt, "must_statements", None) or []),
        )
    # Fallback: same reference (refines may mutate; avoid if possible)
    return stmt


def _apply_refine(stmt: YangStatement, refine: YangRefineStmt) -> None:
    """Apply refine modifications to a statement copy."""
    if getattr(refine, "type", None) is not None and isinstance(stmt, YangLeafStmt):
        stmt.type = refine.type
    for refine_must in refine.must_statements:
        must_list = getattr(stmt, "must_statements", None)
        if must_list is None:
            setattr(stmt, "must_statements", [])
            must_list = getattr(stmt, "must_statements")
        must_list.append(refine_must)


def _expand_uses_in_statements(
    statements: list[YangStatement],
    module: YangModule,
) -> list[YangStatement]:
    """Expand uses statements in place: resolve groupings and apply refines. Returns a flat list of statements."""
    expanded: list[YangStatement] = []
    for stmt in statements:
        if isinstance(stmt, YangUsesStmt):
            grouping = module.get_grouping(stmt.grouping_name)
            if grouping:
                nested = _expand_uses_in_statements(grouping.statements, module)
                for s in nested:
                    s_copy = _copy_statement(s)
                    for refine in stmt.refines:
                        if refine.target_path == s.name:
                            _apply_refine(s_copy, refine)
                    expanded.append(s_copy)
        elif hasattr(stmt, "statements"):
            stmt_copy = _copy_statement(stmt)
            stmt_copy.statements = _expand_uses_in_statements(stmt.statements, module)
            expanded.append(stmt_copy)
        else:
            expanded.append(stmt)
    return expanded


def _statement_to_property(
    stmt: YangStatement,
    typedef_names: set[str],
    module: YangModule,
) -> dict[str, Any] | None:
    """Convert an AST statement to a JSON Schema property. Returns None for unsupported nodes. Expands uses when present."""
    from ..ast import YangContainerStmt, YangLeafListStmt, YangLeafStmt, YangListStmt

    if isinstance(stmt, YangContainerStmt):
        children = _expand_uses_in_statements(stmt.statements, module)
        props: dict[str, Any] = {}
        required: list[str] = []
        for child in children:
            child_prop = _statement_to_property(child, typedef_names, module)
            if child_prop is not None:
                props[child.name] = child_prop
                if isinstance(child, YangLeafStmt) and child.mandatory:
                    required.append(child.name)
        when_cond = None
        if getattr(stmt, "when", None) is not None:
            when_cond = getattr(stmt.when, "condition", None)
        out = {
            "type": "object",
            "description": stmt.description or "",
            "x-yang": _build_xyang(
                "container",
                must_list=getattr(stmt, "must_statements", None) or [],
                when_condition=when_cond,
            ),
        }
        if props:
            out["properties"] = props
        if required:
            out["required"] = required
        out["additionalProperties"] = False
        return out

    if isinstance(stmt, YangListStmt):
        list_children = _expand_uses_in_statements(stmt.statements, module)
        items: dict[str, Any] = {"type": "object", "properties": {}}
        item_required: list[str] = []
        for child in list_children:
            child_prop = _statement_to_property(child, typedef_names, module)
            if child_prop is not None:
                items["properties"][child.name] = child_prop
                if isinstance(child, YangLeafStmt) and child.mandatory:
                    item_required.append(child.name)
        if item_required:
            items["required"] = item_required
        items["additionalProperties"] = False
        when_cond = None
        if getattr(stmt, "when", None) is not None:
            when_cond = getattr(stmt.when, "condition", None)
        out = {
            "type": "array",
            "items": items,
            "description": stmt.description or "",
            "x-yang": _build_xyang(
                "list",
                key=stmt.key,
                must_list=getattr(stmt, "must_statements", None) or [],
                when_condition=when_cond,
            ),
        }
        if getattr(stmt, "min_elements", None) is not None and stmt.min_elements is not None:
            out["minItems"] = stmt.min_elements
        if getattr(stmt, "max_elements", None) is not None and stmt.max_elements is not None:
            out["maxItems"] = stmt.max_elements
        return out

    if isinstance(stmt, YangLeafStmt):
        type_stmt = stmt.type
        when_cond = None
        if getattr(stmt, "when", None) is not None:
            when_cond = getattr(stmt.when, "condition", None)
        if type_stmt and type_stmt.name in typedef_names:
            out = {
                "$ref": f"#/$defs/{type_stmt.name}",
                "description": stmt.description or "",
                "x-yang": _build_xyang(
                    "leaf",
                    must_list=getattr(stmt, "must_statements", None) or [],
                    when_condition=when_cond,
                ),
            }
        else:
            out = {
                **_type_to_schema(type_stmt, typedef_names),
                "description": stmt.description or "",
                "x-yang": _build_xyang(
                    "leaf",
                    must_list=getattr(stmt, "must_statements", None) or [],
                    when_condition=when_cond,
                ),
            }
        if stmt.default is not None:
            out["default"] = stmt.default
        return out

    if isinstance(stmt, YangLeafListStmt):
        type_stmt = stmt.type
        items_schema = _type_to_schema(type_stmt, typedef_names)
        when_cond = None
        if getattr(stmt, "when", None) is not None:
            when_cond = getattr(stmt.when, "condition", None)
        out = {
            "type": "array",
            "items": items_schema,
            "description": stmt.description or "",
            "x-yang": _build_xyang(
                "leaf-list",
                must_list=getattr(stmt, "must_statements", None) or [],
                when_condition=when_cond,
            ),
        }
        if getattr(stmt, "min_elements", None) is not None and stmt.min_elements is not None:
            out["minItems"] = stmt.min_elements
        if getattr(stmt, "max_elements", None) is not None and stmt.max_elements is not None:
            out["maxItems"] = stmt.max_elements
        return out

    if isinstance(stmt, YangChoiceStmt):
        one_of: list[dict[str, Any]] = []
        for case in getattr(stmt, "cases", []) or []:
            if not isinstance(case, YangCaseStmt):
                continue
            case_props: dict[str, Any] = {}
            for s in case.statements:
                child_prop = _statement_to_property(s, typedef_names, module)
                if child_prop is not None:
                    case_props[s.name] = child_prop
            entry: dict[str, Any] = {"properties": case_props}
            if case_props:
                entry["required"] = list(case_props.keys())
            one_of.append(entry)
        return {
            "type": "object",
            "description": stmt.description or "",
            "oneOf": one_of,
            "x-yang": {"type": "choice", "mandatory": getattr(stmt, "mandatory", False)},
        }

    return None


def _typedef_to_def(name: str, typedef: YangTypedefStmt) -> dict[str, Any]:
    """Convert YangTypedefStmt to a $defs entry."""
    type_stmt = typedef.type
    schema = _type_to_schema(type_stmt, set())  # no $ref inside typedef def
    schema["description"] = typedef.description or ""
    schema["x-yang"] = {"type": "typedef"}
    return schema


def generate_json_schema(module: YangModule) -> dict[str, Any]:
    """
    Build a JSON Schema dict from a YangModule AST.

    The output has the structure expected by parse_json_schema: root x-yang (module
    meta), properties (e.g. data-model container), and $defs (typedefs).
    """
    typedef_names = set(module.typedefs.keys())
    root_xyang: dict[str, Any] = {
        "module": module.name or "unknown",
        "yang-version": getattr(module, "yang_version", "1.1"),
        "namespace": module.namespace or "",
        "prefix": module.prefix or "",
        "organization": module.organization or "",
        "contact": module.contact or "",
    }
    properties: dict[str, Any] = {}
    for stmt in module.statements:
        if not getattr(stmt, "name", None):
            continue
        prop = _statement_to_property(stmt, typedef_names, module)
        if prop is not None:
            properties[stmt.name] = prop

    defs: dict[str, Any] = {}
    for name, typedef in module.typedefs.items():
        if isinstance(typedef, YangTypedefStmt):
            defs[name] = _typedef_to_def(name, typedef)

    root: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": module.namespace or f"urn:{module.name or 'unknown'}",
        "description": module.description or "",
        "x-yang": root_xyang,
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if defs:
        root["$defs"] = defs
    return root


def schema_to_yang_json(
    module: YangModule,
    output_path: str | Path | None = None,
    indent: int = 2,
) -> str:
    """
    Serialize YangModule to JSON Schema string (and optionally write to file).

    Args:
        module: YangModule AST.
        output_path: If set, write the JSON to this path (e.g. "schema.yang.json").
        indent: JSON indent (default 2).

    Returns:
        JSON string of the schema.
    """
    data = generate_json_schema(module)
    text = json.dumps(data, indent=indent, ensure_ascii=False)
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return text
