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
)
from ..module import YangModule
from ..refine_expand import copy_yang_statement
from ..uses_expand import expand_uses_in_statements
from ..xpath.ast import PathNode
from ..xpath.schema_nav import SchemaNav

from .schema_keys import JsonSchemaKey, XYangKey, XYangMustEntryKey, json_schema_defs_uri


def _leafref_path_string(path: Any) -> str:
    """Return leafref path as string (PathNode.to_string() or raw str)."""
    if path is None:
        return ""
    if isinstance(path, PathNode):
        return path.to_string()
    return str(path)


def _locate_stmt_with_parent(
    stmts: list[YangStatement],
    parent: YangStatement | YangModule,
    target: YangStatement,
) -> YangStatement | YangModule | None:
    """Return the immediate parent of target under stmts, or None if not found."""
    for s in stmts:
        if s is target:
            return parent
        if isinstance(s, YangChoiceStmt):
            for case in s.cases:
                if case is target:
                    return s
                found = _locate_stmt_with_parent(case.statements, case, target)
                if found is not None:
                    return found
        elif hasattr(s, "statements") and not isinstance(
            s, (YangLeafStmt, YangLeafListStmt)
        ):
            found = _locate_stmt_with_parent(s.statements, s, target)
            if found is not None:
                return found
    return None


def _schema_parent_of(
    module: YangModule,
    node: YangStatement | YangModule,
) -> YangStatement | YangModule | None:
    """Parent of node in the module tree, or None if node is the module root."""
    if node is module:
        return None
    return _locate_stmt_with_parent(module.statements, module, node)


def _leafref_context_parent(
    module: YangModule,
    immediate_parent: YangStatement | YangModule | None,
) -> YangStatement | YangModule | None:
    """Instance parent for leafref path resolution (choice/case lifted to enclosing node)."""
    if immediate_parent is None:
        return None
    if isinstance(immediate_parent, YangCaseStmt):
        choice = _schema_parent_of(module, immediate_parent)
        if choice is None:
            return None
        return _schema_parent_of(module, choice)
    return immediate_parent


def _resolve_leafref_target_leaf(
    module: YangModule | None,
    path_node: PathNode | None,
    leafref_anchor: YangStatement | YangModule | None,
) -> YangLeafStmt | None:
    """
    Resolve a leafref path to the target YangLeafStmt when the path is cacheable:
    no predicates, only identifier / . / .. steps.
    """
    if module is None or path_node is None or not path_node.segments:
        return None
    for seg in path_node.segments:
        if seg.predicate is not None:
            return None

    if path_node.is_absolute:
        current: YangStatement | YangModule = module
    else:
        if leafref_anchor is None:
            return None
        current = leafref_anchor

    for seg in path_node.segments:
        if seg.step == ".":
            continue
        if seg.step == "..":
            if current is module:
                return None
            parent = _schema_parent_of(module, current)
            if parent is None:
                return None
            current = parent
            continue
        stmts = getattr(current, "statements", [])
        nxt = SchemaNav._find(stmts, seg.step)
        if nxt is None:
            return None
        current = nxt

    return current if isinstance(current, YangLeafStmt) else None


