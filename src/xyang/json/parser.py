"""
Parser that builds a YANG AST (xyang.ast / YangModule) from a JSON Schema file
with x-yang annotations (e.g. meta-model.json).

Reuses existing AST nodes: YangModule, YangContainerStmt, YangListStmt,
YangLeafStmt, YangLeafListStmt, YangTypedefStmt, YangTypeStmt, YangMustStmt.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ..module import YangModule
from ..ast import (
    YangAnydataStmt,
    YangAnyxmlStmt,
    YangBitStmt,
    YangCaseStmt,
    YangChoiceStmt,
    YangContainerStmt,
    YangIdentityStmt,
    YangListStmt,
    YangLeafStmt,
    YangLeafListStmt,
    YangStatement,
    YangTypedefStmt,
    YangTypeStmt,
    YangMustStmt,
    YangWhenStmt,
)
from ..xpath import XPathParser

from .schema_keys import (
    JSON_SCHEMA_DEFS_URI_PREFIX,
    JsonSchemaKey,
    XYangKey,
    XYangMustEntryKey,
    XYangTypeValue,
    XYangWhenEntryKey,
)


def _get_xyang(schema: dict[str, Any]) -> dict[str, Any]:
    """Extract x-yang object from a schema node (property or $def)."""
    return schema.get(JsonSchemaKey.X_YANG) or {}


def _if_features_from_xyang(xyang: dict[str, Any]) -> list[str]:
    """Parse ``x-yang`` ``if-features``: AND of RFC ``if-feature`` substatements (string or string list)."""
    raw = xyang.get(XYangKey.IF_FEATURES)
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, list):
        return [str(x) for x in raw if isinstance(x, str) and x.strip()]
    return []


def _set_if_features_from_xyang(stmt: Any, xyang: dict[str, Any]) -> None:
    feats = _if_features_from_xyang(xyang)
    if feats:
        stmt.if_features = feats


def _when_from_xyang(xyang: dict[str, Any]) -> YangWhenStmt | None:
    """Build YangWhenStmt from x-yang ``when``: object with ``condition`` and optional ``description``."""
    raw = xyang.get(XYangKey.WHEN)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    cond = raw.get(XYangWhenEntryKey.CONDITION)
    if not cond or not isinstance(cond, str):
        return None
    desc = raw.get(JsonSchemaKey.DESCRIPTION) or ""
    if not isinstance(desc, str):
        desc = str(desc)
    return YangWhenStmt(expression=cond, description=desc)


def _ref_to_typedef_name(ref: str) -> str | None:
    """Return typedef name from $ref like '#/$defs/entity-name' or None."""
    if not ref or not ref.startswith(JSON_SCHEMA_DEFS_URI_PREFIX):
        return None
    return ref.removeprefix(JSON_SCHEMA_DEFS_URI_PREFIX)


def _fraction_digits_from_multiple_of(value: Any) -> int | None:
    """If value equals 10^-n for integer n in 1..18, return n; else None."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if d <= 0 or d >= 1:
        return None
    n = 0
    t = d
    while t < 1 and n < 18:
        t *= 10
        n += 1
    if t == 1:
        return n
    return None


