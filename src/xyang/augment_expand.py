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
    YangAnydataStmt,
    YangAnyxmlStmt,
    YangDeviateStmt,
    YangDeviationStmt,
    YangInputStmt,
    YangLeafListStmt,
    YangLeafStmt,
    YangListStmt,
    YangOutputStmt,
    YangRpcStmt,
    YangStatement,
    YangStatementList,
    YangStatementWithMust,
    YangStatementWithWhen,
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


def _materialize_operation_io(parent: YangStatement, name: str) -> Optional[YangStatement]:
    """RFC 7950 §7.14.2 / §7.14.3: every rpc and action has ``input`` and ``output`` schema
    nodes, written or not. Add the empty node a schema node identifier names."""
    if not isinstance(parent, YangRpcStmt) or name not in ("input", "output"):
        return None
    if name == "input":
        node: YangStatement = YangInputStmt(name="input")
        index = next(
            (i for i, s in enumerate(parent.statements) if isinstance(s, YangOutputStmt)),
            len(parent.statements),
        )
        parent.statements.insert(index, node)
    else:
        node = YangOutputStmt(name="output")
        parent.statements.append(node)
    return node


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
    return _materialize_operation_io(parent, name)


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
    node = _materialize_operation_io(parent, name)  # type: ignore[arg-type]
    if node is not None:
        return ("statements", parent.statements.index(node))
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


def _copied_path_to_target(
    module: YangModule, segments: List[YangIdentifierRef]
) -> tuple[YangStatementList, tuple[str, int]]:
    """Copy the ancestors of the node *segments* name in a module copy.

    Returns the copied parent and the slot of the target in it. The target is not copied.
    """
    def missing(name: str, under: str) -> YangSemanticError:
        path = "/" + "/".join(f"{s.prefix}:{s.name}" for s in segments)
        return YangSemanticError(f"deviation: no child {name!r} under {under!r} (path {path!r})")

    parent: YangStatementList = module
    slot = _schema_child_slot(module, segments[0].name)
    if slot is None:
        raise missing(segments[0].name, module.name)
    for seg in segments[1:]:
        current = _cow_statement(_child_at(parent, slot))
        _put_child(parent, slot, current)
        parent = current
        slot = _schema_child_slot(current, seg.name)
        if slot is None:
            raise missing(seg.name, getattr(current, "name", "?"))
    return parent, slot


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


def _deviation_target(
    root: YangModule,
    dev: YangDeviationStmt,
    copies: Dict[int, YangModule],
) -> tuple[YangStatementList, tuple[str, int], bool]:
    """Resolve *dev*'s target to ``(parent, slot, foreign)`` in a tree this build may edit.

    When *foreign*, the target itself is still shared with the parser cache."""
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
        if isinstance(parent, YangChoiceStmt) and node in parent.cases:
            return parent, ("cases", parent.cases.index(node)), False
        return parent, ("statements", parent.statements.index(node)), False
    private = _private_target_module(root, owner, copies)
    return (*_copied_path_to_target(private, resolved), True)


class _DeviateError(YangSemanticError):
    pass


def _node_kind(node: YangStatement) -> str:
    return type(node).__name__.removeprefix("Yang").removesuffix("Stmt").lower()


def _single(
    node: YangStatement,
    deviate: YangDeviateStmt,
    prop: str,
    value: object,
    *,
    present: bool,
    always_present: bool = False,
) -> object:
    """Return the new value of a single-valued property, or raise on an invalid deviate."""
    if deviate.kind == "add" and present:
        raise _DeviateError(
            f"cannot 'deviate add' {prop}: target {_node_kind(node)} {node.name!r} already has it "
            "(use 'deviate replace')"
        )
    if deviate.kind == "replace" and not present and not always_present:
        raise _DeviateError(
            f"cannot 'deviate replace' {prop}: target {_node_kind(node)} {node.name!r} has no {prop} "
            "(use 'deviate add')"
        )
    return value


def _require(node: YangStatement, prop: str, ok: bool) -> None:
    if not ok:
        raise _DeviateError(
            f"{prop} does not apply to target {_node_kind(node)} {node.name!r}"
        )


def _apply_deviate_defaults(node: YangStatement, deviate: YangDeviateStmt) -> None:
    values = deviate.defaults
    if isinstance(node, YangLeafListStmt):
        current = list(node.defaults)
        if deviate.kind == "add":
            node.defaults = current + list(values)
        elif deviate.kind == "replace":
            if not current:
                raise _DeviateError(
                    f"cannot 'deviate replace' default: target leaf-list {node.name!r} has no default"
                )
            node.defaults = list(values)
        else:
            for value in values:
                if value not in current:
                    raise _DeviateError(
                        f"cannot 'deviate delete' default {value!r}: target leaf-list "
                        f"{node.name!r} has no such default"
                    )
                current.remove(value)
            node.defaults = current
        return
    _require(node, "default", isinstance(node, (YangLeafStmt, YangChoiceStmt)))
    if len(values) != 1:
        raise _DeviateError(
            f"target {_node_kind(node)} {node.name!r} takes one default, got {len(values)}"
        )
    present = node.default is not None  # type: ignore[union-attr]
    if deviate.kind == "delete":
        if not present or str(node.default) != values[0]:  # type: ignore[union-attr]
            raise _DeviateError(
                f"cannot 'deviate delete' default {values[0]!r}: target {_node_kind(node)} "
                f"{node.name!r} has default {node.default!r}"  # type: ignore[union-attr]
            )
        node.default = None  # type: ignore[union-attr]
        return
    node.default = _single(node, deviate, "default", values[0], present=present)  # type: ignore[union-attr]