def _type_to_schema(
    type_stmt: YangTypeStmt | None,
    typedef_names: set[str],
    module: YangModule | None = None,
    leafref_anchor: YangStatement | YangModule | None = None,
) -> dict[str, Any]:
    """Build JSON Schema for a type. Uses $ref for typedef names when in typedef_names."""
    if type_stmt is None:
        return {JsonSchemaKey.TYPE: "string"}

    name = type_stmt.name
    if name in typedef_names:
        return {JsonSchemaKey.REF: json_schema_defs_uri(name)}

    if name == "leafref":
        path_str = _leafref_path_string(type_stmt.path)
        require = getattr(type_stmt, "require_instance", True)
        path_node = type_stmt.path if isinstance(type_stmt.path, PathNode) else None
        target_leaf = _resolve_leafref_target_leaf(
            module, path_node, leafref_anchor
        )
        target_type = target_leaf.type if target_leaf and target_leaf.type else None
        if target_type is not None and module is not None:
            inner = _type_to_schema(
                target_type, typedef_names, module=module, leafref_anchor=None
            )
        else:
            inner = {JsonSchemaKey.TYPE: "string"}
        inner_clean = {k: v for k, v in inner.items() if k != JsonSchemaKey.X_YANG}
        return {
            **inner_clean,
            JsonSchemaKey.X_YANG: {
                XYangKey.TYPE: "leafref",
                XYangKey.PATH: path_str,
                XYangKey.REQUIRE_INSTANCE: require,
            },
        }
    out: dict[str, Any]
    if name == "string":
        out = {JsonSchemaKey.TYPE: "string"}
        if type_stmt.pattern:
            p = type_stmt.pattern
            if not (p.startswith("^") and p.endswith("$")):
                p = f"^{p}$"
            # Use pattern as-is; json.dumps will escape backslashes for JSON
            out[JsonSchemaKey.PATTERN] = p
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
                out[JsonSchemaKey.MIN_LENGTH] = min_len
            if max_len is not None:
                out[JsonSchemaKey.MAX_LENGTH] = max_len
        return out
    if name == "enumeration" and type_stmt.enums:
        return {JsonSchemaKey.TYPE: "string", JsonSchemaKey.ENUM: list(type_stmt.enums)}
    if name == "boolean":
        return {JsonSchemaKey.TYPE: "boolean"}
    if name in ("int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64"):
        out = {JsonSchemaKey.TYPE: "integer"}
        if name == "uint8":
            out[JsonSchemaKey.MINIMUM] = 0
            out[JsonSchemaKey.MAXIMUM] = 255
        elif type_stmt.range:
            parts = type_stmt.range.split("..")
            if len(parts) >= 1 and parts[0].strip():
                try:
                    out[JsonSchemaKey.MINIMUM] = int(parts[0].strip())
                except ValueError:
                    pass
            if len(parts) >= 2 and parts[1].strip().lower() != "max":
                try:
                    out[JsonSchemaKey.MAXIMUM] = int(parts[1].strip())
                except ValueError:
                    pass
        return out
    if name == "decimal64":
        out = {JsonSchemaKey.TYPE: "number"}
        if type_stmt.fraction_digits is not None:
            fd = int(type_stmt.fraction_digits)
            if fd > 0:
                out[JsonSchemaKey.MULTIPLE_OF] = 10**-fd
        return out
    if name == "empty":
        return {JsonSchemaKey.TYPE: "object", JsonSchemaKey.MAX_PROPERTIES: 0}
    if name == "union" and type_stmt.types:
        return {
            JsonSchemaKey.ONE_OF: [
                _type_to_schema(
                    t,
                    typedef_names,
                    module=module,
                    leafref_anchor=leafref_anchor,
                )
                for t in type_stmt.types
            ],
        }
    # Default: string
    return {JsonSchemaKey.TYPE: "string"}


def _must_to_json(must: YangMustStmt) -> dict[str, Any]:
    """Convert YangMustStmt to x-yang must entry."""
    return {
        XYangMustEntryKey.MUST: must.expression,
        XYangMustEntryKey.ERROR_MESSAGE: must.error_message or "",
        JsonSchemaKey.DESCRIPTION: must.description or "",
    }


def _build_xyang(
    node_type: str,
    key: str | None = None,
    must_list: list[YangMustStmt] | None = None,
    when_condition: str | None = None,
    presence: str | None = None,
) -> dict[str, Any]:
    """Build x-yang object for a node."""
    xyang: dict[str, Any] = {XYangKey.TYPE: node_type}
    if key:
        xyang[XYangKey.KEY] = key
    if must_list:
        xyang[XYangKey.MUST] = [_must_to_json(m) for m in must_list]
    if when_condition:
        xyang[XYangKey.WHEN] = when_condition
    if presence:
        xyang[XYangKey.PRESENCE] = presence
    return xyang


