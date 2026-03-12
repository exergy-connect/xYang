"""
Parser that builds a YANG AST (xyang.ast / YangModule) from a JSON Schema file
with x-yang annotations (e.g. meta-model.json).

Reuses existing AST nodes: YangModule, YangContainerStmt, YangListStmt,
YangLeafStmt, YangLeafListStmt, YangTypedefStmt, YangTypeStmt, YangMustStmt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..module import YangModule
from ..ast import (
    YangCaseStmt,
    YangChoiceStmt,
    YangContainerStmt,
    YangListStmt,
    YangLeafStmt,
    YangLeafListStmt,
    YangTypedefStmt,
    YangTypeStmt,
    YangMustStmt,
    YangWhenStmt,
)
from ..xpath import XPathParser


def _get_xyang(schema: dict[str, Any]) -> dict[str, Any]:
    """Extract x-yang object from a schema node (property or $def)."""
    return schema.get("x-yang") or {}


def _when_from_xyang(xyang: dict[str, Any]) -> YangWhenStmt | None:
    """Build YangWhenStmt from x-yang 'when' condition string, or None if absent."""
    when_str = xyang.get("when")
    if not when_str or not isinstance(when_str, str):
        return None
    try:
        ast = XPathParser(when_str).parse()
    except Exception:
        ast = None
    return YangWhenStmt(condition=when_str, ast=ast)


def _ref_to_typedef_name(ref: str) -> str | None:
    """Return typedef name from $ref like '#/$defs/entity-name' or None."""
    if not ref or not ref.startswith("#/$defs/"):
        return None
    return ref.replace("#/$defs/", "", 1)


def _resolve_schema(schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """Resolve $ref and allOf to a single schema with merged properties (for list items / groupings)."""
    if not schema or not isinstance(schema, dict):
        return {}
    if "$ref" in schema and len(schema) <= 2:
        name = _ref_to_typedef_name(schema["$ref"])
        if name and name in defs:
            return _resolve_schema(defs[name], defs)
    if "allOf" in schema:
        merged: dict[str, Any] = {"properties": {}}
        for part in schema.get("allOf") or []:
            if isinstance(part, dict):
                resolved = _resolve_schema(part, defs)
                merged["properties"] = {**merged.get("properties", {}), **resolved.get("properties", {})}
                for k, v in resolved.items():
                    if k != "properties":
                        merged[k] = v
        return merged
    return schema


def _type_from_schema(defs: dict[str, Any], schema: dict[str, Any], xyang: dict[str, Any]) -> YangTypeStmt | None:
    """Build YangTypeStmt from JSON schema (+ $ref) and x-yang (e.g. leafref)."""
    # Leafref from x-yang
    if xyang.get("type") == "leafref":
        path = xyang.get("path", "") or ""
        require = xyang.get("require-instance", True)
        type_stmt = YangTypeStmt(name="leafref", path=None, require_instance=bool(require))
        if path:
            type_stmt.path = path  # str for JSON; normalizer accepts str for comparison
        return type_stmt
    # $ref to typedef: preserve typedef name; copy range so AST matches YANG (pattern left None so validator resolves typedef)
    ref = schema.get("$ref")
    if ref:
        name = _ref_to_typedef_name(ref)
        if name and name in defs:
            def_schema = defs[name]
            if isinstance(def_schema, dict):
                resolved = _type_from_schema(defs, def_schema, _get_xyang(def_schema))
                if resolved is not None:
                    out = YangTypeStmt(name=name)
                    if getattr(resolved, "range", None):
                        out.range = resolved.range
                    return out
            return YangTypeStmt(name=name)
        if name:
            return YangTypeStmt(name=name)
    # Inline type
    t = schema.get("type")
    if "enum" in schema:
        enums = list(schema["enum"]) if isinstance(schema["enum"], list) else []
        if len(enums) > 1:
            type_stmt = YangTypeStmt(name="enumeration")
            type_stmt.enums = enums
            return type_stmt
        if len(enums) == 1 and t == "string" and isinstance(enums[0], str):
            type_stmt = YangTypeStmt(name="string")
            type_stmt.pattern = "\\*" if enums[0] == "*" else enums[0]
            return type_stmt
    if t == "string":
        type_stmt = YangTypeStmt(name="string")
        if "pattern" in schema:
            p = schema["pattern"]
            if isinstance(p, str) and p.startswith("^") and p.endswith("$"):
                p = p[1:-1]
            type_stmt.pattern = p
        min_len = schema.get("minLength")
        max_len = schema.get("maxLength")
        if min_len is not None and max_len is not None:
            type_stmt.length = f"{min_len}..{max_len}"
        elif max_len is not None:
            type_stmt.length = f"0..{max_len}"
        elif min_len is not None:
            type_stmt.length = f"{min_len}.."
        return type_stmt
    if t == "integer":
        min_val = schema.get("minimum")
        max_val = schema.get("maximum")
        if min_val == 0 and max_val == 255:
            type_stmt = YangTypeStmt(name="uint8")
            type_stmt.range = "0..255"
        else:
            type_stmt = YangTypeStmt(name="int32")
            if min_val is not None and max_val is not None:
                type_stmt.range = f"{min_val}..{max_val}"
            elif max_val is not None:
                type_stmt.range = f"0..{max_val}"
            elif min_val is not None:
                type_stmt.range = f"{min_val}..max"
        return type_stmt
    if t == "number":
        return YangTypeStmt(name="decimal64")
    if t == "boolean":
        return YangTypeStmt(name="boolean")
    if t == "object" and schema.get("maxProperties") == 0:
        return YangTypeStmt(name="empty")
    if "oneOf" in schema:
        union_types = []
        for branch in schema.get("oneOf") or []:
            if isinstance(branch, dict):
                branch_xyang = branch.get("x-yang") or {}
                bt = _type_from_schema(defs, branch, branch_xyang)
                if bt:
                    union_types.append(bt)
        if union_types:
            return YangTypeStmt(name="union", types=union_types)
    return None


def _build_typedef(def_name: str, def_schema: dict[str, Any], defs: dict[str, Any]) -> YangTypedefStmt | None:
    """Build YangTypedefStmt from a $defs entry with x-yang type typedef."""
    xyang = _get_xyang(def_schema)
    if xyang.get("type") != "typedef":
        return None
    desc = def_schema.get("description", "")
    type_stmt = _type_from_schema(defs, def_schema, xyang)
    if type_stmt is None:
        type_stmt = YangTypeStmt(name="string")
    stmt = YangTypedefStmt(name=def_name, description=desc, type=type_stmt)
    return stmt


def _build_must_list(xyang: dict[str, Any]) -> list[YangMustStmt]:
    """Build list of YangMustStmt from x-yang must (list of {must, error-message, description})."""
    out = []
    for m in xyang.get("must") or []:
        if isinstance(m, dict):
            out.append(
                YangMustStmt(
                    expression=m.get("must", ""),
                    error_message=m.get("error-message", ""),
                    description=m.get("description", ""),
                )
            )
    return out


def _property_schema_and_xyang(prop_value: dict[str, Any], defs: dict[str, Any]) -> tuple[dict, dict]:
    """Resolve property value (maybe with $ref + allOf) to one schema and merged x-yang."""
    if "$ref" in prop_value and "x-yang" in prop_value:
        ref_name = _ref_to_typedef_name(prop_value["$ref"])
        base = defs.get(ref_name, {}) if ref_name else {}
        # Merge: base schema + prop_value overrides; x-yang from base merged with prop_value (so must, etc. from def are kept)
        schema = {**base, **{k: v for k, v in prop_value.items() if k != "x-yang"}}
        base_xyang = base.get("x-yang") or {}
        prop_xyang = prop_value.get("x-yang") or {}
        merged_xyang = {**base_xyang, **prop_xyang}
        return schema, merged_xyang
    if "allOf" in prop_value:
        merged = {}
        xyang = {}
        for part in prop_value["allOf"]:
            if isinstance(part, dict):
                if "$ref" in part:
                    name = _ref_to_typedef_name(part["$ref"])
                    if name:
                        merged.update(defs.get(name, {}))
                else:
                    merged.update(part)
                xyang.update(part.get("x-yang") or {})
        return merged, xyang
    return prop_value, _get_xyang(prop_value)


def _convert_container(
    name: str,
    schema: dict[str, Any],
    xyang: dict[str, Any],
    defs: dict[str, Any],
    parent_path: str,
    must_list: list[YangMustStmt],
) -> YangContainerStmt:
    """Convert a container property to YangContainerStmt."""
    description = schema.get("description", "")
    child_statements = []
    container_required = set(schema.get("required") or [])
    for child_name, child_val in (schema.get("properties") or {}).items():
        child = _convert_property(
            child_name,
            child_val,
            defs,
            f"{parent_path}/{child_name}",
            mandatory_override=child_name in container_required,
        )
        if child is not None:
            child_statements.append(child)
    c = YangContainerStmt(name=name, description=description, statements=child_statements)
    c.must_statements = must_list
    when_stmt = _when_from_xyang(xyang)
    if when_stmt is not None:
        c.when = when_stmt
    return c


def _convert_list(
    name: str,
    schema: dict[str, Any],
    xyang: dict[str, Any],
    defs: dict[str, Any],
    parent_path: str,
    must_list: list[YangMustStmt],
) -> YangListStmt:
    """Convert a list property to YangListStmt."""
    description = schema.get("description", "")
    key = xyang.get("key")
    items = _resolve_schema(schema.get("items") or {}, defs)
    child_statements = []
    item_required = set(items.get("required") or [])
    item_props = items.get("properties") or {}
    for child_name, child_val in item_props.items():
        child = _convert_property(
            child_name,
            child_val,
            defs,
            f"{parent_path}/{name}/{child_name}",
            mandatory_override=child_name in item_required,
        )
        if child is not None:
            child_statements.append(child)
    lst = YangListStmt(name=name, description=description, key=key, statements=child_statements)
    lst.must_statements = must_list
    when_stmt = _when_from_xyang(xyang)
    if when_stmt is not None:
        lst.when = when_stmt
    return lst


def _convert_leaf(
    name: str,
    schema: dict[str, Any],
    xyang: dict[str, Any],
    prop_value: dict[str, Any],
    defs: dict[str, Any],
    mandatory_override: bool | None,
    must_list: list[YangMustStmt],
) -> YangLeafStmt:
    """Convert a leaf property to YangLeafStmt."""
    description = schema.get("description", "")
    type_schema = schema
    if "$ref" in prop_value:
        ref_name = _ref_to_typedef_name(prop_value["$ref"])
        if ref_name and ref_name in defs and _get_xyang(defs[ref_name]).get("type") == "typedef":
            type_schema = prop_value
    type_stmt = _type_from_schema(defs, type_schema, xyang)
    if type_stmt is None:
        type_stmt = YangTypeStmt(name="string")
    mandatory = mandatory_override if mandatory_override is not None else (name in (schema.get("required") or []))
    default = schema.get("default")
    if default is not None and schema.get("type") != "boolean":
        default = str(default).lower() if isinstance(default, bool) else str(default)
    leaf = YangLeafStmt(
        name=name,
        description=description,
        type=type_stmt,
        mandatory=mandatory,
        default=default,
    )
    leaf.must_statements = must_list
    when_stmt = _when_from_xyang(xyang)
    if when_stmt is not None:
        leaf.when = when_stmt
    return leaf


def _convert_leaf_list(
    name: str,
    schema: dict[str, Any],
    xyang: dict[str, Any],
    defs: dict[str, Any],
    must_list: list[YangMustStmt],
) -> YangLeafListStmt:
    """Convert a leaf-list property to YangLeafListStmt."""
    description = schema.get("description", "")
    items_schema = schema.get("items") or schema
    items_xyang = (items_schema.get("x-yang") or {}) if isinstance(items_schema, dict) else {}
    type_stmt = _type_from_schema(defs, items_schema, items_xyang or xyang)
    if type_stmt is None:
        type_stmt = YangTypeStmt(name="string")
    ll = YangLeafListStmt(name=name, description=description, type=type_stmt)
    ll.must_statements = must_list
    when_stmt = _when_from_xyang(xyang)
    if when_stmt is not None:
        ll.when = when_stmt
    return ll


def _convert_choice(
    name: str,
    schema: dict[str, Any],
    xyang: dict[str, Any],
    defs: dict[str, Any],
    parent_path: str,
) -> YangChoiceStmt:
    """Convert a JSON schema property with x-yang type 'choice' to YangChoiceStmt. Uses oneOf (valid JSON Schema)."""
    description = schema.get("description", "")
    mandatory = xyang.get("mandatory", False)
    one_of = schema.get("oneOf") or []
    cases: list[YangCaseStmt] = []
    for case_schema in one_of:
        if not isinstance(case_schema, dict):
            continue
        case_xyang = _get_xyang(case_schema)
        case_name = case_xyang.get("name") or ""
        if not case_name and case_schema.get("required"):
            req = case_schema["required"]
            case_name = req[0] + "-case" if (isinstance(req, list) and len(req) == 1) else ""
        if not case_name:
            case_props = case_schema.get("properties") or {}
            keys = list(case_props.keys())
            case_name = keys[0] + "-case" if len(keys) == 1 else ""
        case_props = case_schema.get("properties") or {}
        case_statements: list[YangContainerStmt | YangListStmt | YangLeafStmt | YangLeafListStmt] = []
        for prop_name, prop_val in case_props.items():
            stmt = _convert_property(
                prop_name,
                prop_val,
                defs,
                f"{parent_path}/{name}/{case_name}/{prop_name}",
                mandatory_override=None,
            )
            if stmt is not None:
                case_statements.append(stmt)
        cases.append(YangCaseStmt(name=case_name, description="", statements=case_statements))
    return YangChoiceStmt(name=name, description=description, mandatory=mandatory, cases=cases)


def _convert_property(
    name: str,
    prop_value: dict[str, Any],
    defs: dict[str, Any],
    parent_path: str,
    mandatory_override: bool | None = None,
) -> YangContainerStmt | YangListStmt | YangLeafStmt | YangLeafListStmt | YangChoiceStmt | None:
    """Convert one JSON schema property to a YANG AST statement. Returns None if not x-yang mapped."""
    schema, xyang = _property_schema_and_xyang(prop_value, defs)
    node_type = xyang.get("type")
    if node_type == "leafref":
        node_type = "leaf"
    must_list = _build_must_list(xyang) if node_type in ("leaf", "leaf-list", "container", "list") else []

    if node_type == "container":
        return _convert_container(name, schema, xyang, defs, parent_path, must_list)
    if node_type == "list":
        return _convert_list(name, schema, xyang, defs, parent_path, must_list)
    if node_type == "leaf":
        return _convert_leaf(name, schema, xyang, prop_value, defs, mandatory_override, must_list)
    if node_type == "leaf-list":
        return _convert_leaf_list(name, schema, xyang, defs, must_list)
    if node_type == "choice":
        return _convert_choice(name, schema, xyang, defs, parent_path)
    return None


def parse_json_schema(source: str | Path | dict[str, Any]) -> YangModule:
    """
    Build a YangModule (and nested AST nodes from xyang.ast) from a JSON Schema
    with x-yang annotations.

    Args:
        source: Path to a .json file, or JSON string, or parsed dict.

    Returns:
        YangModule with .statements (e.g. data-model container), .typedefs.
    """
    if isinstance(source, dict):
        data = source
    elif isinstance(source, (str, Path)):
        path = Path(source)
        if path.suffix == ".json" and path.exists():
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        elif isinstance(source, str):
            data = json.loads(source)
        else:
            raise FileNotFoundError(f"Not a JSON file or JSON string: {source}")
    else:
        raise TypeError("source must be path, JSON string, or dict")

    root_xyang = data.get("x-yang") or {}
    defs = data.get("$defs") or {}

    module = YangModule(
        name=root_xyang.get("module", "unknown"),
        yang_version=root_xyang.get("yang-version", "1.1"),
        namespace=root_xyang.get("namespace", ""),
        prefix=root_xyang.get("prefix", ""),
        organization=root_xyang.get("organization", ""),
        contact=root_xyang.get("contact", ""),
        description=data.get("description", ""),
    )

    for def_name, def_schema in defs.items():
        if not isinstance(def_schema, dict):
            continue
        td = _build_typedef(def_name, def_schema, defs)
        if td is not None:
            module.typedefs[def_name] = td

    root_props = (data.get("properties") or {})
    if "data-model" in root_props:
        dm = root_props["data-model"]
        if isinstance(dm, dict):
            dm_props = dm.get("properties") or {}
            statements = []
            for prop_name, prop_val in dm_props.items():
                stmt = _convert_property(prop_name, prop_val, defs, f"/data-model/{prop_name}")
                if stmt is not None:
                    statements.append(stmt)
            container = YangContainerStmt(
                name="data-model",
                description=(dm.get("description") or ""),
                statements=statements,
            )
            module.statements.append(container)

    return module
