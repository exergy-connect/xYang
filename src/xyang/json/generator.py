"""
Generate a JSON Schema file (schema.yang.json) from a YANG AST (YangModule).

Produces JSON Schema with x-yang annotations compatible with the json/parser
so that parse_json_schema(generate_json_schema(module)) round-trips where supported.
"""

from __future__ import annotations

import contextvars
import json
import re
from copy import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from ..ast import (
    YangAnydataStmt,
    YangAnyxmlStmt,
    YangCaseStmt,
    YangChoiceStmt,
    YangContainerStmt,
    YangAugmentStmt,
    YangDeviationStmt,
    YangExtensionStmt,
    YangExtensionInvocationStmt,
    YangGroupingStmt,
    YangIdentityStmt,
    YangInputStmt,
    YangLeafListStmt,
    YangLeafStmt,
    YangListStmt,
    YangMustStmt,
    YangOutputStmt,
    YangRefineStmt,
    YangRpcStmt,
    YangActionStmt,
    YangStatement,
    YangTypeStmt,
    YangTypedefStmt,
    YangUsesStmt,
    YangWhenStmt,
)
from ..augment_expand import apply_augmentations, apply_deviations
from ..errors import YangExportError
from ..ext.capabilities import apply_extension_invocations
from ..ext.rfc8791.structure_expand import FOREIGN_AUGMENTS, FOREIGN_SLOTS, _STRUCTURE_INDEX_KEY
from ..identity_graph import (
    IdentityPair,
    descendant_closure,
    identity_ancestor_closure,
    qualified_identity_name,
    resolve_identity_base_ref,
)
from ..identifier_ref import coerce_identifier_ref, format_identifier_ref, parse_absolute_schema_path
from ..module import YangModule
from ..refine_expand import copy_yang_statement
from ..uses_expand import ExpandUsesContext, expand_uses_in_statements
from ..xpath.ast import PathNode
from ..xpath.schema_nav import SchemaNav
from ..xpath.utils import coerce_default_value

from ..types.registry import type_to_schema
from .schema_keys import (
    JsonSchemaKey,
    XYangKey,
    XYangMustEntryKey,
    XYangTypeValue,
    XYangWhenEntryKey,
    json_schema_defs_uri,
)

def _with_description(out: dict[str, Any], text: Any) -> None:
    """Emit ``description`` only when *text* is a non-empty string."""
    if isinstance(text, str) and text != "":
        out[JsonSchemaKey.DESCRIPTION] = text


_ANY_JSON_INSTANCE_SCHEMA: dict[str, Any] = {
    JsonSchemaKey.TYPE: [
        "array",
        "boolean",
        "integer",
        "null",
        "number",
        "object",
        "string",
    ],
}


def _try_int_literal(default: Any) -> int | None:
    if isinstance(default, int) and not isinstance(default, bool):
        return default
    if isinstance(default, str):
        if default.isdigit():
            return int(default)
        if default.startswith("-") and default[1:].isdigit():
            return int(default)
    return None


def _json_schema_default_value(
    default: Any,
    *,
    yang_type_name: str | None = None,
    json_schema_type: str | None = None,
) -> Any:
    """Map YANG AST default values to JSON Schema literal types."""
    if default is None:
        return None
    type_name = yang_type_name or json_schema_type
    if type_name == "boolean" or json_schema_type == "boolean":
        if default is True or (isinstance(default, str) and default.lower() == "true"):
            return True
        if default is False or (isinstance(default, str) and default.lower() == "false"):
            return False
    if yang_type_name == "union":
        numeric = _try_int_literal(default)
        if numeric is not None:
            return numeric
        return default
    coerce_type = yang_type_name
    if json_schema_type == "integer" and coerce_type in (None, "integer"):
        coerce_type = "int32"
    if json_schema_type == "number" and coerce_type is None:
        coerce_type = "decimal64"
    coerced = coerce_default_value(default, coerce_type)
    if coerced is not default:
        return coerced
    if json_schema_type == "integer":
        numeric = _try_int_literal(default)
        if numeric is not None:
            return numeric
    return default


def _format_bases_for_json(bases: list[Any]) -> list[str]:
    out: list[str] = []
    for item in bases:
        ref = coerce_identifier_ref(item)
        if ref is not None:
            out.append(format_identifier_ref(ref))
    return out


@dataclass
class _IdentityExport:
    """Identity bases one export resolved outside the exported module (see ``x-yang.imports``)."""

    root: YangModule
    used: list[IdentityPair] = field(default_factory=list)


_EXPORT: contextvars.ContextVar[_IdentityExport] = contextvars.ContextVar("xyang_identity_export")


def _import_key(root: YangModule, module: YangModule) -> str:
    """Key of *module* in the root ``x-yang.imports``: the prefix that imports it, else its name."""
    for prefix, imported in root.import_prefixes.items():
        if imported is module or imported.name == module.name:
            return prefix
    if module.name in root.import_prefixes or module.name == root.own_prefix_stripped():
        raise YangExportError(
            f"cannot export identities of module {module.name!r}: the name is also a prefix of module {root.name!r}"
        )
    return module.name


def identity_base_for_json(base: Any, scope: YangModule, module: YangModule) -> tuple[str, str]:
    """``(base, $ref)`` of one identity ``base`` written in *scope*, re-expressed in *module*'s scope.

    A base of the exported module is its bare name (``#/$defs/name``). A base of another module is
    ``key:name`` (``#/x-yang/imports/key/identities/name``), and the module is recorded for
    ``x-yang.imports``. A base that does not resolve where it is written cannot be exported.
    """
    ref = coerce_identifier_ref(base)
    label = format_identifier_ref(ref) if ref is not None else str(base)
    pair = resolve_identity_base_ref(scope, ref) if ref is not None else None
    if pair is None:
        raise YangExportError(
            f"cannot export identity base {label!r}: it does not resolve in module {scope.name!r}"
        )
    owner, name = pair
    if owner.name == module.name:
        return name, f"#/{JsonSchemaKey.DEFS}/{name}"
    export = _EXPORT.get(None)
    if export is None:
        raise YangExportError(f"cannot export identity base {label!r} outside generate_json_schema")
    export.used.append(pair)
    key = _import_key(export.root, owner)
    return f"{key}:{name}", f"#/{JsonSchemaKey.X_YANG}/{XYangKey.IMPORTS}/{key}/{XYangKey.IDENTITIES}/{name}"


def _identity_stub(module: YangModule, names: dict[str, set[str]]) -> dict[str, Any]:
    """``x-yang.imports`` entry: *module*'s identities in *names* and the modules their bases name."""
    identities: dict[str, Any] = {}
    imports: dict[str, Any] = {}
    mine = names[module.name]
    for name in sorted(mine):
        identity = module.identities[name]
        identities[name] = _identity_to_def(name, identity, module, only=mine)
        for base in identity.bases:
            ref = coerce_identifier_ref(base)
            pair = resolve_identity_base_ref(module, ref) if ref is not None else None
            if ref is None or pair is None:
                raise YangExportError(
                    f"cannot export identity {name!r} of module {module.name!r}: base {base!r} does not resolve there"
                )
            if pair[0].name != module.name:
                assert ref.prefix is not None
                imports[ref.prefix] = _identity_stub(pair[0], names)
    stub: dict[str, Any] = {
        XYangKey.MODULE: module.name,
        XYangKey.NAMESPACE: module.namespace or "",
        XYangKey.PREFIX: module.prefix or "",
    }
    if imports:
        stub[XYangKey.IMPORTS] = dict(sorted(imports.items()))
    stub[XYangKey.IDENTITIES] = identities
    return stub