def _copy_statement(stmt: YangStatement) -> YangStatement:
    """Deep-copy a statement subtree for uses expansion."""
    return copy_yang_statement(stmt)


def _expand_uses_for_json(
    statements: list[YangStatement], module: YangModule
) -> list[YangStatement]:
    """Expand ``uses`` on a deep-copied subtree so the module AST is not mutated."""
    return expand_uses_in_statements(
        [_copy_statement(s) for s in statements],
        module,
        (),
        [],
    )


def _partition_choice_sibling_statements(
    statements: list[YangStatement],
) -> tuple[list[YangStatement], YangChoiceStmt | None]:
    """Split siblings into (non-choice statements, sole choice) if exactly one choice exists."""
    choices = [s for s in statements if isinstance(s, YangChoiceStmt)]
    others = [s for s in statements if not isinstance(s, YangChoiceStmt)]
    if len(choices) == 1:
        return others, choices[0]
    return statements, None


def _merge_oneof_branches_with_base(
    one_of: list[dict[str, Any]],
    base_props: dict[str, Any],
    base_required: list[str],
) -> list[dict[str, Any]]:
    """Prefix each ``oneOf`` branch with common object properties (YANG choice has no instance node)."""
    merged: list[dict[str, Any]] = []
    base_req_unique = list(dict.fromkeys(base_required))
    for branch in one_of:
        if (
            branch.get(JsonSchemaKey.TYPE) == "object"
            and branch.get(JsonSchemaKey.MAX_PROPERTIES) == 0
        ):
            if base_props or base_required:
                merged.append(
                    {
                        JsonSchemaKey.TYPE: "object",
                        JsonSchemaKey.PROPERTIES: dict(base_props),
                        JsonSchemaKey.REQUIRED: list(base_req_unique),
                        JsonSchemaKey.ADDITIONAL_PROPERTIES: False,
                    }
                )
            else:
                merged.append(dict(branch))
            continue
        bp = dict(branch.get(JsonSchemaKey.PROPERTIES) or {})
        br = list(branch.get(JsonSchemaKey.REQUIRED) or [])
        merged.append(
            {
                JsonSchemaKey.TYPE: "object",
                JsonSchemaKey.PROPERTIES: {**base_props, **bp},
                JsonSchemaKey.REQUIRED: sorted(set(base_required) | set(br)),
                JsonSchemaKey.ADDITIONAL_PROPERTIES: False,
            }
        )
    return merged


def _choice_meta_xyang(choice_stmt: YangChoiceStmt) -> dict[str, Any]:
    """x-yang.choice metadata for hoisted (sibling-less or merged) choices."""
    return {
        JsonSchemaKey.NAME: choice_stmt.name,
        JsonSchemaKey.DESCRIPTION: choice_stmt.description or "",
        XYangKey.MANDATORY: bool(getattr(choice_stmt, "mandatory", False)),
    }


def _choice_to_object_body(
    choice_stmt: YangChoiceStmt,
    typedef_names: set[str],
    module: YangModule,
    leafref_parent: YangStatement | YangModule,
) -> dict[str, Any]:
    """
    Build choice as JSON Schema ``oneOf`` only: each case is a full object branch
    (``properties`` + ``required`` + ``additionalProperties: false``). No merged
    parent ``properties`` listing all case leaves. Case leaves use leafref_parent
    as XPath current() parent (choice/case are not data nodes).
    """
    case_keys_list: list[list[str]] = []
    case_props_list: list[dict[str, Any]] = []
    for case in getattr(choice_stmt, "cases", []) or []:
        if not isinstance(case, YangCaseStmt):
            continue
        case_props: dict[str, Any] = {}
        case_keys: list[str] = []
        for s in case.statements:
            child_prop = _statement_to_property(
                s, typedef_names, module, parent=leafref_parent
            )
            if child_prop is not None:
                case_props[s.name] = child_prop
                case_keys.append(s.name)
        if case_keys:
            case_keys_list.append(case_keys)
            case_props_list.append(case_props)
    out: dict[str, Any] = {JsonSchemaKey.DESCRIPTION: choice_stmt.description or ""}
    mandatory = getattr(choice_stmt, "mandatory", False)
    case_branch = [
        {
            JsonSchemaKey.TYPE: "object",
            JsonSchemaKey.PROPERTIES: cp,
            JsonSchemaKey.REQUIRED: list(keys),
            JsonSchemaKey.ADDITIONAL_PROPERTIES: False,
        }
        for cp, keys in zip(case_props_list, case_keys_list)
    ]
    if mandatory and case_props_list:
        out[JsonSchemaKey.ONE_OF] = case_branch
    elif not mandatory and len(case_props_list) > 1:
        out[JsonSchemaKey.ONE_OF] = [
            {JsonSchemaKey.TYPE: "object", JsonSchemaKey.MAX_PROPERTIES: 0},
            *case_branch,
        ]
    return out


