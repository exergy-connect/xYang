"""Resolve RFC 7950 ``augment`` targets and merge augmented schema into the target module.

Called from the parser only when ``expand_uses`` is True, so ``expand_uses=False`` keeps
``augment`` as explicit statements in the AST—matching the reversibility goal of
preserving ``uses``/grouping structure for round-trip convert paths.
"""

from __future__ import annotations

import copy
from typing import Callable, Dict, List, Optional

from .ast import (
    YangAugmentStmt,
    YangCaseStmt,
    YangChoiceStmt,
    YangDeviationStmt,
    YangStatement,
    YangStatementList,
)
from .module import YangModule
from .errors import YangSemanticError, YangSyntaxError
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


def _walk_absolute_schema_path(
    *,
    ctx_module: YangModule,
    path: str,
    kind: str,
    find_toplevel: Callable[[YangModule, str], Optional[YangStatement]],
    segments: List[YangIdentifierRef] | None = None,
) -> tuple[YangStatementList, YangStatement]:
    """Resolve ``/prefix:name/...`` to ``(parent, target)``.

    ``find_toplevel`` provides the root-node lookup strategy for segment 0.
    Child traversal semantics are shared (choice/case aware) via
    ``_find_named_schema_child``. The parent of a top-level node is its module.
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
    parent: YangStatementList = mod0
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
        parent = cur
        cur = nxt
    return parent, cur


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
    _parent, cur = _walk_absolute_schema_path(
        ctx_module=ctx_module,
        path=path,
        kind=kind,
        find_toplevel=find_toplevel,
        segments=segments,
    )
    if not hasattr(cur, "statements"):
        raise YangSyntaxError(
            f"{kind}: target node {getattr(cur, 'name', '?')!r} cannot contain "
            f"schema substatements (path {path!r})"
        )
    return cur


def _remove_schema_child(parent: YangStatementList, child: YangStatement) -> None:
    """Drop *child* from *parent* (choice cases live on ``cases``, not ``statements``)."""
    if isinstance(parent, YangChoiceStmt) and child in parent.cases:
        parent.cases.remove(child)
        if child in parent.statements:
            parent.statements.remove(child)
        return
    if child in parent.statements:
        parent.statements.remove(child)
        return
    name = getattr(child, "name", "?")
    raise YangSemanticError(
        f"deviation: target node {name!r} is not a child of its parent"
    )


def _cow_statement(stmt: YangStatement) -> YangStatement:
    """Shallow copy whose child lists are new. Descendants stay shared until copied."""
    cloned = copy.copy(stmt)
    cloned.statements = list(stmt.statements)
    if isinstance(stmt, YangChoiceStmt):
        cloned.cases = list(stmt.cases)
    return cloned


def _cow_module(mod: YangModule) -> YangModule:
    """Module copy for one deviating build. The parser cache keeps *mod*."""
    cloned = copy.copy(mod)
    cloned.statements = list(mod.statements)
    cloned.import_prefixes = dict(mod.import_prefixes)
    return cloned


def _schema_child_slot(parent: YangStatementList, name: str) -> tuple[str, int] | None:
    if isinstance(parent, YangChoiceStmt):
        for index, case in enumerate(parent.cases):
            if case.name == name and case.get_schema_node() is not None:
                return ("cases", index)
    for index, stmt in enumerate(parent.statements):
        if getattr(stmt, "name", None) == name and stmt.get_schema_node() is not None:
            return ("statements", index)
    return None


def _child_at(parent: YangStatementList, slot: tuple[str, int]) -> YangStatement:
    attr, index = slot
    return getattr(parent, attr)[index]


def _put_child(parent: YangStatementList, slot: tuple[str, int], stmt: YangStatement) -> None:
    attr, index = slot
    getattr(parent, attr)[index] = stmt


def _drop_child_at(parent: YangStatementList, slot: tuple[str, int]) -> None:
    attr, index = slot
    del getattr(parent, attr)[index]


def _detach_copied_path(module: YangModule, segments: List[YangIdentifierRef]) -> None:
    """Remove the node named by *segments* from a module copy, copying ancestors only."""
    slot = _schema_child_slot(module, segments[0].name)
    if slot is None:
        raise YangSemanticError(
            f"deviation: no schema node for path "
            f"'/{'/'.join(f'{s.prefix}:{s.name}' for s in segments)}'"
        )
    if len(segments) == 1:
        _drop_child_at(module, slot)
        return
    current = _cow_statement(_child_at(module, slot))
    _put_child(module, slot, current)
    for seg in segments[1:-1]:
        slot = _schema_child_slot(current, seg.name)
        if slot is None:
            raise YangSemanticError(
                f"deviation: no child {seg.name!r} under {getattr(current, 'name', '?')!r}"
            )
        nxt = _cow_statement(_child_at(current, slot))
        _put_child(current, slot, nxt)
        current = nxt
    slot = _schema_child_slot(current, segments[-1].name)
    if slot is None:
        raise YangSemanticError(
            f"deviation: no child {segments[-1].name!r} under {getattr(current, 'name', '?')!r}"
        )
    _drop_child_at(current, slot)


def _private_target_module(
    root: YangModule,
    owner: YangModule,
    copies: Dict[int, YangModule],
) -> YangModule:
    """Return a module this build may edit. Cached imports are copied once."""
    if owner is root:
        return root
    for cloned in copies.values():
        if cloned is owner:
            return owner
    existing = copies.get(id(owner))
    if existing is not None:
        return existing
    cloned = _cow_module(owner)
    copies[id(owner)] = cloned
    for prefix, mod in list(root.import_prefixes.items()):
        if mod is owner:
            root.import_prefixes[prefix] = cloned
    return cloned


def _apply_not_supported(
    root: YangModule,
    dev: YangDeviationStmt,
    copies: Dict[int, YangModule],
) -> None:
    path = dev.target_path
    segments = dev.target_path_segments or None
    try:
        parent, node = _walk_absolute_schema_path(
            ctx_module=root,
            path=path,
            kind="deviation",
            find_toplevel=_find_toplevel_schema_child,
            segments=segments,
        )
    except YangSyntaxError as exc:
        raise YangSemanticError(str(exc)) from exc
    resolved = list(segments) if segments else parse_absolute_schema_path(path)
    owner = root.resolve_prefixed_module(resolved[0].prefix or "")
    if owner is None:
        raise YangSemanticError(
            f"deviation: unknown prefix {resolved[0].prefix!r} in path {path!r}"
        )
    if owner is root:
        _remove_schema_child(parent, node)
        return
    private = _private_target_module(root, owner, copies)
    _detach_copied_path(private, resolved)


def apply_deviations(root: YangModule) -> None:
    """Remove each ``deviate not-supported`` target, then drop the ``deviation`` statements.

    Uses the same absolute-path resolution as ``augment`` (import prefixes included).
    A path that does not name a schema node is a :class:`YangSemanticError`.
    A target in another module is removed on a copy owned by *root*; the module
    object in the parser cache is left unchanged.
    ``deviate add|replace|delete`` are not applied; the parser already warned.
    """
    pending = [s for s in root.statements if isinstance(s, YangDeviationStmt)]
    copies: Dict[int, YangModule] = {}
    for dev in pending:
        if dev.not_supported:
            _apply_not_supported(root, dev, copies)
    if pending:
        root.statements = [
            s for s in root.statements if not isinstance(s, YangDeviationStmt)
        ]


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
    seen_dev: set[int] = set()
    for mod in modules.values():
        oid = id(mod)
        if oid in seen_dev:
            continue
        seen_dev.add(oid)
        apply_deviations(mod)
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
