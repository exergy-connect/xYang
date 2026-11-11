"""
Parser that builds a YANG AST (xyang.ast / YangModule) from a JSON Schema file
with x-yang annotations (e.g. meta-model.json).

Reuses existing AST nodes: YangModule, YangContainerStmt, YangListStmt,
YangLeafStmt, YangLeafListStmt, YangTypedefStmt, YangTypeStmt, YangMustStmt.
"""

from __future__ import annotations

import contextvars
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ..module import YangModule
from ..identifier_ref import YangIdentifierRef, coerce_identifier_ref
from ..ext import ensure_builtin_extensions_loaded
from ..ext.capabilities import ExtensionIdentity, apply_extension_invocations, get_extension_apply_callback
from ..ast import (
    YangAnydataStmt,
    YangAnyxmlStmt,
    YangCaseStmt,
    YangChoiceStmt,
    YangContainerStmt,
    YangExtensionInvocationStmt,
    YangExtensionStmt,
    YangIdentityStmt,
    YangInputStmt,
    YangListStmt,
    YangLeafStmt,
    YangLeafListStmt,
    YangOutputStmt,
    YangRpcStmt,
    YangActionStmt,
    YangStatement,
    YangTypedefStmt,
    YangTypeStmt,
    YangPatternSpec,
    YangMustStmt,
    YangWhenStmt,
)
from ..types.registry import is_string_number, type_stmt_from_schema
from ..xpath.parser import bind_xpath_prefixes
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


def _merge_schema_xyang(schema: dict[str, Any], xyang: dict[str, Any]) -> dict[str, Any]:
    """Merge caller ``xyang`` with ``schema``'s own ``x-yang`` (schema wins on duplicate keys)."""
    inner = schema.get(JsonSchemaKey.X_YANG) if isinstance(schema, dict) else None
    if not isinstance(inner, dict):
        inner = {}
    return {**xyang, **inner}