def _resolve_schema(schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """Resolve $ref and allOf to a single schema with merged properties (for list items / groupings)."""
    if not schema or not isinstance(schema, dict):
        return {}
    if JsonSchemaKey.REF in schema and len(schema) <= 2:
        name = _ref_to_typedef_name(schema[JsonSchemaKey.REF])
        if name and name in defs:
            return _resolve_schema(defs[name], defs)
    if JsonSchemaKey.ALL_OF in schema:
        merged: dict[str, Any] = {JsonSchemaKey.PROPERTIES: {}}
        for part in schema.get(JsonSchemaKey.ALL_OF) or []:
            if isinstance(part, dict):
                resolved = _resolve_schema(part, defs)
                merged[JsonSchemaKey.PROPERTIES] = {
                    **merged.get(JsonSchemaKey.PROPERTIES, {}),
                    **resolved.get(JsonSchemaKey.PROPERTIES, {}),
                }
                for k, v in resolved.items():
                    if k != JsonSchemaKey.PROPERTIES:
                        merged[k] = v
        return merged
    return schema


def _type_from_schema(defs: dict[str, Any], schema: dict[str, Any], xyang: dict[str, Any]) -> YangTypeStmt | None:
    """Build YangTypeStmt from JSON schema (+ $ref) and x-yang (e.g. leafref)."""
    if xyang.get(XYangKey.TYPE) == XYangTypeValue.IDENTITYREF:
        bases = xyang.get(XYangKey.BASES)
        if not isinstance(bases, list):
            bases = []
        if not bases:
            b = xyang.get(XYangKey.BASE)
            if isinstance(b, str):
                bases = [b]
        return YangTypeStmt(name="identityref", identityref_bases=list(bases))
    if xyang.get(XYangKey.TYPE) == XYangTypeValue.INSTANCE_IDENTIFIER:
        require = xyang.get(XYangKey.REQUIRE_INSTANCE, True)
        return YangTypeStmt(
            name="instance-identifier",
            require_instance=bool(require),
        )
    if xyang.get(XYangKey.TYPE) == XYangTypeValue.BITS:
        raw = xyang.get(XYangKey.BITS)
        bits: list[YangBitStmt] = []
        if isinstance(raw, dict):
            for name, pos in raw.items():
                if not isinstance(name, str) or not name:
                    continue
                try:
                    p = int(pos)
                except (TypeError, ValueError):
                    continue
                bits.append(YangBitStmt(name=name, position=p))
            bits.sort(key=lambda b: (b.position if b.position is not None else 0, b.name))
        elif isinstance(raw, list):
            # Legacy: [{ "name", "position" }, …] or bare names with index as position
            for i, item in enumerate(raw):
                if isinstance(item, dict):
                    nm = item.get("name")
                    if not isinstance(nm, str) or not nm:
                        continue
                    pos = item.get("position", i)
                    try:
                        p = int(pos)
                    except (TypeError, ValueError):
                        p = i
                    bits.append(YangBitStmt(name=nm, position=p))
                elif isinstance(item, str) and item:
                    bits.append(YangBitStmt(name=item, position=i))
        if bits:
            return YangTypeStmt(name="bits", bits=bits)
    # Leafref from x-yang: path must be parsed to PathNode (same as YANG parser)
    if xyang.get(XYangKey.TYPE) == "leafref":
        path_val = xyang.get(XYangKey.PATH)
        require = xyang.get(XYangKey.REQUIRE_INSTANCE, True)
        path_node = None
        if path_val is not None and isinstance(path_val, str) and path_val.strip():
            # Let XPathParser errors surface: invalid leafref paths from JSON
            # schema are programmer / schema bugs and should abort parsing.
            path_node = XPathParser(path_val.strip()).parse_path()
        type_stmt = YangTypeStmt(name=XYangTypeValue.LEAFREF, path=path_node, require_instance=bool(require))
        return type_stmt
    # $ref to typedef: preserve typedef name only (no range/pattern; matches YANG leaf type reference)
    ref = schema.get(JsonSchemaKey.REF)
    if ref:
        name = _ref_to_typedef_name(ref)
        if name:
            return YangTypeStmt(name=name)
    # Inline type
    t = schema.get(JsonSchemaKey.TYPE)
    if JsonSchemaKey.ENUM in schema:
        enums = list(schema[JsonSchemaKey.ENUM]) if isinstance(schema[JsonSchemaKey.ENUM], list) else []
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
        if JsonSchemaKey.PATTERN in schema:
            p = schema[JsonSchemaKey.PATTERN]
            if isinstance(p, str) and p.startswith("^") and p.endswith("$"):
                p = p[1:-1]
            type_stmt.pattern = p
        min_len = schema.get(JsonSchemaKey.MIN_LENGTH)
        max_len = schema.get(JsonSchemaKey.MAX_LENGTH)
        if min_len is not None and max_len is not None:
            type_stmt.length = f"{min_len}..{max_len}"
        elif max_len is not None:
            type_stmt.length = f"0..{max_len}"
        elif min_len is not None:
            type_stmt.length = f"{min_len}.."
        return type_stmt
    if t == "integer":
        min_val = schema.get(JsonSchemaKey.MINIMUM)
        max_val = schema.get(JsonSchemaKey.MAXIMUM)
        if min_val == 0 and max_val == 255:
            type_stmt = YangTypeStmt(name="uint8")
            # Leave range unset to match YANG (built-in uint8 has no range on leaf type)
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
        type_stmt = YangTypeStmt(name="decimal64")
        legacy_fd = schema.get(JsonSchemaKey.X_FRACTION_DIGITS)
        if isinstance(legacy_fd, int) and legacy_fd > 0:
            type_stmt.fraction_digits = legacy_fd
        else:
            mo = schema.get(JsonSchemaKey.MULTIPLE_OF)
            fd = _fraction_digits_from_multiple_of(mo)
            if fd is not None:
                type_stmt.fraction_digits = fd
        min_val = schema.get(JsonSchemaKey.MINIMUM)
        max_val = schema.get(JsonSchemaKey.MAXIMUM)
        if min_val is not None or max_val is not None:
            lo = "min" if min_val is None else str(min_val)
            hi = "max" if max_val is None else str(max_val)
            type_stmt.range = f"{lo}..{hi}"
        return type_stmt
    if t == "boolean":
        return YangTypeStmt(name="boolean")
    if t == "object" and schema.get(JsonSchemaKey.MAX_PROPERTIES) == 0:
        return YangTypeStmt(name="empty")
    if JsonSchemaKey.ONE_OF in schema:
        union_types = []
        for branch in schema.get(JsonSchemaKey.ONE_OF) or []:
            if isinstance(branch, dict):
                branch_xyang = branch.get(JsonSchemaKey.X_YANG) or {}
                bt = _type_from_schema(defs, branch, branch_xyang)
                if bt:
                    union_types.append(bt)
        if union_types:
            return YangTypeStmt(name="union", types=union_types)
    return None


def _is_identity_def_schema(def_schema: dict[str, Any]) -> bool:
    return _get_xyang(def_schema).get(XYangKey.TYPE) == XYangTypeValue.IDENTITY


def _is_typedef_def_schema(def_schema: dict[str, Any]) -> bool:
    """$defs entries are typedefs unless they are identities.

    The generator may set ``x-yang.type`` on a typedef body (e.g. ``leafref``, ``bits``);
    those entries must still be treated as typedefs, not skipped.
    """
    t = _get_xyang(def_schema).get(XYangKey.TYPE)
    if t == XYangTypeValue.IDENTITY:
        return False
    return True


def _build_typedef(def_name: str, def_schema: dict[str, Any], defs: dict[str, Any]) -> YangTypedefStmt | None:
    """Build YangTypedefStmt from a $defs entry."""
    xyang = _get_xyang(def_schema)
    if not _is_typedef_def_schema(def_schema):
        return None
    desc = def_schema.get(JsonSchemaKey.DESCRIPTION, "")
    type_stmt = _type_from_schema(defs, def_schema, xyang)
    if type_stmt is None:
        type_stmt = YangTypeStmt(name="string")
    stmt = YangTypedefStmt(name=def_name, description=desc, type=type_stmt)
    return stmt


def _build_identity(def_name: str, def_schema: dict[str, Any]) -> YangIdentityStmt | None:
    """Build YangIdentityStmt from a $defs entry with x-yang type identity."""
    if not _is_identity_def_schema(def_schema):
        return None
    xyang = _get_xyang(def_schema)
    bases = xyang.get(XYangKey.BASES) or []
    if not isinstance(bases, list):
        bases = []
    desc = def_schema.get(JsonSchemaKey.DESCRIPTION, "")
    ident = YangIdentityStmt(name=def_name, description=desc, bases=list(bases))
    _set_if_features_from_xyang(ident, xyang)
    return ident


def _build_must_list(xyang: dict[str, Any]) -> list[YangMustStmt]:
    """Build list of YangMustStmt from x-yang must (list of {must, error-message, description})."""
    out = []
    for m in xyang.get(XYangKey.MUST) or []:
        if isinstance(m, dict):
            out.append(
                YangMustStmt(
                    expression=m.get(XYangMustEntryKey.MUST, ""),
                    error_message=m.get(XYangMustEntryKey.ERROR_MESSAGE, ""),
                    description=m.get(JsonSchemaKey.DESCRIPTION, ""),
                )
            )
    return out


def _property_schema_and_xyang(prop_value: dict[str, Any], defs: dict[str, Any]) -> tuple[dict, dict]:
    """Resolve property value (maybe with $ref + allOf) to one schema and merged x-yang."""
    if JsonSchemaKey.REF in prop_value and JsonSchemaKey.X_YANG in prop_value:
        ref_name = _ref_to_typedef_name(prop_value[JsonSchemaKey.REF])
        base = defs.get(ref_name, {}) if ref_name else {}
        # Merge: base schema + prop_value overrides; x-yang from base merged with prop_value (so must, etc. from def are kept)
        schema = {
            **base,
            **{k: v for k, v in prop_value.items() if k != JsonSchemaKey.X_YANG},
        }
        base_xyang = base.get(JsonSchemaKey.X_YANG) or {}
        prop_xyang = prop_value.get(JsonSchemaKey.X_YANG) or {}
        merged_xyang = {**base_xyang, **prop_xyang}
        return schema, merged_xyang
    if JsonSchemaKey.ALL_OF in prop_value:
        merged = {}
        xyang = {}
        for part in prop_value[JsonSchemaKey.ALL_OF]:
            if isinstance(part, dict):
                if JsonSchemaKey.REF in part:
                    name = _ref_to_typedef_name(part[JsonSchemaKey.REF])
                    if name:
                        merged.update(defs.get(name, {}))
                else:
                    merged.update(part)
                xyang.update(part.get(JsonSchemaKey.X_YANG) or {})
        top_xy = prop_value.get(JsonSchemaKey.X_YANG) or {}
        merged_xyang = {**xyang, **top_xy}
        return merged, merged_xyang
    return prop_value, _get_xyang(prop_value)


def _empty_optional_choice_branch(branch: Any) -> bool:
    """First branch of optional hoisted choice: instance may omit all case leaves."""
    return (
        isinstance(branch, dict)
        and branch.get(JsonSchemaKey.TYPE) == "object"
        and branch.get(JsonSchemaKey.MAX_PROPERTIES) == 0
    )


def _hoisted_container_is_choice_oneof(schema: dict[str, Any], xyang: dict[str, Any]) -> bool:
    """Container whose only data shape is ``oneOf`` (no merged ``properties`` for cases)."""
    if xyang.get(XYangKey.TYPE) != "container":
        return False
    one_of = schema.get(JsonSchemaKey.ONE_OF)
    if not isinstance(one_of, list) or not one_of:
        return False
    props = schema.get(JsonSchemaKey.PROPERTIES)
    if props:
        return False
    return True


def _hoisted_list_items_are_choice_oneof(items: dict[str, Any]) -> bool:
    """List entry object whose only data shape is ``oneOf`` (no merged ``properties``)."""
    if items.get(JsonSchemaKey.TYPE) != "object":
        return False
    one_of = items.get(JsonSchemaKey.ONE_OF)
    if not isinstance(one_of, list) or not one_of:
        return False
    if items.get(JsonSchemaKey.PROPERTIES):
        return False
    return True


def _parse_hoisted_choice_oneof(
    one_of: list[Any],
    defs: dict[str, Any],
    parent_path: str,
    *,
    mandatory: bool | None,
    choice_name: str = "hoisted-choice",
    choice_description: str = "",
    choice_xyang_meta: dict[str, Any] | None = None,
) -> list[YangStatement]:
    """
    Rebuild hoisted YANG choice from ``oneOf`` on the parent object.

    Returns sibling statements in schema order: common leaves (shared across
    branches), then a single ``YangChoiceStmt``. YANG choices are not instance
    nodes; case keys sit beside sibling leaves in instance data.
    """
    meta: dict[str, Any] = (
        choice_xyang_meta if isinstance(choice_xyang_meta, dict) else {}
    )
    branches = [b for b in one_of if isinstance(b, dict)]
    branches_with_props = [b for b in branches if not _empty_optional_choice_branch(b)]
    if not branches_with_props:
        branches_with_props = branches

    req_sets_all = [set(b.get(JsonSchemaKey.REQUIRED) or []) for b in branches]
    common_req = set.intersection(*req_sets_all) if req_sets_all else set()

    if mandatory is None:
        mandatory = not any(rs == common_req for rs in req_sets_all)

    case_branches = [
        b
        for b in branches_with_props
        if set(b.get(JsonSchemaKey.REQUIRED) or []) - common_req
    ]

    prop_key_sets = [
        set((b.get(JsonSchemaKey.PROPERTIES) or {}).keys()) for b in branches_with_props
    ]
    common_prop_keys = set.intersection(*prop_key_sets) if prop_key_sets else set()

    common_mandatory: set[str] = set()
    if case_branches:
        reqs_case = [set(b.get(JsonSchemaKey.REQUIRED) or []) for b in case_branches]
        common_mandatory = set.intersection(*reqs_case) if reqs_case else set()

    common_children: list[YangStatement] = []
    if common_prop_keys and branches_with_props:
        template = branches_with_props[0]
        tb_props = template.get(JsonSchemaKey.PROPERTIES) or {}
        for k in sorted(common_prop_keys):
            prop_val = tb_props.get(k)
            if prop_val is None:
                continue
            stmt = _convert_property(
                k,
                prop_val,
                defs,
                f"{parent_path}/{k}",
                mandatory_override=k in common_mandatory,
            )
            if stmt is not None:
                common_children.append(stmt)

    cases: list[YangCaseStmt] = []
    for branch in case_branches:
        bprops = branch.get(JsonSchemaKey.PROPERTIES) or {}
        breq = set(branch.get(JsonSchemaKey.REQUIRED) or [])
        disc_keys = sorted(breq - common_mandatory)
        case_statements: list[YangStatement] = []
        for dk in disc_keys:
            prop_val = bprops.get(dk)
            if prop_val is None:
                continue
            stmt = _convert_property(
                dk,
                prop_val,
                defs,
                f"{parent_path}/{dk}",
                mandatory_override=None,
            )
            if stmt is not None:
                case_statements.append(stmt)
        if case_statements:
            b_xyang = branch.get(JsonSchemaKey.X_YANG) or {}
            case_name = ""
            if isinstance(b_xyang, dict):
                case_name = str(b_xyang.get(JsonSchemaKey.NAME) or "").strip()
            if not case_name:
                label = disc_keys[0] if disc_keys else "case"
                case_name = f"{label}-case"
            case_desc = branch.get(JsonSchemaKey.DESCRIPTION)
            if not isinstance(case_desc, str):
                case_desc = ""
            case_stmt = YangCaseStmt(
                name=case_name, description=case_desc, statements=case_statements
            )
            _set_if_features_from_xyang(case_stmt, b_xyang)
            cases.append(case_stmt)

    choice_stmt = YangChoiceStmt(
        name=choice_name,
        description=choice_description,
        mandatory=mandatory,
        cases=cases,
    )
    _set_if_features_from_xyang(choice_stmt, meta)
    choice_stmt.validate_case_unique_child_names()
    return [*common_children, choice_stmt]


def _convert_container(
    name: str,
    schema: dict[str, Any],
    xyang: dict[str, Any],
    defs: dict[str, Any],
    parent_path: str,
    must_list: list[YangMustStmt],
) -> YangContainerStmt:
    """Convert a container property to YangContainerStmt."""
    description = schema.get(JsonSchemaKey.DESCRIPTION, "")
    props_raw = schema.get(JsonSchemaKey.PROPERTIES) or {}
    one_of = schema.get(JsonSchemaKey.ONE_OF)

    if _hoisted_container_is_choice_oneof(schema, xyang) and isinstance(one_of, list):
        choice_meta = xyang.get(XYangKey.CHOICE)
        meta: dict[str, Any] = choice_meta if isinstance(choice_meta, dict) else {}
        meta_m = meta.get(XYangKey.MANDATORY)
        man: bool | None = None if meta_m is None else bool(meta_m)
        child_statements = _parse_hoisted_choice_oneof(
            one_of,
            defs,
            parent_path,
            mandatory=man,
            choice_name=str(meta.get(JsonSchemaKey.NAME) or "hoisted-choice"),
            choice_description=str(meta.get(JsonSchemaKey.DESCRIPTION) or ""),
            choice_xyang_meta=meta,
        )
    else:
        child_statements = []
        container_required = set(schema.get(JsonSchemaKey.REQUIRED) or [])
        for child_name, child_val in props_raw.items():
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
    if xyang.get(XYangKey.PRESENCE) is not None:
        c.presence = xyang.get(XYangKey.PRESENCE)
    _set_if_features_from_xyang(c, xyang)
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
    description = schema.get(JsonSchemaKey.DESCRIPTION, "")
    key = xyang.get(XYangKey.KEY)
    items = _resolve_schema(schema.get(JsonSchemaKey.ITEMS) or {}, defs)
    item_props = items.get(JsonSchemaKey.PROPERTIES) or {}
    items_one = items.get(JsonSchemaKey.ONE_OF)
    item_base = f"{parent_path}/{name}"

    if _hoisted_list_items_are_choice_oneof(items) and isinstance(items_one, list):
        choice_meta = xyang.get(XYangKey.CHOICE)
        meta: dict[str, Any] = choice_meta if isinstance(choice_meta, dict) else {}
        meta_m = meta.get(XYangKey.MANDATORY)
        man: bool | None = None if meta_m is None else bool(meta_m)
        child_statements = _parse_hoisted_choice_oneof(
            items_one,
            defs,
            item_base,
            mandatory=man,
            choice_name=str(meta.get(JsonSchemaKey.NAME) or "hoisted-choice"),
            choice_description=str(meta.get(JsonSchemaKey.DESCRIPTION) or ""),
            choice_xyang_meta=meta,
        )
    else:
        child_statements = []
        item_required = set(items.get(JsonSchemaKey.REQUIRED) or [])
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
    if JsonSchemaKey.MIN_ITEMS in schema and schema[JsonSchemaKey.MIN_ITEMS] is not None:
        lst.min_elements = int(schema[JsonSchemaKey.MIN_ITEMS])
    if JsonSchemaKey.MAX_ITEMS in schema and schema[JsonSchemaKey.MAX_ITEMS] is not None:
        lst.max_elements = int(schema[JsonSchemaKey.MAX_ITEMS])
    _set_if_features_from_xyang(lst, xyang)
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
    description = schema.get(JsonSchemaKey.DESCRIPTION, "")
    type_schema = schema
    if JsonSchemaKey.REF in prop_value:
        ref_name = _ref_to_typedef_name(prop_value[JsonSchemaKey.REF])
        if ref_name and ref_name in defs:
            d = defs[ref_name]
            if _is_typedef_def_schema(d) or _is_identity_def_schema(d):
                type_schema = prop_value
    type_stmt = _type_from_schema(defs, type_schema, xyang)
    if type_stmt is None:
        type_stmt = YangTypeStmt(name="string")
    if mandatory_override is not None:
        mandatory = mandatory_override
    elif xyang.get(XYangKey.MANDATORY) is True:
        mandatory = True
    else:
        mandatory = name in (schema.get(JsonSchemaKey.REQUIRED) or [])
    default = schema.get(JsonSchemaKey.DEFAULT)
    if default is not None and schema.get(JsonSchemaKey.TYPE) != "boolean":
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
    _set_if_features_from_xyang(leaf, xyang)
    return leaf


def _convert_anydata_anyxml(
    name: str,
    schema: dict[str, Any],
    xyang: dict[str, Any],
    mandatory_override: bool | None,
    must_list: list[YangMustStmt],
    *,
    as_anyxml: bool,
) -> YangAnydataStmt | YangAnyxmlStmt:
    """Convert a property with x-yang type anydata or anyxml."""
    description = schema.get(JsonSchemaKey.DESCRIPTION, "")
    if mandatory_override is not None:
        mandatory = mandatory_override
    elif xyang.get(XYangKey.MANDATORY) is True:
        mandatory = True
    else:
        mandatory = name in (schema.get(JsonSchemaKey.REQUIRED) or [])
    cls = YangAnyxmlStmt if as_anyxml else YangAnydataStmt
    node = cls(name=name, description=description, mandatory=mandatory)
    node.must_statements = must_list
    when_stmt = _when_from_xyang(xyang)
    if when_stmt is not None:
        node.when = when_stmt
    _set_if_features_from_xyang(node, xyang)
    return node


def _convert_leaf_list(
    name: str,
    schema: dict[str, Any],
    xyang: dict[str, Any],
    defs: dict[str, Any],
    must_list: list[YangMustStmt],
) -> YangLeafListStmt:
    """Convert a leaf-list property to YangLeafListStmt."""
    description = schema.get(JsonSchemaKey.DESCRIPTION, "")
    items_schema = schema.get(JsonSchemaKey.ITEMS) or schema
    items_xyang = (
        (items_schema.get(JsonSchemaKey.X_YANG) or {}) if isinstance(items_schema, dict) else {}
    )
    type_stmt = _type_from_schema(defs, items_schema, items_xyang or xyang)
    if type_stmt is None:
        type_stmt = YangTypeStmt("string")
    when_stmt = _when_from_xyang(xyang)
    ll = YangLeafListStmt(
        statements=[],
        name=name,
        description=description,
        must_statements=must_list,
        when=when_stmt,
        type=type_stmt,
    )
    if JsonSchemaKey.MIN_ITEMS in schema and schema[JsonSchemaKey.MIN_ITEMS] is not None:
        ll.min_elements = int(schema[JsonSchemaKey.MIN_ITEMS])
    if JsonSchemaKey.MAX_ITEMS in schema and schema[JsonSchemaKey.MAX_ITEMS] is not None:
        ll.max_elements = int(schema[JsonSchemaKey.MAX_ITEMS])
    raw_def = schema.get(JsonSchemaKey.DEFAULT)
    if raw_def is not None:
        if isinstance(raw_def, list):
            ll.defaults = list(raw_def)
        else:
            ll.defaults = [raw_def]
    _set_if_features_from_xyang(ll, xyang)
    return ll


def _convert_choice(
    name: str,
    schema: dict[str, Any],
    xyang: dict[str, Any],
    defs: dict[str, Any],
    parent_path: str,
) -> YangChoiceStmt:
    """Convert a JSON schema property with x-yang type 'choice' to YangChoiceStmt. Uses oneOf (valid JSON Schema)."""
    description = schema.get(JsonSchemaKey.DESCRIPTION, "")
    mandatory = xyang.get(XYangKey.MANDATORY, False)
    one_of = schema.get(JsonSchemaKey.ONE_OF) or []
    cases: list[YangCaseStmt] = []
    for case_schema in one_of:
        if not isinstance(case_schema, dict):
            continue
        if _empty_optional_choice_branch(case_schema):
            continue
        case_xyang = _get_xyang(case_schema)
        case_name = case_xyang.get(JsonSchemaKey.NAME) or ""
        if not case_name and case_schema.get(JsonSchemaKey.REQUIRED):
            req = case_schema[JsonSchemaKey.REQUIRED]
            case_name = req[0] + "-case" if (isinstance(req, list) and len(req) == 1) else ""
        if not case_name:
            case_props = case_schema.get(JsonSchemaKey.PROPERTIES) or {}
            keys = list(case_props.keys())
            case_name = keys[0] + "-case" if len(keys) == 1 else ""
        case_props = case_schema.get(JsonSchemaKey.PROPERTIES) or {}
        case_statements: list[YangStatement] = []
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
        case_desc = case_schema.get(JsonSchemaKey.DESCRIPTION)
        if not isinstance(case_desc, str):
            case_desc = ""
        case_stmt = YangCaseStmt(
            name=case_name, description=case_desc, statements=case_statements
        )
        _set_if_features_from_xyang(case_stmt, case_xyang)
        cases.append(case_stmt)
    choice_stmt = YangChoiceStmt(
        name=name, description=description, mandatory=mandatory, cases=cases
    )
    _set_if_features_from_xyang(choice_stmt, xyang)
    choice_stmt.validate_case_unique_child_names()
    return choice_stmt


def _convert_property(
    name: str,
    prop_value: dict[str, Any],
    defs: dict[str, Any],
    parent_path: str,
    mandatory_override: bool | None = None,
) -> (
    YangContainerStmt
    | YangListStmt
    | YangLeafStmt
    | YangLeafListStmt
    | YangChoiceStmt
    | YangAnydataStmt
    | YangAnyxmlStmt
    | None
):
    """Convert one JSON schema property to a YANG AST statement. Returns None if not x-yang mapped."""
    schema, xyang = _property_schema_and_xyang(prop_value, defs)
    node_type = xyang.get(XYangKey.TYPE)
    if node_type == XYangTypeValue.LEAFREF:
        node_type = "leaf"
    if node_type == XYangTypeValue.IDENTITYREF:
        node_type = "leaf"
    if node_type == XYangTypeValue.INSTANCE_IDENTIFIER:
        node_type = "leaf"
    must_list = _build_must_list(xyang) if node_type in (
        "leaf",
        "leaf-list",
        "container",
        "list",
        XYangTypeValue.ANYDATA,
        XYangTypeValue.ANYXML,
    ) else []

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
    if node_type == XYangTypeValue.ANYDATA:
        return _convert_anydata_anyxml(
            name, schema, xyang, mandatory_override, must_list, as_anyxml=False
        )
    if node_type == XYangTypeValue.ANYXML:
        return _convert_anydata_anyxml(
            name, schema, xyang, mandatory_override, must_list, as_anyxml=True
        )
    return None


def parse_json_schema(source: str | Path | dict[str, Any]) -> YangModule:
    """
    Build a YangModule (and nested AST nodes from xyang.ast) from a JSON Schema
    with x-yang annotations.

    Args:
        source: Path to a .json file, or JSON string, or parsed dict.

    Returns:
        YangModule with .statements (one per root JSON Schema property, e.g.
        ``data-model`` or ``program``), and .typedefs.
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

    root_xyang = data.get(JsonSchemaKey.X_YANG) or {}
    defs = data.get(JsonSchemaKey.DEFS) or {}

    module = YangModule(
        name=root_xyang.get(XYangKey.MODULE, "unknown"),
        yang_version=root_xyang.get(XYangKey.YANG_VERSION, "1.1"),
        namespace=root_xyang.get(XYangKey.NAMESPACE, ""),
        prefix=root_xyang.get(XYangKey.PREFIX, ""),
        organization=root_xyang.get(XYangKey.ORGANIZATION, ""),
        contact=root_xyang.get(XYangKey.CONTACT, ""),
        description=data.get(JsonSchemaKey.DESCRIPTION, ""),
    )

    for def_name, def_schema in defs.items():
        if not isinstance(def_schema, dict):
            continue
        ident = _build_identity(def_name, def_schema)
        if ident is not None:
            module.identities[def_name] = ident
            continue
        td = _build_typedef(def_name, def_schema, defs)
        if td is not None:
            module.typedefs[def_name] = td

    root_props = data.get(JsonSchemaKey.PROPERTIES) or {}
    for root_name, root_val in root_props.items():
        if not isinstance(root_val, dict):
            continue
        stmt = _convert_property(root_name, root_val, defs, f"/{root_name}")
        if stmt is not None:
            module.statements.append(stmt)

    return module