def _imports_for_json(root: YangModule, used: list[IdentityPair]) -> dict[str, Any]:
    """Imported identities the exported module needs, so the JSON form resolves them without ``import``.

    Needed: every identity an ``identityref`` base names, the bases of the module's own identities, and
    the identities of a directly imported module that derive from one of those (an instance value may
    name them), each with its bases. Nothing else of an import is carried.
    """
    used_keys = {(module.name, name) for module, name in used}
    for name, identity in root.identities.items():
        for base in identity.bases:
            ref = coerce_identifier_ref(base)
            if resolve_identity_base_ref(root, base) is None:
                raise YangExportError(
                    f"cannot export identity {name!r}: base {(format_identifier_ref(ref) if ref is not None else str(base))!r} "
                    f"does not resolve in module {root.name!r}"
                )
    names: dict[str, set[str]] = {}

    def need(pairs: list[IdentityPair]) -> None:
        for module, name in pairs:
            names.setdefault(module.name, set()).add(name)

    candidates = [(root, name) for name in root.identities]
    candidates += [(m, name) for m in root.import_prefixes.values() for name in m.identities]
    for module, name in candidates:
        closure = identity_ancestor_closure(module, name)
        if module is root or any((m.name, n) in used_keys for m, n in closure):
            need(closure)
    need(used)
    names.pop(root.name, None)
    out: dict[str, Any] = {}
    for module in [*root.import_prefixes.values(), *(m for m, _ in used)]:
        if module.name in names:
            out[_import_key(root, module)] = _identity_stub(module, names)
    return dict(sorted(out.items()))


def _leaf_yang_type_name(
    type_stmt: YangTypeStmt | None,
    typedef_names: set[str],
    module: YangModule,
) -> str | None:
    if type_stmt is None:
        return None
    if type_stmt.name in typedef_names:
        td = module.typedefs.get(type_stmt.name)
        if isinstance(td, YangTypedefStmt) and td.type is not None:
            return td.type.name
        return None
    return type_stmt.name


def _mandatory_schema_child(stmt: YangStatement) -> bool:
    """Leaf / anydata / anyxml may appear in container ``required``."""
    return isinstance(stmt, (YangLeafStmt, YangAnydataStmt, YangAnyxmlStmt)) and bool(
        getattr(stmt, "mandatory", False)
    )


def _if_features_for_xyang(obj: Any) -> list[str] | None:
    """Return ``if-features`` array for x-yang, or None when empty."""
    raw = getattr(obj, "if_features", None) or []
    if not raw:
        return None
    return list(raw)


def _bits_space_separated_pattern(bit_names: list[str]) -> str:
    """JSON Schema ``pattern`` for a YANG ``bits`` value: space-separated bit names (any order).

    Matches the token alphabet only; duplicate tokens are not excluded (YANG validation
    still rejects duplicates). Names are longest-first in the alternation.
    """
    if not bit_names:
        return "^$"
    escaped = sorted((re.escape(n) for n in bit_names), key=len, reverse=True)
    alt = "|".join(escaped)
    return rf"^$|^(?:{alt})(?:\s+(?:{alt}))*$"


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
            s, (YangLeafStmt, YangLeafListStmt, YangAnydataStmt, YangAnyxmlStmt)
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
    if not isinstance(node, YangStatement):
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
        nxt = SchemaNav.child(current, seg.step)
        if nxt is None:
            return None
        current = nxt

    return current if isinstance(current, YangLeafStmt) else None


def _merge_units_into_schema(schema: dict[str, Any], units: str) -> None:
    """Attach RFC 7950 ``units`` to ``x-yang`` on a JSON Schema fragment (in place)."""
    if not units:
        return
    xy = dict(schema.get(JsonSchemaKey.X_YANG) or {})
    xy[XYangKey.UNITS] = units
    schema[JsonSchemaKey.X_YANG] = xy


def _type_to_schema(
    type_stmt: YangTypeStmt | None,
    typedef_names: set[str],
    module: YangModule | None = None,
    leafref_anchor: YangStatement | YangModule | None = None,
) -> dict[str, Any]:
    """Build JSON Schema for a type. Uses $ref for typedef names when in typedef_names."""
    if type_stmt is None:
        return {JsonSchemaKey.TYPE: "string"}
    out = _type_to_schema_impl(type_stmt, typedef_names, module, leafref_anchor)
    _merge_units_into_schema(out, type_stmt.units)
    return out


def _type_to_schema_impl(
    type_stmt: YangTypeStmt,
    typedef_names: set[str],
    module: YangModule | None,
    leafref_anchor: YangStatement | YangModule | None,
) -> dict[str, Any]:
    """JSON Schema for one type. Built-in encodings come from the type registry."""
    return type_to_schema(type_stmt, typedef_names, module, leafref_anchor)


def _must_to_json(must: YangMustStmt) -> dict[str, Any]:
    """Convert YangMustStmt to x-yang must entry."""
    out = {
        XYangMustEntryKey.MUST: must.expression,
        XYangMustEntryKey.ERROR_MESSAGE: must.error_message or "",
    }
    if must.error_app_tag:
        out[XYangMustEntryKey.ERROR_APP_TAG] = must.error_app_tag
    _with_xpath_prefixes(out, must.ast)
    _with_description(out, must.description)
    return out


def _with_xpath_prefixes(out: dict[str, Any], ast: Any) -> None:
    """Record the module each prefixed step is bound to; the JSON form carries no imports."""
    from ..xpath.parser import xpath_prefix_map

    bound = xpath_prefix_map(ast)
    if bound:
        out[XYangKey.XPATH_PREFIXES] = dict(sorted(bound.items()))


def _when_to_xyang_json(when: YangWhenStmt) -> dict[str, Any]:
    """Serialize ``when`` as object: ``condition`` (required) and optional ``description``."""
    out: dict[str, Any] = {XYangWhenEntryKey.CONDITION: when.expression}
    _with_xpath_prefixes(out, when.ast)
    if when.description and when.description.strip():
        out[JsonSchemaKey.DESCRIPTION] = when.description
    if getattr(when, "evaluate_with_parent_context", False):
        out["evaluate-with-parent-context"] = True
    return out


def _explicit_config(stmt: YangStatement) -> bool | None:
    """Return explicit ``config`` from a data node, or ``None`` if unset (inherit)."""
    return getattr(stmt, "config", None)


def _build_xyang(
    node_type: str,
    key: str | None = None,
    must_list: list[YangMustStmt] | None = None,
    when_stmt: YangWhenStmt | None = None,
    presence: str | None = None,
    *,
    mandatory: bool | None = None,
    config: bool | None = None,
    if_features: list[str] | None = None,
    units: str | None = None,
) -> dict[str, Any]:
    """Build x-yang object for a node."""
    xyang: dict[str, Any] = {XYangKey.TYPE: node_type}
    if key:
        xyang[XYangKey.KEY] = key
    if must_list:
        xyang[XYangKey.MUST] = [_must_to_json(m) for m in must_list]
    if when_stmt is not None and when_stmt.expression:
        xyang[XYangKey.WHEN] = _when_to_xyang_json(when_stmt)
    if presence:
        xyang[XYangKey.PRESENCE] = presence
    if mandatory is True:
        xyang[XYangKey.MANDATORY] = True
    if config is not None:
        xyang[XYangKey.CONFIG] = config
    if if_features:
        xyang[XYangKey.IF_FEATURES] = list(if_features)
    if units:
        xyang[XYangKey.UNITS] = units
    return xyang


@dataclass
class _ExtensionUse:
    """Imported extensions one export invoked (see ``x-yang.imports``)."""

    root: YangModule
    used: list[tuple[YangModule, str]] = field(default_factory=list)


_EXT_USED: contextvars.ContextVar[_ExtensionUse] = contextvars.ContextVar("xyang_extension_export")

# RFC 8791 is exported and re-applied (#164). Any other extension with an apply
# callback still has no JSON form, so export fails instead of dropping it.
_RFC8791 = "ietf-yang-structure-ext"
_RFC8791_EXPORTED = frozenset({"structure", "augment-structure"})


def _extension_def_json(ext: YangExtensionStmt) -> dict[str, Any]:
    """One extension definition: argument, yin-element, description, reference. Absent fields stay absent."""
    out: dict[str, Any] = {}
    if ext.argument_name:
        out[XYangKey.ARGUMENT] = ext.argument_name
    if ext.argument_yin_element is not None:
        out[XYangKey.YIN_ELEMENT] = ext.argument_yin_element
    if ext.description:
        out[JsonSchemaKey.DESCRIPTION] = ext.description
    if ext.reference:
        out[XYangKey.REFERENCE] = ext.reference
    return out