def _pattern_metadata_from_xyang(
    xyang_merged: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Top-level ``x-yang`` pattern error metadata (legacy single-pattern schemas)."""
    em = xyang_merged.get(XYangKey.PATTERN_ERROR_MESSAGE)
    tag = xyang_merged.get(XYangKey.PATTERN_ERROR_APP_TAG)
    pem = em if isinstance(em, str) else None
    pet = tag if isinstance(tag, str) else None
    return pem, pet


def _apply_string_pattern_entries(
    type_stmt: YangTypeStmt, xyang_merged: dict[str, Any]
) -> None:
    """Restore full pattern list (including invert-match) from x-yang metadata."""
    raw = xyang_merged.get(XYangKey.STRING_PATTERNS)
    if not isinstance(raw, list):
        return
    out: list[YangPatternSpec] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        patt = item.get(JsonSchemaKey.PATTERN)
        if not isinstance(patt, str):
            continue
        out.append(
            YangPatternSpec(
                pattern=patt,
                invert_match=bool(item.get("invert-match", False)),
                error_message=item.get(XYangKey.PATTERN_ERROR_MESSAGE)
                if isinstance(item.get(XYangKey.PATTERN_ERROR_MESSAGE), str)
                else None,
                error_app_tag=item.get(XYangKey.PATTERN_ERROR_APP_TAG)
                if isinstance(item.get(XYangKey.PATTERN_ERROR_APP_TAG), str)
                else None,
            )
        )
    if out:
        type_stmt.patterns = out


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
    path = xyang.get(XYangKey.AUGMENT_STRUCTURE)
    if isinstance(path, str) and path:
        stmt.augment_structure = path


def _units_from_xyang(xyang: dict[str, Any]) -> str:
    """RFC 7950 ``units`` from ``x-yang.units``."""
    u = xyang.get(XYangKey.UNITS)
    return u if isinstance(u, str) else ""


def _set_config_from_xyang(stmt: Any, xyang: dict[str, Any]) -> None:
    """RFC 7950 §7.21.1 ``config`` from ``x-yang.config`` when explicitly set."""
    if XYangKey.CONFIG in xyang and isinstance(xyang[XYangKey.CONFIG], bool):
        stmt.config = xyang[XYangKey.CONFIG]


def recorded_prefixes(raw: Any) -> dict[str, str]:
    """Validate an ``x-yang`` ``xpath-prefixes`` map; anything else is a load error."""
    if not isinstance(raw, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in raw.items()):
        raise ValueError(f'"{XYangKey.XPATH_PREFIXES}" must map prefixes to module names, got {raw!r}')
    return raw


def _bind_recorded(stmt: Any, raw: dict[str, Any]) -> None:
    if XYangKey.XPATH_PREFIXES in raw:
        stmt.bind_prefixes(None, recorded_prefixes(raw[XYangKey.XPATH_PREFIXES]))
        stmt.prefixes_bound = True


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
    when = YangWhenStmt(expression=cond, description=desc)
    if raw.get("evaluate-with-parent-context") is True or raw.get("evaluate_with_parent_context") is True:
        when.evaluate_with_parent_context = True
    _bind_recorded(when, raw)
    return when


def _bases_from_json(raw: Any) -> list[YangIdentifierRef]:
    if not isinstance(raw, list):
        return []
    out: list[YangIdentifierRef] = []
    for item in raw:
        ref = coerce_identifier_ref(item)
        if ref is not None:
            out.append(ref)
    return out


def _ref_to_typedef_name(ref: str) -> str | None:
    """Return typedef name from $ref like '#/$defs/entity-name' or None."""
    if not ref or not ref.startswith(JSON_SCHEMA_DEFS_URI_PREFIX):
        return None
    return ref.removeprefix(JSON_SCHEMA_DEFS_URI_PREFIX)


def _format_decimal64_bound(value: Any, fraction_digits: int | None) -> str:
    """Format a decimal64 range bound to match YANG lexical form (e.g. 4 -> 4.0)."""
    if fraction_digits is not None and fraction_digits > 0:
        try:
            return f"{float(value):.{fraction_digits}f}"
        except (TypeError, ValueError):
            pass
    return str(value)


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
    stmt = type_stmt_from_schema(defs, schema, xyang)
    if stmt is not None:
        merged_xy = _merge_schema_xyang(schema, xyang)
        units = _units_from_xyang(merged_xy)
        if units:
            stmt.units = units
    return stmt


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
    default = def_schema.get(JsonSchemaKey.DEFAULT)
    stmt = YangTypedefStmt(
        name=def_name,
        description=desc,
        type=type_stmt,
        default=default,
    )
    units = _units_from_xyang(xyang)
    if units:
        stmt.units = units
    _attach_invocations(stmt, xyang)
    return stmt


def _build_identity(def_name: str, def_schema: dict[str, Any]) -> YangIdentityStmt | None:
    """Build YangIdentityStmt from a $defs entry with x-yang type identity."""
    if not _is_identity_def_schema(def_schema):
        return None
    xyang = _get_xyang(def_schema)
    bases = _bases_from_json(xyang.get(XYangKey.BASES))
    desc = def_schema.get(JsonSchemaKey.DESCRIPTION, "")
    ident = YangIdentityStmt(name=def_name, description=desc, bases=bases)
    _set_if_features_from_xyang(ident, xyang)
    _attach_invocations(ident, xyang)
    return ident


def _build_must_list(xyang: dict[str, Any]) -> list[YangMustStmt]:
    """Build list of YangMustStmt from x-yang must (list of {must, error-message, description})."""
    out = []
    for m in xyang.get(XYangKey.MUST) or []:
        if isinstance(m, dict):
            must = YangMustStmt(
                expression=m.get(XYangMustEntryKey.MUST, ""),
                error_message=m.get(XYangMustEntryKey.ERROR_MESSAGE, ""),
                description=m.get(JsonSchemaKey.DESCRIPTION, ""),
            )
            _bind_recorded(must, m)
            out.append(must)
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
            _attach_invocations(case_stmt, b_xyang if isinstance(b_xyang, dict) else None)
            cases.append(case_stmt)

    choice_stmt = YangChoiceStmt(
        name=choice_name,
        description=choice_description,
        mandatory=mandatory,
        cases=cases,
    )
    _set_if_features_from_xyang(choice_stmt, meta)
    _attach_invocations(choice_stmt, meta)
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
    _set_config_from_xyang(c, xyang)
    _attach_invocations(c, xyang)
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
    lst.unique = _unique_from_xyang(xyang, f"{parent_path}/{name}")
    when_stmt = _when_from_xyang(xyang)
    if when_stmt is not None:
        lst.when = when_stmt
    if JsonSchemaKey.MIN_ITEMS in schema and schema[JsonSchemaKey.MIN_ITEMS] is not None:
        lst.min_elements = int(schema[JsonSchemaKey.MIN_ITEMS])
    if JsonSchemaKey.MAX_ITEMS in schema and schema[JsonSchemaKey.MAX_ITEMS] is not None:
        lst.max_elements = int(schema[JsonSchemaKey.MAX_ITEMS])
    _set_if_features_from_xyang(lst, xyang)
    _set_config_from_xyang(lst, xyang)
    _attach_invocations(lst, xyang)
    return lst


def _unique_from_xyang(xyang: dict[str, Any], where: str) -> list[list[str]]:
    raw = xyang.get(XYangKey.UNIQUE)
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(
        isinstance(paths, list) and paths and all(isinstance(p, str) and p for p in paths) for paths in raw
    ):
        raise ValueError(f"x-yang 'unique' at {where} must be a list of non-empty lists of paths, got {raw!r}")
    return [list(paths) for paths in raw]


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
    if default is not None:
        schema_type = schema.get(JsonSchemaKey.TYPE)
        if schema_type == "boolean":
            if isinstance(default, bool):
                default = "true" if default else "false"
            elif isinstance(default, str):
                default = default.lower()
        elif schema_type == "integer" and isinstance(default, (int, float)):
            default = str(int(default))
        else:
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
    units = _units_from_xyang(xyang)
    if units:
        leaf.units = units
    _set_config_from_xyang(leaf, xyang)
    _attach_invocations(leaf, xyang)
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
    _attach_invocations(node, xyang)
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
        type_stmt = YangTypeStmt(name="string")
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
    units = _units_from_xyang(xyang)
    if units:
        ll.units = units
    _set_config_from_xyang(ll, xyang)
    _attach_invocations(ll, xyang)
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
        _attach_invocations(case_stmt, case_xyang)
        cases.append(case_stmt)
    choice_stmt = YangChoiceStmt(
        name=name, description=description, mandatory=mandatory, cases=cases
    )
    _set_if_features_from_xyang(choice_stmt, xyang)
    _set_config_from_xyang(choice_stmt, xyang)
    _attach_invocations(choice_stmt, xyang)
    choice_stmt.validate_case_unique_child_names()
    return choice_stmt


def _convert_io_block(
    schema: dict[str, Any],
    defs: dict[str, Any],
    parent_path: str,
    *,
    io_type: str,
) -> YangInputStmt | YangOutputStmt | None:
    """Convert RPC ``input`` / ``output`` JSON to AST."""
    xyang = _get_xyang(schema)
    if xyang.get(XYangKey.TYPE) != io_type:
        return None
    must_list = _build_must_list(xyang)
    description = schema.get(JsonSchemaKey.DESCRIPTION, "")
    child_statements: list[YangStatement] = []
    props_raw = schema.get(JsonSchemaKey.PROPERTIES) or {}
    block_required = set(schema.get(JsonSchemaKey.REQUIRED) or [])
    for child_name, child_val in props_raw.items():
        if not isinstance(child_val, dict):
            continue
        child = _convert_property(
            child_name,
            child_val,
            defs,
            f"{parent_path}/{child_name}",
            mandatory_override=child_name in block_required,
        )
        if child is not None:
            child_statements.append(child)
    if io_type == XYangTypeValue.INPUT:
        stmt = YangInputStmt(name=io_type, description=description, statements=child_statements)
    else:
        stmt = YangOutputStmt(name=io_type, description=description, statements=child_statements)
    stmt.must_statements = must_list
    when_stmt = _when_from_xyang(xyang)
    if when_stmt is not None:
        stmt.when = when_stmt
    _set_if_features_from_xyang(stmt, xyang)
    _attach_invocations(stmt, xyang)
    return stmt


def _convert_rpc(
    name: str,
    rpc_value: dict[str, Any],
    defs: dict[str, Any],
    cls: type[YangRpcStmt] = YangRpcStmt,
    kind: str = XYangTypeValue.RPC,
) -> YangRpcStmt | None:
    """Convert one ``x-yang.rpcs`` (or ``x-yang.actions``) entry to ``YangRpcStmt`` (``YangActionStmt``)."""
    xyang = _get_xyang(rpc_value)
    if xyang.get(XYangKey.TYPE) != kind:
        raise ValueError(f"{kind} '{name}' must have x-yang type '{kind}', got {xyang.get(XYangKey.TYPE)!r}")
    must_list = _build_must_list(xyang)
    statements: list[YangStatement] = []
    for io_key, io_type in (
        ("input", XYangTypeValue.INPUT),
        ("output", XYangTypeValue.OUTPUT),
    ):
        io_raw = rpc_value.get(io_key)
        if isinstance(io_raw, dict):
            io_stmt = _convert_io_block(io_raw, defs, f"/{name}/{io_key}", io_type=io_type)
            if io_stmt is not None:
                statements.append(io_stmt)
    rpc = cls(name=name, statements=statements)
    rpc.must_statements = must_list
    when_stmt = _when_from_xyang(xyang)
    if when_stmt is not None:
        rpc.when = when_stmt
    _set_if_features_from_xyang(rpc, xyang)
    _attach_invocations(rpc, xyang)
    return rpc


def _convert_property(
    name: str,
    prop_value: dict[str, Any],
    defs: dict[str, Any],
    parent_path: str,
    mandatory_override: bool | None = None,
) -> Any:
    """Convert one property. A ``module:name`` key is a node another module defines (augment)."""
    module_name, sep, local = name.partition(":")
    if not sep:
        stmt = _convert_property_local(name, prop_value, defs, parent_path, mandatory_override)
        return _attach_actions(stmt, prop_value, defs, parent_path)
    if not module_name or not local:
        raise ValueError(f"property name {name!r} must be 'name' or 'module:name'")
    stmt = _convert_property_local(local, prop_value, defs, parent_path, mandatory_override)
    if stmt is not None:
        stmt.defining_module = module_name
    return _attach_actions(stmt, prop_value, defs, parent_path)


def _attach_actions(stmt: Any, prop_value: dict[str, Any], defs: dict[str, Any], parent_path: str) -> Any:
    """Add the ``x-yang.actions`` of a container or list property as ``YangActionStmt`` children."""
    if not isinstance(stmt, (YangContainerStmt, YangListStmt)):
        return stmt
    _schema, xyang = _property_schema_and_xyang(prop_value, defs)
    actions = xyang.get(XYangKey.ACTIONS)
    if actions is None:
        return stmt
    if not isinstance(actions, dict):
        raise ValueError(f'x-yang "actions" at {parent_path} must be an object keyed by action name')
    for action_name, action_value in actions.items():
        if not isinstance(action_value, dict):
            raise ValueError(f"action '{action_name}' at {parent_path} must be an object")
        owner, colon, local = str(action_name).rpartition(":")
        action = _convert_rpc(local, action_value, defs, YangActionStmt, XYangTypeValue.ACTION)
        if colon:
            action.defining_module = owner
        stmt.statements.append(action)
    return stmt


def _convert_property_local(
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
    if is_string_number(node_type) and schema.get(JsonSchemaKey.TYPE) == "string":
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


def _bind_type_paths(type_stmt: Any, module: YangModule) -> None:
    if type_stmt is None:
        return
    path = getattr(type_stmt, "path", None)
    if path is not None and not getattr(path, "bound", False):
        bind_xpath_prefixes(path, module.resolve_prefix_to_module_name, path.to_string())
    for member in getattr(type_stmt, "types", None) or []:
        _bind_type_paths(member, module)


def _bind_xpath_prefixes(stmts: list[Any], module: YangModule) -> None:
    """Bind prefixed steps in every ``must``, ``when`` and leafref ``path`` without a recorded
    ``xpath-prefixes`` map to *module*'s own prefix."""
    for stmt in stmts:
        for must in getattr(stmt, "must_statements", None) or []:
            if not getattr(must, "prefixes_bound", False):
                must.bind_prefixes(module)
        when = getattr(stmt, "when", None)
        if when is not None and not getattr(when, "prefixes_bound", False):
            when.bind_prefixes(module)
        _bind_type_paths(getattr(stmt, "type", None), module)
        _bind_xpath_prefixes(stmt.statements, module)
        for case in getattr(stmt, "cases", None) or []:
            _bind_xpath_prefixes([case], module)


class _JsonParse:
    """Module and ``$defs`` while ``parse_json_schema`` rebuilds extension invocations."""

    def __init__(self, module: YangModule, defs: dict[str, Any]) -> None:
        self.module = module
        self.defs = defs


_PARSING: contextvars.ContextVar[_JsonParse] = contextvars.ContextVar("xyang_json_parse_extensions")


def _extension_from_json(name: str, raw: Any, module_name: str = "") -> YangExtensionStmt:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f'extension {name!r} must be an object, got {raw!r}')
    ext = YangExtensionStmt(name=name)
    argument = raw.get(XYangKey.ARGUMENT)
    if isinstance(argument, str) and argument:
        ext.argument_name = argument
    if XYangKey.YIN_ELEMENT in raw:
        yin = raw[XYangKey.YIN_ELEMENT]
        if not isinstance(yin, bool):
            raise ValueError(f'extension {name!r} "{XYangKey.YIN_ELEMENT}" must be a boolean')
        ext.argument_yin_element = yin
    description = raw.get(JsonSchemaKey.DESCRIPTION)
    if isinstance(description, str):
        ext.description = description
    reference = raw.get(XYangKey.REFERENCE)
    if isinstance(reference, str):
        ext.reference = reference
    if module_name:
        ensure_builtin_extensions_loaded()
        callback = get_extension_apply_callback(ExtensionIdentity(module_name=module_name, extension_name=name))
        if callback is not None:
            ext.apply_callback = callback
    return ext