def _apply_deviate_musts(node: YangStatement, deviate: YangDeviateStmt) -> None:
    _require(node, "must", isinstance(node, YangStatementWithMust))
    current = list(node.must_statements)  # type: ignore[attr-defined]
    if deviate.kind == "add":
        node.must_statements = current + list(deviate.must_statements)  # type: ignore[attr-defined]
        return
    for must in deviate.must_statements:
        match = next((m for m in current if m.expression == must.expression), None)
        if match is None:
            raise _DeviateError(
                f"cannot 'deviate delete' must {must.expression!r}: target "
                f"{_node_kind(node)} {node.name!r} has no such must"
            )
        current.remove(match)
    node.must_statements = current  # type: ignore[attr-defined]


def _apply_deviate_unique(node: YangStatement, deviate: YangDeviateStmt) -> None:
    _require(node, "unique", isinstance(node, YangListStmt))
    current = [list(u) for u in node.unique]  # type: ignore[attr-defined]
    if deviate.kind == "add":
        node.unique = current + [list(u) for u in deviate.unique]  # type: ignore[attr-defined]
        return
    for paths in deviate.unique:
        if paths not in current:
            raise _DeviateError(
                f"cannot 'deviate delete' unique {' '.join(paths)!r}: target list "
                f"{node.name!r} has no such unique"
            )
        current.remove(paths)
    node.unique = current  # type: ignore[attr-defined]


def _apply_deviate(node: YangStatement, deviate: YangDeviateStmt) -> None:
    """Apply one ``deviate add|replace|delete`` to *node* (RFC 7950 §7.20.3.2)."""
    if deviate.config is not None:
        _require(node, "config", isinstance(node, YangStatementWithWhen) and not isinstance(node, YangRpcStmt))
        node.config = _single(  # type: ignore[attr-defined]
            node, deviate, "config", deviate.config,
            present=node.config is not None, always_present=True,  # type: ignore[attr-defined]
        )
    if deviate.mandatory is not None:
        _require(
            node,
            "mandatory",
            isinstance(node, (YangLeafStmt, YangChoiceStmt, YangAnydataStmt, YangAnyxmlStmt)),
        )
        node.mandatory = _single(  # type: ignore[attr-defined]
            node, deviate, "mandatory", deviate.mandatory,
            present=bool(node.mandatory), always_present=True,  # type: ignore[attr-defined]
        )
    if deviate.min_elements is not None:
        _require(node, "min-elements", isinstance(node, (YangListStmt, YangLeafListStmt)))
        node.min_elements = _single(  # type: ignore[attr-defined]
            node, deviate, "min-elements", deviate.min_elements,
            present=node.min_elements is not None, always_present=True,  # type: ignore[attr-defined]
        )
    if deviate.max_elements_set:
        _require(node, "max-elements", isinstance(node, (YangListStmt, YangLeafListStmt)))
        node.max_elements = _single(  # type: ignore[attr-defined]
            node, deviate, "max-elements", deviate.max_elements,
            present=node.max_elements is not None, always_present=True,  # type: ignore[attr-defined]
        )
    if deviate.type is not None:
        _require(node, "type", isinstance(node, (YangLeafStmt, YangLeafListStmt)))
        node.type = deviate.type  # type: ignore[attr-defined]
    if deviate.units is not None:
        _require(node, "units", isinstance(node, (YangLeafStmt, YangLeafListStmt)))
        if deviate.kind == "delete":
            if node.units != deviate.units:
                raise _DeviateError(
                    f"cannot 'deviate delete' units {deviate.units!r}: target "
                    f"{_node_kind(node)} {node.name!r} has units {node.units!r}"
                )
            node.units = ""
        else:
            node.units = _single(  # type: ignore[assignment]
                node, deviate, "units", deviate.units, present=bool(node.units)
            )
    if deviate.defaults:
        _apply_deviate_defaults(node, deviate)
    if deviate.must_statements:
        _apply_deviate_musts(node, deviate)
    if deviate.unique:
        _apply_deviate_unique(node, deviate)


def _apply_deviation(
    root: YangModule,
    dev: YangDeviationStmt,
    copies: Dict[int, YangModule],
) -> None:
    parent, slot, foreign = _deviation_target(root, dev, copies)
    node = _child_at(parent, slot)
    if dev.not_supported:
        if foreign:
            _drop_child_at(parent, slot)
        else:
            _remove_schema_child(parent, node)
        return
    if foreign:
        node = _cow_statement(node)
        _put_child(parent, slot, node)
    for deviate in dev.deviates:
        try:
            _apply_deviate(node, deviate)
        except _DeviateError as exc:
            raise YangSemanticError(f"deviation {dev.target_path!r}: {exc}") from None


def apply_deviations(root: YangModule) -> None:
    """Apply each ``deviation`` in order, then drop the ``deviation`` statements.

    Uses the same absolute-path resolution as ``augment`` (import prefixes included).
    A path that does not name a schema node, or a ``deviate`` the target cannot take
    (RFC 7950 §7.20.3.2), is a :class:`YangSemanticError`.
    A target in another module is changed on a copy owned by *root*; the module
    object in the parser cache is left unchanged.
    """
    pending = [s for s in root.statements if isinstance(s, YangDeviationStmt)]
    copies: Dict[int, YangModule] = {}
    for dev in pending:
        _apply_deviation(root, dev, copies)
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