def _statement_to_property(
    stmt: YangStatement,
    typedef_names: set[str],
    module: YangModule,
    parent: YangStatement | YangModule | None = None,
) -> dict[str, Any] | None:
    """Convert an AST statement to a JSON Schema property. Returns None for unsupported nodes. Expands uses when present."""
    from ..ast import YangContainerStmt, YangLeafListStmt, YangLeafStmt, YangListStmt

    if isinstance(stmt, YangContainerStmt):
        children = _expand_uses_for_json(stmt.statements, module)
        when_cond = None
        if getattr(stmt, "when", None) is not None:
            when_cond = getattr(stmt.when, "condition", None)
        others, hoisted_ch = _partition_choice_sibling_statements(children)
        if hoisted_ch is not None and others:
            base_props: dict[str, Any] = {}
            base_required: list[str] = []
            for child in others:
                child_prop = _statement_to_property(child, typedef_names, module, parent=stmt)
                if child_prop is not None:
                    base_props[child.name] = child_prop
                    if isinstance(child, YangLeafStmt) and child.mandatory:
                        base_required.append(child.name)
            ch_body = _choice_to_object_body(
                hoisted_ch, typedef_names, module, leafref_parent=stmt
            )
            xy_container = {
                **_build_xyang(
                    "container",
                    must_list=getattr(stmt, "must_statements", None) or [],
                    when_condition=when_cond,
                    presence=getattr(stmt, "presence", None),
                ),
                XYangKey.CHOICE: _choice_meta_xyang(hoisted_ch),
            }
            out = {
                JsonSchemaKey.TYPE: "object",
                JsonSchemaKey.DESCRIPTION: stmt.description or "",
                JsonSchemaKey.X_YANG: xy_container,
            }
            if JsonSchemaKey.ONE_OF in ch_body:
                out[JsonSchemaKey.ONE_OF] = _merge_oneof_branches_with_base(
                    ch_body[JsonSchemaKey.ONE_OF], base_props, base_required
                )
            elif ch_body.get(JsonSchemaKey.PROPERTIES):
                out[JsonSchemaKey.PROPERTIES] = {**base_props, **ch_body[JsonSchemaKey.PROPERTIES]}
                out[JsonSchemaKey.ADDITIONAL_PROPERTIES] = False
                req = list(base_required)
                if ch_body.get(JsonSchemaKey.REQUIRED):
                    req = sorted(set(req) | set(ch_body[JsonSchemaKey.REQUIRED]))
                if req:
                    out[JsonSchemaKey.REQUIRED] = req
            return out

        if len(children) == 1 and isinstance(children[0], YangChoiceStmt):
            # Choice (and case) are not data nodes; instance keys are case leaves on this container.
            ch_body = _choice_to_object_body(
                children[0], typedef_names, module, leafref_parent=stmt
            )
            ch0 = children[0]
            xy_container = {
                **_build_xyang(
                    "container",
                    must_list=getattr(stmt, "must_statements", None) or [],
                    when_condition=when_cond,
                    presence=getattr(stmt, "presence", None),
                ),
                XYangKey.CHOICE: _choice_meta_xyang(ch0),
            }
            out = {
                JsonSchemaKey.TYPE: "object",
                # Choice text lives in x-yang.choice.description; do not merge onto the container.
                JsonSchemaKey.DESCRIPTION: stmt.description or "",
                JsonSchemaKey.X_YANG: xy_container,
            }
            if JsonSchemaKey.ONE_OF in ch_body:
                out[JsonSchemaKey.ONE_OF] = ch_body[JsonSchemaKey.ONE_OF]
            elif ch_body.get(JsonSchemaKey.PROPERTIES):
                out[JsonSchemaKey.PROPERTIES] = ch_body[JsonSchemaKey.PROPERTIES]
                out[JsonSchemaKey.ADDITIONAL_PROPERTIES] = False
            return out

        props: dict[str, Any] = {}
        required: list[str] = []
        for child in children:
            child_prop = _statement_to_property(child, typedef_names, module, parent=stmt)
            if child_prop is not None:
                props[child.name] = child_prop
                if isinstance(child, YangLeafStmt) and child.mandatory:
                    required.append(child.name)
        out = {
            JsonSchemaKey.TYPE: "object",
            JsonSchemaKey.DESCRIPTION: stmt.description or "",
            JsonSchemaKey.X_YANG: _build_xyang(
                "container",
                must_list=getattr(stmt, "must_statements", None) or [],
                when_condition=when_cond,
                presence=getattr(stmt, "presence", None),
            ),
        }
        if props:
            out[JsonSchemaKey.PROPERTIES] = props
        if required:
            out[JsonSchemaKey.REQUIRED] = required
        out[JsonSchemaKey.ADDITIONAL_PROPERTIES] = False
        return out

    if isinstance(stmt, YangListStmt):
        # Match parser/yang_parser: do not expand uses under lists refined to max-elements 0
        # (xFrame meta-model breaks composite recursion that way).
        if getattr(stmt, "max_elements", None) == 0:
            list_children = [_copy_statement(s) for s in stmt.statements]
        else:
            list_children = _expand_uses_for_json(stmt.statements, module)
        when_cond = None
        if getattr(stmt, "when", None) is not None:
            when_cond = getattr(stmt.when, "condition", None)
        list_xy = _build_xyang(
            "list",
            key=stmt.key,
            must_list=getattr(stmt, "must_statements", None) or [],
            when_condition=when_cond,
        )
        items: dict[str, Any]
        others_lc, hoisted_list_ch = _partition_choice_sibling_statements(list_children)
        if hoisted_list_ch is not None and others_lc:
            list_base_props: dict[str, Any] = {}
            list_base_required: list[str] = []
            for child in others_lc:
                child_prop = _statement_to_property(child, typedef_names, module, parent=stmt)
                if child_prop is not None:
                    list_base_props[child.name] = child_prop
                    if isinstance(child, YangLeafStmt) and child.mandatory:
                        list_base_required.append(child.name)
            ch_body = _choice_to_object_body(
                hoisted_list_ch, typedef_names, module, leafref_parent=stmt
            )
            list_xy = {**list_xy, XYangKey.CHOICE: _choice_meta_xyang(hoisted_list_ch)}
            items = {JsonSchemaKey.TYPE: "object"}
            if JsonSchemaKey.ONE_OF in ch_body:
                items[JsonSchemaKey.ONE_OF] = _merge_oneof_branches_with_base(
                    ch_body[JsonSchemaKey.ONE_OF], list_base_props, list_base_required
                )
            else:
                items[JsonSchemaKey.PROPERTIES] = {
                    **list_base_props,
                    **(ch_body.get(JsonSchemaKey.PROPERTIES) or {}),
                }
                items[JsonSchemaKey.ADDITIONAL_PROPERTIES] = False
                req = list(list_base_required)
                if ch_body.get(JsonSchemaKey.REQUIRED):
                    req = sorted(set(req) | set(ch_body[JsonSchemaKey.REQUIRED]))
                if req:
                    items[JsonSchemaKey.REQUIRED] = req
        elif len(list_children) == 1 and isinstance(list_children[0], YangChoiceStmt):
            ch0 = list_children[0]
            ch_body = _choice_to_object_body(
                ch0, typedef_names, module, leafref_parent=stmt
            )
            list_xy = {**list_xy, XYangKey.CHOICE: _choice_meta_xyang(ch0)}
            items = {JsonSchemaKey.TYPE: "object"}
            if JsonSchemaKey.ONE_OF in ch_body:
                items[JsonSchemaKey.ONE_OF] = ch_body[JsonSchemaKey.ONE_OF]
            else:
                items[JsonSchemaKey.PROPERTIES] = ch_body.get(JsonSchemaKey.PROPERTIES) or {}
                items[JsonSchemaKey.ADDITIONAL_PROPERTIES] = False
        else:
            items = {JsonSchemaKey.TYPE: "object", JsonSchemaKey.PROPERTIES: {}}
            item_required: list[str] = []
            for child in list_children:
                child_prop = _statement_to_property(child, typedef_names, module, parent=stmt)
                if child_prop is not None:
                    items[JsonSchemaKey.PROPERTIES][child.name] = child_prop
                    if isinstance(child, YangLeafStmt) and child.mandatory:
                        item_required.append(child.name)
            if item_required:
                items[JsonSchemaKey.REQUIRED] = item_required
            items[JsonSchemaKey.ADDITIONAL_PROPERTIES] = False
        out = {
            JsonSchemaKey.TYPE: "array",
            JsonSchemaKey.ITEMS: items,
            JsonSchemaKey.DESCRIPTION: stmt.description or "",
            JsonSchemaKey.X_YANG: list_xy,
        }
        if getattr(stmt, "min_elements", None) is not None and stmt.min_elements is not None:
            out[JsonSchemaKey.MIN_ITEMS] = stmt.min_elements
        if getattr(stmt, "max_elements", None) is not None and stmt.max_elements is not None:
            out[JsonSchemaKey.MAX_ITEMS] = stmt.max_elements
        return out

    if isinstance(stmt, YangLeafStmt):
        type_stmt = stmt.type
        when_cond = None
        if getattr(stmt, "when", None) is not None:
            when_cond = getattr(stmt.when, "condition", None)
        if type_stmt and type_stmt.name in typedef_names:
            out = {
                JsonSchemaKey.REF: json_schema_defs_uri(type_stmt.name),
                JsonSchemaKey.DESCRIPTION: stmt.description or "",
                JsonSchemaKey.X_YANG: _build_xyang(
                    "leaf",
                    must_list=getattr(stmt, "must_statements", None) or [],
                    when_condition=when_cond,
                ),
            }
        else:
            lr_anchor = _leafref_context_parent(module, parent)
            type_schema = _type_to_schema(
                type_stmt,
                typedef_names,
                module=module,
                leafref_anchor=lr_anchor,
            )
            leaf_xyang = _build_xyang(
                "leaf",
                must_list=getattr(stmt, "must_statements", None) or [],
                when_condition=when_cond,
            )
            # Preserve leafref (type, path, require-instance) from type_schema x-yang
            if type_schema.get(JsonSchemaKey.X_YANG):
                leaf_xyang = {**leaf_xyang, **type_schema.get(JsonSchemaKey.X_YANG, {})}
            out = {
                **{k: v for k, v in type_schema.items() if k != JsonSchemaKey.X_YANG},
                JsonSchemaKey.DESCRIPTION: stmt.description or "",
                JsonSchemaKey.X_YANG: leaf_xyang,
            }
        if stmt.default is not None:
            out[JsonSchemaKey.DEFAULT] = stmt.default
        return out

    if isinstance(stmt, YangLeafListStmt):
        type_stmt = stmt.type
        lr_anchor = _leafref_context_parent(module, parent)
        items_schema = _type_to_schema(
            type_stmt,
            typedef_names,
            module=module,
            leafref_anchor=lr_anchor,
        )
        when_cond = None
        if getattr(stmt, "when", None) is not None:
            when_cond = getattr(stmt.when, "condition", None)
        out = {
            JsonSchemaKey.TYPE: "array",
            JsonSchemaKey.ITEMS: items_schema,
            JsonSchemaKey.DESCRIPTION: stmt.description or "",
            JsonSchemaKey.X_YANG: _build_xyang(
                "leaf-list",
                must_list=getattr(stmt, "must_statements", None) or [],
                when_condition=when_cond,
            ),
        }
        if getattr(stmt, "min_elements", None) is not None and stmt.min_elements is not None:
            out[JsonSchemaKey.MIN_ITEMS] = stmt.min_elements
        if getattr(stmt, "max_elements", None) is not None and stmt.max_elements is not None:
            out[JsonSchemaKey.MAX_ITEMS] = stmt.max_elements
        return out

    if isinstance(stmt, YangChoiceStmt):
        anchor = parent if parent is not None else module
        body = _choice_to_object_body(stmt, typedef_names, module, leafref_parent=anchor)
        out = {
            JsonSchemaKey.TYPE: "object",
            JsonSchemaKey.DESCRIPTION: body.get(JsonSchemaKey.DESCRIPTION, ""),
            JsonSchemaKey.X_YANG: {
                XYangKey.TYPE: "choice",
                XYangKey.MANDATORY: bool(getattr(stmt, "mandatory", False)),
            },
        }
        if body.get(JsonSchemaKey.PROPERTIES):
            out[JsonSchemaKey.PROPERTIES] = body[JsonSchemaKey.PROPERTIES]
        if JsonSchemaKey.ONE_OF in body:
            out[JsonSchemaKey.ONE_OF] = body[JsonSchemaKey.ONE_OF]
        return out

    return None