def _load_extension_defs(module: YangModule, raw_xyang: dict[str, Any]) -> None:
    """Bind ``x-yang.extension`` as the module's extension definitions. No apply callbacks."""
    raw = raw_xyang.get(XYangKey.EXTENSION)
    if raw is None:
        return
    if not isinstance(raw, dict):
        raise ValueError(f'"{XYangKey.EXTENSION}" must map names to extension definitions, got {raw!r}')
    for name, body in raw.items():
        module.extensions[str(name)] = _extension_from_json(str(name), body, module.name)


def _invocation_from_json(raw: Any) -> YangExtensionInvocationStmt:
    """One ``x-yang.extensions`` entry, including a nested body. Not re-applied."""
    if not isinstance(raw, dict) or not isinstance(raw.get(JsonSchemaKey.NAME), str) or ":" not in raw[JsonSchemaKey.NAME]:
        raise ValueError(f'extension invocation must be an object with "name" of the form "prefix:ext", got {raw!r}')
    ctx = _PARSING.get(None)
    if ctx is None:
        raise ValueError("extension invocations require parse_json_schema")
    name = raw[JsonSchemaKey.NAME]
    prefix, _, ext_name = name.partition(":")
    if prefix == ctx.module.own_prefix_stripped():
        owner: YangModule | None = ctx.module
    else:
        owner = ctx.module.import_prefixes.get(prefix)
    if owner is None:
        raise ValueError(f"extension invocation {name!r}: unknown prefix {prefix!r}")
    ext = owner.get_extension(ext_name)
    if ext is None:
        raise ValueError(f"extension invocation {name!r}: unknown extension {ext_name!r} in module {owner.name!r}")
    argument = raw[XYangKey.ARGUMENT] if XYangKey.ARGUMENT in raw else None
    if argument is not None and not isinstance(argument, str):
        raise ValueError(f"extension invocation {name!r}: argument must be a string")
    inv = YangExtensionInvocationStmt(
        name=name,
        prefix=prefix,
        resolved_module=owner,
        resolved_extension=ext,
        argument=argument,
        description=raw.get(JsonSchemaKey.DESCRIPTION) or "",
        reference=raw.get(XYangKey.REFERENCE) or "",
    )
    _set_if_features_from_xyang(inv, raw)
    when_stmt = _when_from_xyang(raw)
    if when_stmt is not None:
        inv.when = when_stmt
    inv.must_statements = _build_must_list(raw)
    if XYangKey.CONFIG in raw and isinstance(raw[XYangKey.CONFIG], bool):
        inv.config = raw[XYangKey.CONFIG]
    body = raw.get(XYangKey.BODY) or []
    if not isinstance(body, list):
        raise ValueError(f'extension invocation {name!r}: "{XYangKey.BODY}" must be a list')
    for item in body:
        if not isinstance(item, dict):
            raise ValueError(f"extension invocation {name!r}: body entry must be an object")
        if XYangKey.EXTENSION in item:
            inv.statements.append(_invocation_from_json(item[XYangKey.EXTENSION]))
            continue
        node = item.get("node")
        schema = item.get("schema")
        if isinstance(node, str) and isinstance(schema, dict):
            child = _convert_property(node, schema, ctx.defs, f"/{node}")
            if child is None:
                raise ValueError(f"extension invocation {name!r}: body node {node!r} is not a schema node")
            inv.statements.append(child)
            continue
        raise ValueError(f"extension invocation {name!r}: body entry must be an extension or a node")
    return inv