def _is_rfc8791(inv: YangExtensionInvocationStmt, name: str) -> bool:
    owner = inv.resolved_module
    ext = inv.resolved_extension
    return owner is not None and owner.name == _RFC8791 and ext is not None and ext.name == name


def _reject_semantic_extension(inv: YangExtensionInvocationStmt) -> None:
    """An extension with an apply callback and no JSON form fails the export.

    RFC 8791 ``structure`` and ``augment-structure`` round-trip (#164). Anything else
    that is applied at parse time is not dropped.
    """
    ext = inv.resolved_extension
    owner = inv.resolved_module
    if owner is not None and owner.name == _RFC8791 and ext is not None and ext.name in _RFC8791_EXPORTED:
        return
    if ext is None or ext.apply_callback is None:
        return
    raise YangExportError(
        f"cannot export extension invocation {inv.name!r}: "
        f"extension {owner.name}:{ext.name} is applied when the module is parsed and is not "
        f"re-applied when the native JSON form is loaded"
    )


def _record_imported_extension(inv: YangExtensionInvocationStmt) -> None:
    """An extension defined in another module travels on that module's ``x-yang.imports`` stub."""
    export = _EXT_USED.get(None)
    if export is None:
        raise YangExportError(f"cannot export extension invocation {inv.name!r} outside generate_json_schema")
    owner = inv.resolved_module
    if owner.name == export.root.name:
        return
    pair = (owner, inv.resolved_extension.name)
    if pair not in export.used:
        export.used.append(pair)


def _one_extension_invocation(
    inv: YangExtensionInvocationStmt,
    typedef_names: set[str],
    module: YangModule,
) -> dict[str, Any]:
    """One invocation: ``{name: prefix:ext, argument?, ...}`` plus a nested body, in source order."""
    _reject_semantic_extension(inv)
    _record_imported_extension(inv)
    out: dict[str, Any] = {JsonSchemaKey.NAME: inv.name}
    if inv.argument is not None:
        out[XYangKey.ARGUMENT] = inv.argument
    if inv.description:
        out[JsonSchemaKey.DESCRIPTION] = inv.description
    if inv.reference:
        out[XYangKey.REFERENCE] = inv.reference
    features = _if_features_for_xyang(inv)
    if features:
        out[XYangKey.IF_FEATURES] = features
    if inv.when is not None and inv.when.expression:
        out[XYangKey.WHEN] = _when_to_xyang_json(inv.when)
    if inv.must_statements:
        out[XYangKey.MUST] = [_must_to_json(m) for m in inv.must_statements]
    config = _explicit_config(inv)
    if config is not None:
        out[XYangKey.CONFIG] = config
    body = _extension_body_json(inv, typedef_names, module)
    if body:
        out[XYangKey.BODY] = body
    return out


def _extension_body_json(
    inv: YangExtensionInvocationStmt,
    typedef_names: set[str],
    module: YangModule,
) -> list[dict[str, Any]]:
    """Nested statements of *inv*, kept in source order. Anything else fails the export."""
    body: list[dict[str, Any]] = []
    for stmt in inv.statements:
        if isinstance(stmt, YangExtensionInvocationStmt):
            body.append({XYangKey.EXTENSION: _one_extension_invocation(stmt, typedef_names, module)})
            continue
        if isinstance(
            stmt,
            (
                YangContainerStmt,
                YangListStmt,
                YangLeafStmt,
                YangLeafListStmt,
                YangChoiceStmt,
                YangAnydataStmt,
                YangAnyxmlStmt,
            ),
        ):
            prop = _statement_to_property(stmt, typedef_names, module, parent=inv)
            if prop is None:
                raise YangExportError(
                    f"cannot export extension invocation {inv.name!r}: "
                    f"nested statement {stmt.name!r} is not representable in the native JSON form"
                )
            body.append({"node": _property_key(stmt, module), "schema": prop})
            continue
        kind = type(stmt).__name__
        raise YangExportError(
            f"cannot export extension invocation {inv.name!r}: "
            f"nested statement {kind} {getattr(stmt, 'name', '')!r} is not representable in the native JSON form"
        )
    return body


def _extension_invocations_json(
    statements: list[YangStatement],
    typedef_names: set[str],
    module: YangModule,
) -> list[dict[str, Any]]:
    """Invocations that are direct children of one node, in source order."""
    return [
        _one_extension_invocation(stmt, typedef_names, module)
        for stmt in statements
        if isinstance(stmt, YangExtensionInvocationStmt)
    ]


def _stamp_extensions(
    xyang: dict[str, Any],
    statements: list[YangStatement],
    typedef_names: set[str],
    module: YangModule,
) -> None:
    """Attach ``x-yang.extensions`` when *statements* invokes an extension."""
    invocations = _extension_invocations_json(statements, typedef_names, module)
    if invocations:
        xyang[XYangKey.EXTENSIONS] = invocations


def _local_extension_defs(module: YangModule) -> dict[str, Any]:
    """This module's extension definitions, in source order."""
    out: dict[str, Any] = {}
    for name, ext in module.extensions.items():
        if isinstance(ext, YangExtensionStmt):
            out[name] = _extension_def_json(ext)
    return out


def _merge_extension_imports(
    root: YangModule,
    imports: dict[str, Any],
    used: list[tuple[YangModule, str]],
) -> dict[str, Any]:
    """Add invoked imported extensions to the ``x-yang.imports`` stubs identities already use."""
    by_owner: dict[str, tuple[YangModule, list[str]]] = {}
    for owner, name in used:
        _owner, names = by_owner.setdefault(owner.name, (owner, []))
        if name not in names:
            names.append(name)
    for owner, names in by_owner.values():
        key = _import_key(root, owner)
        stub: dict[str, Any] | None = imports.get(key)
        if stub is None:
            stub = {
                XYangKey.MODULE: owner.name,
                XYangKey.NAMESPACE: owner.namespace or "",
                XYangKey.PREFIX: owner.prefix or "",
            }
            imports[key] = stub
        ext_map: dict[str, Any] = {}
        for name in sorted(names):
            ext = owner.extensions.get(name)
            if not isinstance(ext, YangExtensionStmt):
                raise YangExportError(
                    f"cannot export extension {owner.name}:{name}: the extension definition is not in that module"
                )
            ext_map[name] = _extension_def_json(ext)
        stub[XYangKey.EXTENSION] = ext_map
    return dict(sorted(imports.items()))


def _find_extension_invocation(stmt: YangStatement) -> YangExtensionInvocationStmt | None:
    if isinstance(stmt, YangExtensionInvocationStmt):
        return stmt
    for child in stmt.statements:
        found = _find_extension_invocation(child)
        if found is not None:
            return found
    if isinstance(stmt, YangChoiceStmt):
        for case in stmt.cases:
            found = _find_extension_invocation(case)
            if found is not None:
                return found
    return None


def _placement_node(stmt: YangStatement) -> bool:
    """A node the native JSON form already carries, so an invocation on it has a place."""
    return isinstance(
        stmt,
        (
            YangContainerStmt,
            YangListStmt,
            YangLeafStmt,
            YangLeafListStmt,
            YangChoiceStmt,
            YangCaseStmt,
            YangAnydataStmt,
            YangAnyxmlStmt,
            YangRpcStmt,
            YangTypedefStmt,
            YangIdentityStmt,
        ),
    )