def _typedef_to_def(name: str, typedef: YangTypedefStmt, module: YangModule) -> dict[str, Any]:
    """Convert YangTypedefStmt to a $defs entry."""
    type_stmt = typedef.type
    schema = _type_to_schema(
        type_stmt,
        set(),
        module=module,
        leafref_anchor=None,
    )  # no $ref inside typedef def
    schema[JsonSchemaKey.DESCRIPTION] = typedef.description or ""
    schema[JsonSchemaKey.X_YANG] = {XYangKey.TYPE: "typedef"}
    return schema


def generate_json_schema(module: YangModule) -> dict[str, Any]:
    """
    Build a JSON Schema dict from a YangModule AST.

    The output has the structure expected by parse_json_schema: root x-yang (module
    meta), properties (one entry per module-level data node), and $defs (typedefs).
    """
    typedef_names = set(module.typedefs.keys())
    root_xyang: dict[str, Any] = {
        XYangKey.MODULE: module.name or "unknown",
        XYangKey.YANG_VERSION: getattr(module, "yang_version", "1.1"),
        XYangKey.NAMESPACE: module.namespace or "",
        XYangKey.PREFIX: module.prefix or "",
        XYangKey.ORGANIZATION: module.organization or "",
        XYangKey.CONTACT: module.contact or "",
    }
    properties: dict[str, Any] = {}
    for stmt in module.statements:
        if not getattr(stmt, "name", None):
            continue
        prop = _statement_to_property(stmt, typedef_names, module, parent=module)
        if prop is not None:
            properties[stmt.name] = prop

    defs: dict[str, Any] = {}
    for name, typedef in module.typedefs.items():
        if isinstance(typedef, YangTypedefStmt):
            defs[name] = _typedef_to_def(name, typedef, module)

    root: dict[str, Any] = {
        JsonSchemaKey.SCHEMA: "https://json-schema.org/draft/2020-12/schema",
        JsonSchemaKey.ID: module.namespace or f"urn:{module.name or 'unknown'}",
        JsonSchemaKey.DESCRIPTION: module.description or "",
        JsonSchemaKey.X_YANG: root_xyang,
        JsonSchemaKey.TYPE: "object",
        JsonSchemaKey.PROPERTIES: properties,
        JsonSchemaKey.ADDITIONAL_PROPERTIES: False,
    }
    if defs:
        root[JsonSchemaKey.DEFS] = defs
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