def _attach_invocations(stmt: Any, xyang: dict[str, Any] | None) -> None:
    """Append ``x-yang.extensions`` onto *stmt*, in the order they were exported."""
    if not isinstance(xyang, dict):
        return
    raw = xyang.get(XYangKey.EXTENSIONS)
    if not raw:
        return
    if not isinstance(raw, list):
        raise ValueError(f'"{XYangKey.EXTENSIONS}" must be a list of invocations, got {raw!r}')
    for item in raw:
        stmt.statements.append(_invocation_from_json(item))


def _module_from_import_stub(key: str, raw: Any) -> YangModule:
    """Rebuild one ``x-yang.imports`` entry: an imported module reduced to its identities."""
    if not isinstance(raw, dict) or not all(isinstance(raw.get(k), str) for k in (XYangKey.MODULE, XYangKey.PREFIX)):
        raise ValueError(f'"{XYangKey.IMPORTS}" entry {key!r} must be an object with "module" and "prefix"')
    stub = YangModule(
        name=raw[XYangKey.MODULE],
        namespace=raw.get(XYangKey.NAMESPACE, ""),
        prefix=raw[XYangKey.PREFIX],
    )
    _load_imports(stub, raw)
    identities = raw.get(XYangKey.IDENTITIES) or {}
    if not isinstance(identities, dict):
        raise ValueError(f'"{XYangKey.IDENTITIES}" of import {key!r} must be an object')
    for name, def_schema in identities.items():
        ident = _build_identity(name, def_schema) if isinstance(def_schema, dict) else None
        if ident is None:
            raise ValueError(f'identity {name!r} of import {key!r} is not an identity definition')
        stub.identities[name] = ident
    _load_extension_defs(stub, raw)
    _load_features(stub, raw)
    _load_stub_invocations(stub, raw)
    return stub


