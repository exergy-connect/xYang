"""Resolve RFC 7950 ``augment`` targets and merge augmented schema into the target module.

Called from the parser only when ``expand_uses`` is True, so ``expand_uses=False`` keeps
``augment`` as explicit statements in the AST—matching the reversibility goal of
preserving ``uses``/grouping structure for round-trip convert paths.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from .ast import (
    YangAugmentStmt,
    YangChoiceStmt,
    YangStatement,
    YangStatementList,
)
from .module import YangModule
from .errors import YangSyntaxError
from .refine_expand import copy_yang_statement
from .uses_expand import (
    _merge_uses_if_features_into_grouping_roots,
    _merge_uses_when_into_grouping_roots,
)


def _split_prefixed_identifier(segment: str) -> Tuple[str, str]:
    segment = segment.strip()
    if ":" not in segment:
        raise YangSyntaxError(
            f"Invalid augment path segment {segment!r}: expected 'prefix:identifier'"
        )
    pref, _, ident = segment.partition(":")
    if not pref or not ident:
        raise YangSyntaxError(
            f"Invalid augment path segment {segment!r}: expected 'prefix:identifier'"
        )
    return pref, ident


def _parse_augment_path(path: str) -> List[str]:
    raw = (path or "").strip().strip('"').strip("'")
    if not raw.startswith("/"):
        raise YangSyntaxError(
            f"Augment path must be an absolute schema node identifier, got {path!r}"
        )
    parts = [p for p in raw[1:].split("/") if p.strip()]
    if not parts:
        raise YangSyntaxError(f"Empty augment path: {path!r}")
    return parts


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


def resolve_augment_target(ctx_module: YangModule, path: str) -> YangStatement:
    """
    Resolve an absolute augment path to the **target schema node** that receives new children.

    Each path segment is ``prefix:identifier`` (RFC 7950 absolute schema node identifier).
    """
    return resolve_absolute_schema_path(
        ctx_module=ctx_module,
        path=path,
        kind="augment",
        find_toplevel=_find_toplevel_schema_child,
    )


def resolve_absolute_schema_path(
    *,
    ctx_module: YangModule,
    path: str,
    kind: str,
    find_toplevel: Callable[[YangModule, str], Optional[YangStatement]],
) -> YangStatement:
    """Resolve absolute ``/prefix:name/...`` path into a target schema node.

    ``find_toplevel`` provides the root-node lookup strategy for segment 0.
    Child traversal semantics are shared (choice/case aware) via
    ``_find_named_schema_child``.
    """
    segments = _parse_augment_path(path)
    pref0, name0 = _split_prefixed_identifier(segments[0])
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
        pref, nm = _split_prefixed_identifier(seg)
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


def apply_augmentations(root: YangModule) -> None:
    """
    For each top-level ``augment``, copy its (already ``uses``-expanded) children onto the
    target node, merge ``if-feature`` / ``when`` like ``uses``, then remove the
    ``augment`` statement from *root*.
    """
    augments = [s for s in root.statements if isinstance(s, YangAugmentStmt)]
    for aug in augments:
        target = resolve_augment_target(root, aug.augment_path)
        copies = [copy_yang_statement(x) for x in aug.statements]
        _merge_uses_if_features_into_grouping_roots(copies, aug.if_features)
        _merge_uses_when_into_grouping_roots(copies, aug.when)
        tlist: YangStatementList = target  # type: ignore[assignment]
        for c in copies:
            tlist.statements.append(c)
    root.statements = [s for s in root.statements if not isinstance(s, YangAugmentStmt)]
