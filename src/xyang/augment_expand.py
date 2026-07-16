"""Resolve RFC 7950 ``augment`` targets and merge augmented schema into the target module.

Called from the parser only when ``expand_uses`` is True, so ``expand_uses=False`` keeps
``augment`` as explicit statements in the AST—matching the reversibility goal of
preserving ``uses``/grouping structure for round-trip convert paths.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from .ast import (
    YangAugmentStmt,
    YangCaseStmt,
    YangChoiceStmt,
    YangStatement,
    YangStatementList,
)
from .module import YangModule
from .errors import YangSyntaxError
from .identifier_ref import YangIdentifierRef, parse_absolute_schema_path
from .refine_expand import copy_yang_statement
from .uses_expand import (
    _merge_uses_if_features_into_grouping_roots,
    _merge_uses_when_into_grouping_roots,
)


def _path_segments_from_augment(aug: YangAugmentStmt, path: str) -> List[YangIdentifierRef]:
    stored = aug.augment_path_segments
    if stored:
        return stored
    try:
        return parse_absolute_schema_path(path)
    except ValueError as exc:
        raise YangSyntaxError(str(exc)) from exc


def _find_named_schema_child(parent: YangStatement, name: str) -> Optional[YangStatement]:
    if isinstance(parent, YangChoiceStmt):
        for case in parent.cases:
            if case.name == name:
                return case
        return None
    if not hasattr(parent, "statements"):
        return None
    sl: YangStatementList = parent  # type: ignore[assignment]
    for s in sl.statements:
        if getattr(s, "name", None) == name and s.get_schema_node() is not None:
            return s
    return None


def _find_toplevel_schema_child(module: YangModule, name: str) -> Optional[YangStatement]:
    for s in module.statements:
        if getattr(s, "name", None) == name and s.get_schema_node() is not None:
            return s
    return None


def resolve_augment_target(
    ctx_module: YangModule, path: str, aug: YangAugmentStmt | None = None
) -> YangStatement:
    """
    Resolve an absolute augment path to the **target schema node** that receives new children.

    Each path segment is ``prefix:identifier`` (RFC 7950 absolute schema node identifier).
    """
    return resolve_absolute_schema_path(
        ctx_module=ctx_module,
        path=path,
        segments=_path_segments_from_augment(aug, path) if aug is not None else None,
        kind="augment",
        find_toplevel=_find_toplevel_schema_child,
    )


def resolve_absolute_schema_path(
    *,
    ctx_module: YangModule,
    path: str,
    kind: str,
    find_toplevel: Callable[[YangModule, str], Optional[YangStatement]],
    segments: List[YangIdentifierRef] | None = None,
) -> YangStatement:
    """Resolve absolute ``/prefix:name/...`` path into a target schema node.

    ``find_toplevel`` provides the root-node lookup strategy for segment 0.
    Child traversal semantics are shared (choice/case aware) via
    ``_find_named_schema_child``.
    """
    if not segments:
        try:
            segments = parse_absolute_schema_path(path)
        except ValueError as exc:
            raise YangSyntaxError(str(exc)) from exc
    first = segments[0]
    pref0 = first.prefix
    name0 = first.name
    if not pref0:
        raise YangSyntaxError(
            f"{kind}: invalid first segment in path {path!r} "
            "(expected 'prefix:identifier')"
        )
    mod0 = ctx_module.resolve_prefixed_module(pref0)
    if mod0 is None:
        raise YangSyntaxError(
            f"{kind}: unknown prefix {pref0!r} in path {path!r} "
            f"(module {ctx_module.name!r})"
        )
    cur = find_toplevel(mod0, name0)
    if cur is None:
        raise YangSyntaxError(
            f"{kind}: no top-level schema node {name0!r} in module {mod0.name!r} "
            f"(path {path!r})"
        )
    for seg in segments[1:]:
        pref = seg.prefix
        nm = seg.name
        if not pref:
            raise YangSyntaxError(
                f"{kind}: invalid path segment {nm!r} in path {path!r} "
                "(expected 'prefix:identifier')"
            )
        if ctx_module.resolve_prefixed_module(pref) is None:
            raise YangSyntaxError(
                f"{kind}: unknown prefix {pref!r} in path {path!r}"
            )
        nxt = _find_named_schema_child(cur, nm)
        if nxt is None:
            raise YangSyntaxError(
                f"{kind}: no child {nm!r} under node in path {path!r} "
                f"(after {cur.name!r})"
            )
        cur = nxt
    if not hasattr(cur, "statements"):
        raise YangSyntaxError(
            f"{kind}: target node {getattr(cur, 'name', '?')!r} cannot contain "
            f"schema substatements (path {path!r})"
        )
    return cur


def _stamp_defining_module(stmt: YangStatement, module_name: str) -> None:
    """Mark *stmt* and descendants as defined in *module_name* (RFC 7951 qualified JSON names)."""
    if hasattr(stmt, "defining_module"):
        stmt.defining_module = module_name  # type: ignore[attr-defined]
    for child in stmt.statements:
        _stamp_defining_module(child, module_name)
    if isinstance(stmt, YangChoiceStmt):
        for case in stmt.cases:
            _stamp_defining_module(case, module_name)


def _merge_augment_into_target(
    aug: YangAugmentStmt, target: YangStatement, *, source_module: YangModule
) -> None:
    """Copy augmented children onto *target* (``uses``-expanded body expected)."""
    copies = [copy_yang_statement(x) for x in aug.statements]
    for c in copies:
        _stamp_defining_module(c, source_module.name)
    _merge_uses_if_features_into_grouping_roots(copies, aug.if_features)
    _merge_uses_when_into_grouping_roots(copies, aug.when)
    if isinstance(target, YangChoiceStmt):
        for c in copies:
            if isinstance(c, YangCaseStmt):
                target.cases.append(c)
            else:
                target.statements.append(c)
    else:
        tlist: YangStatementList = target  # type: ignore[assignment]
        for c in copies:
            tlist.statements.append(c)


def register_module_closure(modules: Dict[str, YangModule], mod: YangModule) -> None:
    """Register *mod* and every module reachable via ``import`` (RFC 7950 import closure)."""
    modules[mod.name] = mod
    for imported in mod.import_prefixes.values():
        register_module_closure(modules, imported)


def apply_augmentations_across_module_map(modules: Dict[str, YangModule]) -> None:
    """
    Apply every top-level ``augment`` still present in any module in *modules*.

    Use after loading a set of related modules (e.g. anydata validation map) so
    augments defined in one file merge into targets in another module that shares
    the same :class:`YangModule` instances (one :class:`~xyang.parser.yang_parser.YangParser`
    cache per load batch).
    """
    pending: list[tuple[YangModule, YangAugmentStmt]] = []
    seen: set[int] = set()
    for mod in modules.values():
        oid = id(mod)
        if oid in seen:
            continue
        seen.add(oid)
        for stmt in mod.statements:
            if isinstance(stmt, YangAugmentStmt):
                pending.append((mod, stmt))
    for aug_module, aug in pending:
        target = resolve_augment_target(aug_module, aug.augment_path, aug)
        _merge_augment_into_target(aug, target, source_module=aug_module)
    for mod in modules.values():
        mod.statements = [
            s for s in mod.statements if not isinstance(s, YangAugmentStmt)
        ]


def apply_augmentations(root: YangModule) -> None:
    """
    For each top-level ``augment``, copy its (already ``uses``-expanded) children onto the
    target node, merge ``if-feature`` / ``when`` like ``uses``, then remove the
    ``augment`` statement from *root*.
    """
    augments = [s for s in root.statements if isinstance(s, YangAugmentStmt)]
    for aug in augments:
        target = resolve_augment_target(root, aug.augment_path, aug)
        _merge_augment_into_target(aug, target, source_module=root)
    root.statements = [s for s in root.statements if not isinstance(s, YangAugmentStmt)]