def _load_features(module: YangModule, raw_xyang: dict[str, Any]) -> None:
    """Bind ``x-yang.features`` so ``if-feature`` matches the module that was exported."""
    raw = raw_xyang.get(XYangKey.FEATURES)
    if raw is None:
        return
    if not isinstance(raw, dict):
        raise ValueError(f'"{XYangKey.FEATURES}" must map feature names to objects, got {raw!r}')
    for name, body in raw.items():
        module.features.add(str(name))
        if not isinstance(body, dict):
            raise ValueError(f'feature {name!r} must be an object, got {body!r}')
        guards = body.get(XYangKey.IF_FEATURES)
        if guards:
            if not isinstance(guards, list) or not all(isinstance(item, str) for item in guards):
                raise ValueError(f'feature {name!r} "{XYangKey.IF_FEATURES}" must be a list of strings')
            module.feature_if_features[str(name)] = list(guards)


def _load_stub_invocations(stub: YangModule, raw: dict[str, Any]) -> None:
    """Rebuild ``sx:structure`` nodes carried on an import stub and index them."""
    invocations = raw.get(XYangKey.EXTENSIONS)
    if not invocations:
        return
    if not isinstance(invocations, list):
        raise ValueError(f'"{XYangKey.EXTENSIONS}" of import {stub.name!r} must be a list')
    token = _PARSING.set(_JsonParse(stub, {}))
    try:
        for item in invocations:
            stub.statements.append(_invocation_from_json(item))
    finally:
        _PARSING.reset(token)
    apply_extension_invocations(stub)