def _assert_extensions_placed(module: YangModule) -> None:
    """Fail when an invocation sits on a construct the form does not carry. Groupings are expanded."""

    def walk(owner: YangStatement, placed: bool) -> None:
        for child in owner.statements:
            if isinstance(child, YangExtensionInvocationStmt):
                _reject_semantic_extension(child)
                if not placed:
                    raise YangExportError(
                        f"cannot export extension invocation {child.name!r}: "
                        f"it is on {type(owner).__name__} {getattr(owner, 'name', '')!r}, "
                        f"which the native JSON form does not carry"
                    )
                walk(child, True)
                continue
            if isinstance(child, (YangGroupingStmt, YangExtensionStmt)):
                continue
            if isinstance(child, YangUsesStmt):
                found = _find_extension_invocation(child)
                if found is not None:
                    raise YangExportError(
                        f"cannot export extension invocation {found.name!r}: "
                        f"it is inside uses {child.grouping_qname()!r}, which the native JSON form does not carry"
                    )
                continue
            walk(child, _placement_node(child))
        if isinstance(owner, YangChoiceStmt):
            for case in owner.cases:
                walk(case, True)

    for stmt in module.statements:
        if isinstance(stmt, YangExtensionInvocationStmt):
            _reject_semantic_extension(stmt)
            walk(stmt, True)
            continue
        if isinstance(stmt, (YangGroupingStmt, YangExtensionStmt)):
            continue
        if isinstance(stmt, YangUsesStmt):
            found = _find_extension_invocation(stmt)
            if found is not None:
                raise YangExportError(
                    f"cannot export extension invocation {found.name!r}: "
                    f"it is inside uses {stmt.grouping_qname()!r}, which the native JSON form does not carry"
                )
            continue
        walk(stmt, _placement_node(stmt))
    for typedef in module.typedefs.values():
        if isinstance(typedef, YangTypedefStmt):
            walk(typedef, True)
    for identity in module.identities.values():
        if isinstance(identity, YangIdentityStmt):
            walk(identity, True)


def _copy_statement(stmt: YangStatement) -> YangStatement:
    """Deep-copy a statement subtree for uses expansion."""
    return copy_yang_statement(stmt)