def _load_imports(module: YangModule, raw_xyang: dict[str, Any]) -> None:
    """Bind ``x-yang.imports`` as the module's import prefixes, so identity bases resolve without files."""
    imports = raw_xyang.get(XYangKey.IMPORTS)
    if imports is None:
        return
    if not isinstance(imports, dict):
        raise ValueError(f'"{XYangKey.IMPORTS}" must map keys to imported modules, got {imports!r}')
    for key, raw in imports.items():
        module.import_prefixes[key] = _module_from_import_stub(key, raw)


def parse_json_schema(source: str | Path | dict[str, Any]) -> YangModule:
    """
    Build a YangModule (and nested AST nodes from xyang.ast) from a JSON Schema
    with x-yang annotations.

    Args:
        source: Path to a .json file, or JSON string, or parsed dict.

    Returns:
        YangModule with .statements (one per root JSON Schema property, e.g.
        ``data-model`` or ``program``), and .typedefs.

    Raises:
        ValueError: The root schema, or a root ``properties`` member, has no
        ``x-yang`` object. Plain JSON Schema is not imported.
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

    root_xyang = data.get(JsonSchemaKey.X_YANG)
    if not isinstance(root_xyang, dict):
        raise ValueError(
            'JSON Schema has no root "x-yang" annotation; '
            'xYang needs a .yang.json produced by "xyang convert" '
            "(see design/json-schema-xyang-profile.md)"
        )
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

    _load_imports(module, root_xyang)
    _load_extension_defs(module, root_xyang)
    _load_features(module, root_xyang)
    token = _PARSING.set(_JsonParse(module, defs))
    try:
        _parse_json_schema_body(module, data, root_xyang, defs)
    finally:
        _PARSING.reset(token)
    return module


def _parse_json_schema_body(
    module: YangModule,
    data: dict[str, Any],
    root_xyang: dict[str, Any],
    defs: dict[str, Any],
) -> None:
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
        if not isinstance(root_val.get(JsonSchemaKey.X_YANG), dict):
            raise ValueError(
                f'JSON Schema property "{root_name}" has no "x-yang" annotation'
            )
        stmt = _convert_property(root_name, root_val, defs, f"/{root_name}")
        if stmt is not None:
            module.statements.append(stmt)

    rpcs_raw = root_xyang.get(XYangKey.RPCS) or {}
    if isinstance(rpcs_raw, dict):
        for rpc_name, rpc_val in rpcs_raw.items():
            if not isinstance(rpc_val, dict):
                continue
            rpc_stmt = _convert_rpc(str(rpc_name), rpc_val, defs)
            if rpc_stmt is not None:
                module.statements.append(rpc_stmt)

    _attach_invocations(module, root_xyang)
    # Index ``sx:structure`` and apply a cross-module ``sx:augment-structure`` once.
    # A same-module augment is already merged into the structure body.
    apply_extension_invocations(module)

    _bind_xpath_prefixes(module.statements, module)
    for typedef in module.typedefs.values():
        _bind_type_paths(getattr(typedef, "type", None), module)