def _expand_uses_for_json(
    statements: list[YangStatement], module: YangModule
) -> list[YangStatement]:
    """Expand ``uses`` on a deep-copied subtree so the module AST is not mutated."""
    return expand_uses_in_statements(
        [_copy_statement(s) for s in statements],
        ctx=ExpandUsesContext(module=module),
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
        merged_branch: dict[str, Any] = {
            JsonSchemaKey.TYPE: "object",
            JsonSchemaKey.PROPERTIES: {**base_props, **bp},
            JsonSchemaKey.REQUIRED: sorted(set(base_required) | set(br)),
            JsonSchemaKey.ADDITIONAL_PROPERTIES: False,
        }
        b_desc = branch.get(JsonSchemaKey.DESCRIPTION)
        if isinstance(b_desc, str) and b_desc:
            merged_branch[JsonSchemaKey.DESCRIPTION] = b_desc
        b_xy = branch.get(JsonSchemaKey.X_YANG)
        if isinstance(b_xy, dict) and b_xy:
            merged_branch[JsonSchemaKey.X_YANG] = dict(b_xy)
        merged.append(merged_branch)
    return merged


def _choice_meta_xyang(
    choice_stmt: YangChoiceStmt,
    typedef_names: set[str],
    module: YangModule,
) -> dict[str, Any]:
    """x-yang.choice metadata for hoisted (sibling-less or merged) choices."""
    meta: dict[str, Any] = {JsonSchemaKey.NAME: choice_stmt.name}
    _with_description(meta, choice_stmt.description)
    meta[XYangKey.MANDATORY] = bool(getattr(choice_stmt, "mandatory", False))
    ff = _if_features_for_xyang(choice_stmt)
    if ff:
        meta[XYangKey.IF_FEATURES] = ff
    cfg = _explicit_config(choice_stmt)
    if cfg is not None:
        meta[XYangKey.CONFIG] = cfg
    _stamp_extensions(meta, choice_stmt.statements, typedef_names, module)
    return meta


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
    case_entries: list[tuple[YangCaseStmt, dict[str, Any], list[str]]] = []
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
                case_props[_property_key(s, module)] = child_prop
                case_keys.append(_property_key(s, module))
        if case_keys:
            case_entries.append((case, case_props, case_keys))
    out: dict[str, Any] = {}
    _with_description(out, choice_stmt.description)
    mandatory = getattr(choice_stmt, "mandatory", False)
    case_branch = []
    for case_st, cp, keys in case_entries:
        case_xy: dict[str, Any] = {JsonSchemaKey.NAME: case_st.name}
        ff = _if_features_for_xyang(case_st)
        if ff:
            case_xy[XYangKey.IF_FEATURES] = ff
        _stamp_extensions(case_xy, case_st.statements, typedef_names, module)
        case_obj: dict[str, Any] = {JsonSchemaKey.TYPE: "object"}
        _with_description(case_obj, case_st.description)
        case_obj[JsonSchemaKey.PROPERTIES] = cp
        case_obj[JsonSchemaKey.ADDITIONAL_PROPERTIES] = False
        case_obj[JsonSchemaKey.REQUIRED] = list(keys)
        case_obj[JsonSchemaKey.X_YANG] = case_xy
        case_branch.append(case_obj)
    if mandatory and case_entries:
        out[JsonSchemaKey.ONE_OF] = case_branch
    elif not mandatory and len(case_entries) > 1:
        out[JsonSchemaKey.ONE_OF] = [
            {JsonSchemaKey.TYPE: "object", JsonSchemaKey.MAX_PROPERTIES: 0},
            *case_branch,
        ]
    return out


def _property_key(stmt: YangStatement, module: YangModule) -> str:
    """RFC 7951 member name: ``module:name`` for a node another module defines (augment)."""
    owner = getattr(stmt, "defining_module", None)
    if owner and owner != module.name:
        return f"{owner}:{stmt.name}"
    return stmt.name or ""


def _child_property_map(
    children: list[YangStatement],
    typedef_names: set[str],
    module: YangModule,
    parent: YangStatement | YangModule,
) -> tuple[dict[str, Any], list[str]]:
    """JSON Schema ``properties`` and parallel ``required`` names for mandatory leaves."""
    props: dict[str, Any] = {}
    required: list[str] = []
    for child in children:
        child_prop = _statement_to_property(child, typedef_names, module, parent=parent)
        if child_prop is not None:
            props[_property_key(child, module)] = child_prop
            if _mandatory_schema_child(child):
                required.append(_property_key(child, module))
    return props, required


def _container_stmt_to_property(
    stmt: YangContainerStmt,
    typedef_names: set[str],
    module: YangModule,
) -> dict[str, Any]:
    children = _expand_uses_for_json(stmt.statements, module)
    when_stmt = getattr(stmt, "when", None)
    others, hoisted_ch = _partition_choice_sibling_statements(children)

    if hoisted_ch is not None and others:
        base_props, base_required = _child_property_map(others, typedef_names, module, stmt)
        ch_body = _choice_to_object_body(
            hoisted_ch, typedef_names, module, leafref_parent=stmt
        )
        xy_container = {
            **_build_xyang(
                "container",
                must_list=getattr(stmt, "must_statements", None) or [],
                when_stmt=when_stmt,
                presence=getattr(stmt, "presence", None),
                if_features=_if_features_for_xyang(stmt),
                config=_explicit_config(stmt),
            ),
            XYangKey.CHOICE: _choice_meta_xyang(hoisted_ch, typedef_names, module),
        }
        _stamp_extensions(xy_container, children, typedef_names, module)
        out: dict[str, Any] = {JsonSchemaKey.TYPE: "object"}
        _with_description(out, stmt.description)
        out[JsonSchemaKey.X_YANG] = xy_container
        if JsonSchemaKey.ONE_OF in ch_body:
            out[JsonSchemaKey.ONE_OF] = _merge_oneof_branches_with_base(
                ch_body[JsonSchemaKey.ONE_OF], base_props, base_required
            )
        elif ch_body.get(JsonSchemaKey.PROPERTIES):
            out[JsonSchemaKey.PROPERTIES] = {
                **base_props,
                **ch_body[JsonSchemaKey.PROPERTIES],
            }
            out[JsonSchemaKey.ADDITIONAL_PROPERTIES] = False
            req = list(base_required)
            if ch_body.get(JsonSchemaKey.REQUIRED):
                req = sorted(set(req) | set(ch_body[JsonSchemaKey.REQUIRED]))
            if req:
                out[JsonSchemaKey.REQUIRED] = req
        return out

    if len(children) == 1 and isinstance(children[0], YangChoiceStmt):
        # Choice (and case) are not data nodes; instance keys are case leaves on this container.
        ch0 = children[0]
        ch_body = _choice_to_object_body(
            ch0, typedef_names, module, leafref_parent=stmt
        )
        xy_container = {
            **_build_xyang(
                "container",
                must_list=getattr(stmt, "must_statements", None) or [],
                when_stmt=when_stmt,
                presence=getattr(stmt, "presence", None),
                if_features=_if_features_for_xyang(stmt),
                config=_explicit_config(stmt),
            ),
            XYangKey.CHOICE: _choice_meta_xyang(ch0, typedef_names, module),
        }
        _stamp_extensions(xy_container, children, typedef_names, module)
        out = {JsonSchemaKey.TYPE: "object"}
        # Choice text lives in x-yang.choice.description; do not merge onto the container.
        _with_description(out, stmt.description)
        out[JsonSchemaKey.X_YANG] = xy_container
        if JsonSchemaKey.ONE_OF in ch_body:
            out[JsonSchemaKey.ONE_OF] = ch_body[JsonSchemaKey.ONE_OF]
        elif ch_body.get(JsonSchemaKey.PROPERTIES):
            out[JsonSchemaKey.PROPERTIES] = ch_body[JsonSchemaKey.PROPERTIES]
            out[JsonSchemaKey.ADDITIONAL_PROPERTIES] = False
        return out

    props, required = _child_property_map(children, typedef_names, module, stmt)
    out = {JsonSchemaKey.TYPE: "object"}
    _with_description(out, stmt.description)
    out[JsonSchemaKey.X_YANG] = _build_xyang(
        "container",
        must_list=getattr(stmt, "must_statements", None) or [],
        when_stmt=when_stmt,
        presence=getattr(stmt, "presence", None),
        if_features=_if_features_for_xyang(stmt),
        config=_explicit_config(stmt),
    )
    _stamp_extensions(out[JsonSchemaKey.X_YANG], children, typedef_names, module)
    if props:
        out[JsonSchemaKey.PROPERTIES] = props
    out[JsonSchemaKey.ADDITIONAL_PROPERTIES] = False
    if required:
        out[JsonSchemaKey.REQUIRED] = required
    return out


def _list_items_object_schema(
    list_children: list[YangStatement],
    stmt: YangListStmt,
    typedef_names: set[str],
    module: YangModule,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Shape of one list entry (object) and optional x-yang keys to merge (e.g. hoisted ``choice``)."""
    others_lc, hoisted_list_ch = _partition_choice_sibling_statements(list_children)
    if hoisted_list_ch is not None and others_lc:
        list_base_props, list_base_required = _child_property_map(
            others_lc, typedef_names, module, stmt
        )
        ch_body = _choice_to_object_body(
            hoisted_list_ch, typedef_names, module, leafref_parent=stmt
        )
        items: dict[str, Any] = {JsonSchemaKey.TYPE: "object"}
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
        overlay = {XYangKey.CHOICE: _choice_meta_xyang(hoisted_list_ch, typedef_names, module)}
        return items, overlay
    if len(list_children) == 1 and isinstance(list_children[0], YangChoiceStmt):
        ch0 = list_children[0]
        ch_body = _choice_to_object_body(
            ch0, typedef_names, module, leafref_parent=stmt
        )
        items = {JsonSchemaKey.TYPE: "object"}
        if JsonSchemaKey.ONE_OF in ch_body:
            items[JsonSchemaKey.ONE_OF] = ch_body[JsonSchemaKey.ONE_OF]
        else:
            items[JsonSchemaKey.PROPERTIES] = ch_body.get(JsonSchemaKey.PROPERTIES) or {}
            items[JsonSchemaKey.ADDITIONAL_PROPERTIES] = False
        overlay = {XYangKey.CHOICE: _choice_meta_xyang(ch0, typedef_names, module)}
        return items, overlay
    props, item_required = _child_property_map(
        list_children, typedef_names, module, stmt
    )
    items = {
        JsonSchemaKey.TYPE: "object",
        JsonSchemaKey.PROPERTIES: props,
    }
    items[JsonSchemaKey.ADDITIONAL_PROPERTIES] = False
    if item_required:
        items[JsonSchemaKey.REQUIRED] = item_required
    return items, None


def _list_stmt_to_property(
    stmt: YangListStmt,
    typedef_names: set[str],
    module: YangModule,
) -> dict[str, Any]:
    # Match parser/yang_parser: do not expand uses under lists refined to max-elements 0
    # (xFrame meta-model breaks composite recursion that way).
    if getattr(stmt, "max_elements", None) == 0:
        list_children = [_copy_statement(s) for s in stmt.statements]
    else:
        list_children = _expand_uses_for_json(stmt.statements, module)
    when_stmt = getattr(stmt, "when", None)
    list_xy = _build_xyang(
        "list",
        key=stmt.key,
        must_list=getattr(stmt, "must_statements", None) or [],
        when_stmt=when_stmt,
        if_features=_if_features_for_xyang(stmt),
        config=_explicit_config(stmt),
    )
    items, choice_overlay = _list_items_object_schema(
        list_children, stmt, typedef_names, module
    )
    if choice_overlay:
        list_xy = {**list_xy, **choice_overlay}
    if stmt.unique:
        list_xy[XYangKey.UNIQUE] = [list(paths) for paths in stmt.unique]
    _stamp_extensions(list_xy, list_children, typedef_names, module)
    out = {
        JsonSchemaKey.TYPE: "array",
        JsonSchemaKey.ITEMS: items,
    }
    _with_description(out, stmt.description)
    out[JsonSchemaKey.X_YANG] = list_xy
    if getattr(stmt, "min_elements", None) is not None and stmt.min_elements is not None:
        out[JsonSchemaKey.MIN_ITEMS] = stmt.min_elements
    if getattr(stmt, "max_elements", None) is not None and stmt.max_elements is not None:
        out[JsonSchemaKey.MAX_ITEMS] = stmt.max_elements
    return out


def _leaf_stmt_to_property(
    stmt: YangLeafStmt,
    typedef_names: set[str],
    module: YangModule,
    parent: YangStatement | YangModule | None,
) -> dict[str, Any]:
    type_stmt = stmt.type
    when_stmt = getattr(stmt, "when", None)
    from ..module import resolve_typedef

    if type_stmt and type_stmt.name in typedef_names and module.typedefs[type_stmt.name].scope is None and resolve_typedef(type_stmt, module)[0] is module.typedefs[type_stmt.name]:
        out: dict[str, Any] = {
            JsonSchemaKey.REF: json_schema_defs_uri(type_stmt.name),
        }
        _with_description(out, stmt.description)
        out[JsonSchemaKey.X_YANG] = _build_xyang(
            "leaf",
            must_list=getattr(stmt, "must_statements", None) or [],
            when_stmt=when_stmt,
            mandatory=stmt.mandatory or None,
            if_features=_if_features_for_xyang(stmt),
            units=stmt.units or None,
            config=_explicit_config(stmt),
        )
        _stamp_extensions(out[JsonSchemaKey.X_YANG], stmt.statements, typedef_names, module)
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
            when_stmt=when_stmt,
            mandatory=stmt.mandatory or None,
            if_features=_if_features_for_xyang(stmt),
            units=stmt.units or None,
            config=_explicit_config(stmt),
        )
        # Preserve leafref (type, path, require-instance) from type_schema x-yang
        if type_schema.get(JsonSchemaKey.X_YANG):
            leaf_xyang = {**leaf_xyang, **type_schema.get(JsonSchemaKey.X_YANG, {})}
        out = {
            k: v
            for k, v in type_schema.items()
            if k not in (JsonSchemaKey.X_YANG, JsonSchemaKey.DESCRIPTION)
        }
        _with_description(out, stmt.description)
        _stamp_extensions(leaf_xyang, stmt.statements, typedef_names, module)
        out[JsonSchemaKey.X_YANG] = leaf_xyang
    if stmt.default is not None:
        yang_type = _leaf_yang_type_name(type_stmt, typedef_names, module)
        schema_type = out.get(JsonSchemaKey.TYPE)
        out[JsonSchemaKey.DEFAULT] = _json_schema_default_value(
            stmt.default,
            yang_type_name=yang_type,
            json_schema_type=schema_type if isinstance(schema_type, str) else None,
        )
    return out


def _anydata_anyxml_stmt_to_property(
    stmt: YangAnydataStmt | YangAnyxmlStmt,
    typedef_names: set[str],
    module: YangModule,
) -> dict[str, Any]:
    when_stmt = getattr(stmt, "when", None)
    xy_type = (
        XYangTypeValue.ANYDATA
        if isinstance(stmt, YangAnydataStmt)
        else XYangTypeValue.ANYXML
    )
    out = {**_ANY_JSON_INSTANCE_SCHEMA}
    _with_description(out, stmt.description)
    out[JsonSchemaKey.X_YANG] = _build_xyang(
        xy_type,
        must_list=getattr(stmt, "must_statements", None) or [],
        when_stmt=when_stmt,
        mandatory=stmt.mandatory or None,
        if_features=_if_features_for_xyang(stmt),
    )
    _stamp_extensions(out[JsonSchemaKey.X_YANG], stmt.statements, typedef_names, module)
    return out


def _leaf_list_stmt_to_property(
    stmt: YangLeafListStmt,
    typedef_names: set[str],
    module: YangModule,
    parent: YangStatement | YangModule | None,
) -> dict[str, Any]:
    type_stmt = stmt.type
    lr_anchor = _leafref_context_parent(module, parent)
    items_schema = _type_to_schema(
        type_stmt,
        typedef_names,
        module=module,
        leafref_anchor=lr_anchor,
    )
    when_stmt = getattr(stmt, "when", None)
    out = {
        JsonSchemaKey.TYPE: "array",
        JsonSchemaKey.ITEMS: items_schema,
    }
    _with_description(out, stmt.description)
    out[JsonSchemaKey.X_YANG] = _build_xyang(
        "leaf-list",
        must_list=getattr(stmt, "must_statements", None) or [],
        when_stmt=when_stmt,
        if_features=_if_features_for_xyang(stmt),
        units=stmt.units or None,
        config=_explicit_config(stmt),
    )
    _stamp_extensions(out[JsonSchemaKey.X_YANG], stmt.statements, typedef_names, module)
    if getattr(stmt, "min_elements", None) is not None and stmt.min_elements is not None:
        out[JsonSchemaKey.MIN_ITEMS] = stmt.min_elements
    if getattr(stmt, "max_elements", None) is not None and stmt.max_elements is not None:
        out[JsonSchemaKey.MAX_ITEMS] = stmt.max_elements
    defaults = getattr(stmt, "defaults", None) or []
    if defaults:
        out[JsonSchemaKey.DEFAULT] = list(defaults)
    return out


def _choice_stmt_to_property(
    stmt: YangChoiceStmt,
    typedef_names: set[str],
    module: YangModule,
    parent: YangStatement | YangModule | None,
) -> dict[str, Any]:
    anchor = parent if parent is not None else module
    body = _choice_to_object_body(stmt, typedef_names, module, leafref_parent=anchor)
    xy_choice: dict[str, Any] = {
        XYangKey.TYPE: "choice",
        XYangKey.MANDATORY: bool(getattr(stmt, "mandatory", False)),
    }
    cfg = _explicit_config(stmt)
    if cfg is not None:
        xy_choice[XYangKey.CONFIG] = cfg
    ff = _if_features_for_xyang(stmt)
    if ff:
        xy_choice[XYangKey.IF_FEATURES] = ff
    _stamp_extensions(xy_choice, stmt.statements, typedef_names, module)
    out: dict[str, Any] = {JsonSchemaKey.TYPE: "object"}
    _with_description(out, body.get(JsonSchemaKey.DESCRIPTION, ""))
    out[JsonSchemaKey.X_YANG] = xy_choice
    if body.get(JsonSchemaKey.PROPERTIES):
        out[JsonSchemaKey.PROPERTIES] = body[JsonSchemaKey.PROPERTIES]
    if JsonSchemaKey.ONE_OF in body:
        out[JsonSchemaKey.ONE_OF] = body[JsonSchemaKey.ONE_OF]
    return out


def _io_block_to_property(
    stmt: YangInputStmt | YangOutputStmt,
    typedef_names: set[str],
    module: YangModule,
) -> dict[str, Any]:
    """Encode RPC/action ``input`` or ``output`` as a JSON Schema object."""
    io_type = (
        XYangTypeValue.INPUT if isinstance(stmt, YangInputStmt) else XYangTypeValue.OUTPUT
    )
    children = _expand_uses_for_json(stmt.statements, module)
    props, required = _child_property_map(children, typedef_names, module, stmt)
    out: dict[str, Any] = {JsonSchemaKey.TYPE: "object"}
    _with_description(out, stmt.description)
    out[JsonSchemaKey.X_YANG] = _build_xyang(
        io_type,
        must_list=getattr(stmt, "must_statements", None) or [],
        when_stmt=getattr(stmt, "when", None),
        if_features=_if_features_for_xyang(stmt),
    )
    _stamp_extensions(out[JsonSchemaKey.X_YANG], children, typedef_names, module)
    out[JsonSchemaKey.ADDITIONAL_PROPERTIES] = False
    if props:
        out[JsonSchemaKey.PROPERTIES] = props
    if required:
        out[JsonSchemaKey.REQUIRED] = required
    return out


def _with_actions(
    prop: dict[str, Any], stmt: YangStatement, typedef_names: set[str], module: YangModule
) -> dict[str, Any]:
    """Add ``x-yang.actions`` (RFC 7950 §7.15) to a container or list property."""
    actions = {
        _property_key(child, module): _rpc_to_json(child, typedef_names, module, XYangTypeValue.ACTION)
        for child in _expand_uses_for_json(stmt.statements, module)
        if isinstance(child, YangActionStmt) and child.name
    }
    if actions:
        prop[JsonSchemaKey.X_YANG][XYangKey.ACTIONS] = actions
    return prop


def _rpc_to_json(
    stmt: YangRpcStmt,
    typedef_names: set[str],
    module: YangModule,
    kind: str = XYangTypeValue.RPC,
) -> dict[str, Any]:
    """Encode one module-level ``rpc`` for ``x-yang.rpcs``, or one ``action`` for ``x-yang.actions``."""
    xyang = _build_xyang(
        kind,
        must_list=getattr(stmt, "must_statements", None) or [],
        when_stmt=getattr(stmt, "when", None),
        if_features=_if_features_for_xyang(stmt),
    )
    _stamp_extensions(xyang, stmt.statements, typedef_names, module)
    out: dict[str, Any] = {JsonSchemaKey.X_YANG: xyang}
    inp = stmt.find_statement("input")
    if isinstance(inp, YangInputStmt):
        out["input"] = _io_block_to_property(inp, typedef_names, module)
    outp = stmt.find_statement("output")
    if isinstance(outp, YangOutputStmt):
        out["output"] = _io_block_to_property(outp, typedef_names, module)
    return out


def _statement_to_property(
    stmt: YangStatement,
    typedef_names: set[str],
    module: YangModule,
    parent: YangStatement | YangModule | None = None,
) -> dict[str, Any] | None:
    """Convert an AST statement to a JSON Schema property. Returns None for unsupported nodes. Expands uses when present."""
    prop = _statement_to_property_body(stmt, typedef_names, module, parent)
    if isinstance(prop, dict):
        path = getattr(stmt, "augment_structure", None)
        xy = prop.get(JsonSchemaKey.X_YANG)
        if isinstance(path, str) and path and isinstance(xy, dict):
            xy[XYangKey.AUGMENT_STRUCTURE] = path
    return prop


def _statement_to_property_body(
    stmt: YangStatement,
    typedef_names: set[str],
    module: YangModule,
    parent: YangStatement | YangModule | None = None,
) -> dict[str, Any] | None:
    if isinstance(stmt, YangContainerStmt):
        return _with_actions(_container_stmt_to_property(stmt, typedef_names, module), stmt, typedef_names, module)
    if isinstance(stmt, YangListStmt):
        return _with_actions(_list_stmt_to_property(stmt, typedef_names, module), stmt, typedef_names, module)
    if isinstance(stmt, YangLeafStmt):
        return _leaf_stmt_to_property(stmt, typedef_names, module, parent)
    if isinstance(stmt, (YangAnydataStmt, YangAnyxmlStmt)):
        return _anydata_anyxml_stmt_to_property(stmt, typedef_names, module)
    if isinstance(stmt, YangLeafListStmt):
        return _leaf_list_stmt_to_property(stmt, typedef_names, module, parent)
    if isinstance(stmt, YangChoiceStmt):
        return _choice_stmt_to_property(stmt, typedef_names, module, parent)
    return None


def _identity_to_def(
    name: str, identity: YangIdentityStmt, module: YangModule, only: set[str] | None = None
) -> dict[str, Any]:
    """Convert YangIdentityStmt to a $defs entry (enum of qualified names + x-yang).

    *only* limits the enum to the identities an ``x-yang.imports`` stub carries.
    """
    closure = sorted(descendant_closure(module, name) & only if only is not None else descendant_closure(module, name))
    enum_vals = [qualified_identity_name(module, n) for n in closure]
    out = {
        JsonSchemaKey.TYPE: "string",
        JsonSchemaKey.ENUM: enum_vals,
    }
    _with_description(out, identity.description)
    out[JsonSchemaKey.X_YANG] = {
        XYangKey.TYPE: XYangTypeValue.IDENTITY,
        XYangKey.BASES: _format_bases_for_json(list(identity.bases)),
        **(
            {XYangKey.IF_FEATURES: list(identity.if_features)}
            if identity.if_features
            else {}
        ),
    }
    if only is None:
        _stamp_extensions(out[JsonSchemaKey.X_YANG], identity.statements, set(module.typedefs), module)
    return out


def _typedef_to_def(typedef: YangTypedefStmt, module: YangModule) -> dict[str, Any]:
    """Convert YangTypedefStmt to a $defs entry."""
    type_stmt = typedef.type
    schema = _type_to_schema(
        type_stmt,
        set(),
        module=module,
        leafref_anchor=None,
    )  # no $ref inside typedef def
    schema.pop(JsonSchemaKey.DESCRIPTION, None)
    _with_description(schema, typedef.description)
    if typedef.units:
        _merge_units_into_schema(schema, typedef.units)
    if typedef.default is not None:
        yang_type = typedef.type.name if typedef.type else None
        schema_type = schema.get(JsonSchemaKey.TYPE)
        schema[JsonSchemaKey.DEFAULT] = _json_schema_default_value(
            typedef.default,
            yang_type_name=yang_type,
            json_schema_type=schema_type if isinstance(schema_type, str) else None,
        )
    invocations = _extension_invocations_json(typedef.statements, set(module.typedefs), module)
    if invocations:
        xy = schema.get(JsonSchemaKey.X_YANG)
        if not isinstance(xy, dict):
            xy = {}
            schema[JsonSchemaKey.X_YANG] = xy
        xy[XYangKey.EXTENSIONS] = invocations
    if typedef.scope is not None:
        schema.setdefault("x-yang", {}).update({"scope": typedef.scope, "name": typedef.name})
    return schema


def _features_json(module: YangModule) -> dict[str, Any]:
    """Declared features, so a reloaded module evaluates ``if-feature`` the same way."""
    names = sorted(module.features)
    if not names and not module.feature_if_features:
        return {}
    out: dict[str, Any] = {}
    for name in names:
        body: dict[str, Any] = {}
        guards = module.feature_if_features.get(name) or []
        if guards:
            body[XYangKey.IF_FEATURES] = list(guards)
        out[name] = body
    return out


def _detached_runtime(module: YangModule) -> dict[str, Any]:
    """A runtime dict the export copy can index without editing *module*'s index."""
    runtime: dict[str, Any] = {}
    for key, value in module.extension_runtime.items():
        if isinstance(value, dict):
            runtime[key] = dict(value)
        elif isinstance(value, list):
            runtime[key] = list(value)
        else:
            runtime[key] = value
    return runtime


def _ordered_extension_invocations(
    module: YangModule,
    typedef_names: set[str],
) -> list[dict[str, Any]]:
    """Module-level invocations in source order, including a foreign ``augment-structure`` that was removed."""
    kept = _extension_invocations_json(module.statements, typedef_names, module)
    foreign = module.extension_runtime.get(FOREIGN_AUGMENTS) or []
    slots = module.extension_runtime.get(FOREIGN_SLOTS) or []
    if not foreign:
        return kept
    groups: dict[int, list[dict[str, Any]]] = {}
    for slot, inv in zip(slots, foreign):
        if not isinstance(inv, YangExtensionInvocationStmt):
            continue
        groups.setdefault(int(slot), []).append(_one_extension_invocation(inv, typedef_names, module))
    ordered: list[dict[str, Any]] = []
    for index, item in enumerate(kept):
        ordered.extend(groups.pop(index, []))
        ordered.append(item)
    ordered.extend(groups.pop(len(kept), []))
    for slot in sorted(groups):
        ordered.extend(groups[slot])
    return ordered


def _iter_structures(module: YangModule) -> list[YangExtensionInvocationStmt]:
    """``sx:structure`` nodes of *module*, applied or not."""
    found: list[YangExtensionInvocationStmt] = []
    seen: set[int] = set()
    for stmt in module.statements:
        if isinstance(stmt, YangExtensionInvocationStmt) and _is_rfc8791(stmt, "structure"):
            found.append(stmt)
            seen.add(id(stmt))
    index = module.extension_runtime.get(_STRUCTURE_INDEX_KEY) or {}
    if isinstance(index, dict):
        for stmt in index.values():
            if isinstance(stmt, YangExtensionInvocationStmt) and id(stmt) not in seen and _is_rfc8791(stmt, "structure"):
                found.append(stmt)
                seen.add(id(stmt))
    return found


def _structure_view(module: YangModule) -> YangModule:
    """*module* with its own ``augment-structure`` merged, without editing *module*."""
    if not any(
        isinstance(stmt, YangExtensionInvocationStmt) and _is_rfc8791(stmt, "augment-structure")
        for stmt in module.statements
    ):
        return module
    cloned = copy(module)
    cloned.extension_runtime = {}
    cloned.statements = [copy_yang_statement(stmt) for stmt in module.statements]
    cloned.import_prefixes = module.import_prefixes
    apply_extension_invocations(cloned, export_view=True)
    return cloned


def _strip_augmented_by(stmt: YangStatement, exporter_name: str) -> YangStatement | None:
    """Drop nodes *exporter_name* added, at any depth, without editing *stmt*."""
    if getattr(stmt, "augment_structure_module", None) == exporter_name:
        return None
    cloned = copy_yang_statement(stmt)
    cloned.statements = [
        kept
        for child in cloned.statements
        if (kept := _strip_augmented_by(child, exporter_name)) is not None
    ]
    if isinstance(cloned, YangChoiceStmt):
        cloned.cases = [
            cast(YangCaseStmt, kept)
            for case in cloned.cases
            if (kept := _strip_augmented_by(case, exporter_name)) is not None
        ]
    return cloned


def _extension_stub(module: YangModule) -> dict[str, Any]:
    """``x-yang.imports`` entry that carries *module*'s extension definitions."""
    return {
        XYangKey.MODULE: module.name,
        XYangKey.NAMESPACE: module.namespace or "",
        XYangKey.PREFIX: module.prefix or "",
        XYangKey.EXTENSION: {
            name: _extension_def_json(ext)
            for name, ext in module.extensions.items()
            if isinstance(ext, YangExtensionStmt)
        },
    }


def _add_imported_structures(root: YangModule, imports: dict[str, Any], typedef_names: set[str]) -> None:
    """Put each structure a foreign ``augment-structure`` targets on that import's stub.

    Nodes this module added are omitted: the invocation is exported separately and applied
    again when the JSON is loaded.
    """
    seen: set[tuple[str, str]] = set()
    invocations = [
        stmt
        for stmt in root.statements
        if isinstance(stmt, YangExtensionInvocationStmt) and _is_rfc8791(stmt, "augment-structure")
    ]
    for saved in root.extension_runtime.get(FOREIGN_AUGMENTS) or []:
        if isinstance(saved, YangExtensionInvocationStmt) and all(saved is not stmt for stmt in invocations):
            invocations.append(saved)
    for inv in invocations:
        if not inv.argument:
            continue
        try:
            first = parse_absolute_schema_path(inv.argument)[0]
        except ValueError:
            continue
        owner = root.resolve_prefixed_module(first.prefix or "")
        if owner is None or owner is root or owner.name == root.name:
            continue
        key = _import_key(root, owner)
        stub: dict[str, Any] | None = imports.get(key)
        if not isinstance(stub, dict):
            stub = {
                XYangKey.MODULE: owner.name,
                XYangKey.NAMESPACE: owner.namespace or "",
                XYangKey.PREFIX: owner.prefix or "",
            }
            imports[key] = stub
        view = _structure_view(owner)
        for structure in _iter_structures(view):
            marker = (key, (structure.argument or "").strip())
            if marker in seen:
                continue
            seen.add(marker)
            shadow = copy(structure)
            shadow.statements = [
                kept
                for child in structure.statements
                if (kept := _strip_augmented_by(child, root.name)) is not None
            ]
            body = _one_extension_invocation(shadow, typedef_names, root)
            stub.setdefault(XYangKey.EXTENSIONS, []).append(body)
            defining = structure.resolved_module
            prefix = structure.prefix
            if defining is not None and prefix:
                nested = stub.setdefault(XYangKey.IMPORTS, {})
                if prefix not in nested:
                    nested[prefix] = _extension_stub(defining)
    if imports:
        # Keep the key order stable across Python and TypeScript.
        ordered = dict(sorted(imports.items()))
        imports.clear()
        imports.update(ordered)


def _apply_own_augments(schema_module: YangModule) -> None:
    """Merge the module's ``augment`` statements into its own (``uses``-expanded) tree.

    The native JSON form is the module's schema tree, so an augment of a node this module
    instantiates (including through an imported grouping) becomes part of that node. An augment of
    another module's own tree has no place in this module's JSON, so it is an error, not dropped.
    """
    for stmt in schema_module.statements:
        if not isinstance(stmt, YangAugmentStmt):
            continue
        first = (stmt.augment_path_segments or parse_absolute_schema_path(stmt.augment_path))[0]
        if schema_module.resolve_prefixed_module(first.prefix or "") is not schema_module:
            raise YangExportError(
                f"cannot export augment {stmt.augment_path!r}: its target belongs to another module, "
                f"which the native JSON form of module {schema_module.name!r} does not carry"
            )
    apply_augmentations(schema_module)


def _apply_own_deviations(schema_module: YangModule) -> None:
    """Apply the module's ``deviation`` statements to its own (augmented) tree.

    Like an augment, a deviation of another module's tree has no place in this module's JSON,
    so it is an error, not dropped.
    """
    for stmt in schema_module.statements:
        if not isinstance(stmt, YangDeviationStmt):
            continue
        first = (stmt.target_path_segments or parse_absolute_schema_path(stmt.target_path))[0]
        if schema_module.resolve_prefixed_module(first.prefix or "") is not schema_module:
            raise YangExportError(
                f"cannot export deviation {stmt.target_path!r}: its target belongs to another module, "
                f"which the native JSON form of module {schema_module.name!r} does not carry"
            )
    apply_deviations(schema_module)


def generate_json_schema(module: YangModule) -> dict[str, Any]:
    """
    Build a JSON Schema dict from a YangModule AST.

    The output has the structure expected by parse_json_schema: root x-yang (module
    meta), properties (one entry per module-level data node), and $defs (typedefs).
    Raises :class:`YangExportError` for a construct the form cannot carry.
    """
    from ..typedef_scope import EXPORT_TYPEDEFS, scoped_export_catalog

    scope_token = EXPORT_TYPEDEFS.set(scoped_export_catalog(module))
    export = _IdentityExport(root=module)
    token = _EXPORT.set(export)
    ext_token = _EXT_USED.set(_ExtensionUse(root=module))
    try:
        return _generate_json_schema(module, export)
    finally:
        EXPORT_TYPEDEFS.reset(scope_token)
        _EXPORT.reset(token)
        _EXT_USED.reset(ext_token)


def _generate_json_schema(module: YangModule, export: _IdentityExport) -> dict[str, Any]:
    typedef_names = set(module.typedefs.keys())
    root_xyang: dict[str, Any] = {
        XYangKey.MODULE: module.name or "unknown",
        XYangKey.YANG_VERSION: getattr(module, "yang_version", "1.1"),
        XYangKey.NAMESPACE: module.namespace or "",
        XYangKey.PREFIX: module.prefix or "",
        XYangKey.ORGANIZATION: module.organization or "",
        XYangKey.CONTACT: module.contact or "",
    }
    # Resolve absolute/relative leafrefs against a uses-expanded view while keeping
    # CLI/parser behavior (`expand_uses=False`) unchanged for persisted ASTs.
    schema_module = copy(module)
    schema_module.extension_runtime = _detached_runtime(module)
    schema_module.statements = _expand_uses_for_json(module.statements, module)
    _apply_own_augments(schema_module)
    _apply_own_deviations(schema_module)
    # Merge a same-module ``sx:augment-structure`` into the structure. A cross-module one
    # stays as an invocation. Already-applied modules no-op (the nodes are already there).
    apply_extension_invocations(schema_module, export_view=True)

    properties: dict[str, Any] = {}
    for stmt in schema_module.statements:
        if not getattr(stmt, "name", None):
            continue
        prop = _statement_to_property(
            stmt, typedef_names, schema_module, parent=schema_module
        )
        if prop is not None:
            properties[_property_key(stmt, module)] = prop

    defs: dict[str, Any] = {}
    for name, typedef in schema_module.typedefs.items():
        if isinstance(typedef, YangTypedefStmt):
            defs[name] = _typedef_to_def(typedef, schema_module)
    from ..typedef_scope import EXPORT_TYPEDEFS

    scoped_definitions = EXPORT_TYPEDEFS.get()
    assert scoped_definitions is not None
    for name, (typedef, owner) in scoped_definitions.items():
        defs[name] = _typedef_to_def(typedef, owner)
    for name, identity in schema_module.identities.items():
        if isinstance(identity, YangIdentityStmt):
            defs[name] = _identity_to_def(name, identity, schema_module)

    rpcs: dict[str, Any] = {}
    for stmt in schema_module.statements:
        if isinstance(stmt, YangRpcStmt) and stmt.name:
            rpcs[stmt.name] = _rpc_to_json(stmt, typedef_names, schema_module)
    if rpcs:
        root_xyang[XYangKey.RPCS] = rpcs
    module_invocations = _ordered_extension_invocations(schema_module, typedef_names)
    imports = _merge_extension_imports(
        module,
        _imports_for_json(module, export.used),
        _EXT_USED.get().used,
    )
    _add_imported_structures(schema_module, imports, set())
    if imports:
        root_xyang[XYangKey.IMPORTS] = imports
    extension_defs = _local_extension_defs(module)
    if extension_defs:
        root_xyang[XYangKey.EXTENSION] = extension_defs
    features = _features_json(module)
    if features:
        root_xyang[XYangKey.FEATURES] = features
    if module_invocations:
        root_xyang[XYangKey.EXTENSIONS] = module_invocations
    _assert_extensions_placed(schema_module)

    root: dict[str, Any] = {
        JsonSchemaKey.SCHEMA: "https://json-schema.org/draft/2020-12/schema",
        JsonSchemaKey.ID: module.namespace or f"urn:{module.name or 'unknown'}",
    }
    _with_description(root, module.description)
    root[JsonSchemaKey.X_YANG] = root_xyang
    root[JsonSchemaKey.TYPE] = "object"
    root[JsonSchemaKey.PROPERTIES] = properties
    root[JsonSchemaKey.ADDITIONAL_PROPERTIES] = False
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
    text = json.dumps(data, indent=indent, ensure_ascii=False) + "\n"
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return text
