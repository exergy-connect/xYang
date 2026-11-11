"""RFC 8791 augment-structure apply callback."""

from __future__ import annotations

import contextvars
from dataclasses import replace

from ...ast import (
    YangExtensionInvocationStmt,
    YangStatement,
    YangStatementList,
    YangWhenStmt,
)
from ...augment_expand import resolve_absolute_schema_path
from ...errors import YangSyntaxError
from ...identifier_ref import parse_absolute_schema_path
from ...module import YangModule
from ...refine_expand import copy_yang_statement
from ...uses_expand import (
    _merge_uses_if_features_into_grouping_roots,
    _merge_uses_when_into_grouping_roots,
)

_STRUCTURE_INDEX_KEY = "ietf-yang-structure-ext:structure-index"
# Top-level ``augment-structure`` invocations whose target is another module. The merge
# removes them from the tree; export still needs the original invocation (RFC 8791, #164).
FOREIGN_AUGMENTS = "ietf-yang-structure-ext:foreign-augment-structure"
FOREIGN_SLOTS = "ietf-yang-structure-ext:foreign-augment-structure-slots"

# Set while ``generate_json_schema`` applies extensions on a copy. A foreign
# ``augment-structure`` stays in that copy so it can be exported verbatim; the imported
# module is not mutated.
_EXPORT_VIEW: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "xyang_rfc8791_export_view", default=False
)


def set_export_view(enabled: bool) -> contextvars.Token[bool]:
    """Return a token ``reset_export_view`` accepts. ``True`` keeps foreign augments unmerged."""
    return _EXPORT_VIEW.set(enabled)


def reset_export_view(token: contextvars.Token[bool]) -> None:
    _EXPORT_VIEW.reset(token)


def _export_view() -> bool:
    return _EXPORT_VIEW.get()


def _lookup_registered_structure(
    module: YangModule,
    name: str,
) -> YangExtensionInvocationStmt | None:
    idx = module.extension_runtime.get(_STRUCTURE_INDEX_KEY)
    if isinstance(idx, dict):
        stmt = idx.get(name)
        if isinstance(stmt, YangExtensionInvocationStmt):
            return stmt
    # ``expand_uses`` is off until after import, so a structure may still be only a
    # statement. Indexing it here would edit the imported module during export.
    for stmt in module.statements:
        if (
            isinstance(stmt, YangExtensionInvocationStmt)
            and stmt.resolved_extension is not None
            and stmt.resolved_extension.name == "structure"
            and stmt.resolved_module is not None
            and stmt.resolved_module.name == "ietf-yang-structure-ext"
            and (stmt.argument or "").strip() == name
        ):
            return stmt
    return None


def resolve_augment_structure_target(ctx_module: YangModule, path: str) -> YangStatement:
    """Resolve absolute augment-structure path to its target schema node."""
    return resolve_absolute_schema_path(
        ctx_module=ctx_module,
        path=path,
        kind="augment-structure",
        find_toplevel=_lookup_registered_structure,
    )


def _target_module(ctx_module: YangModule, path: str) -> YangModule:
    """Module that owns the first node of an absolute ``augment-structure`` path."""
    try:
        first = parse_absolute_schema_path(path)[0]
    except ValueError as exc:
        raise YangSyntaxError(str(exc)) from exc
    prefix = first.prefix or ""
    owner = ctx_module.resolve_prefixed_module(prefix)
    if owner is None:
        raise YangSyntaxError(
            f"augment-structure: unknown prefix {prefix!r} in path {path!r} "
            f"(module {ctx_module.name!r})"
        )
    return owner


def _when_for_merge(when: YangWhenStmt | None) -> YangWhenStmt | None:
    """A copy of *when* so merging does not set flags on the invocation itself.

    ``_merge_uses_when_into_grouping_roots`` marks the object it is given
    ``evaluate_with_parent_context``. The invocation must stay as written so a
    cross-module export is verbatim.
    """
    if when is None:
        return None
    return replace(when)


def apply_augment_structure_invocation(
    invocation: YangExtensionInvocationStmt,
    *,
    context_module: YangModule,
) -> YangStatement | None:
    """Apply one RFC 8791 augment-structure invocation.

    A target in this module is merged and the invocation is removed (``None``).
    A target in another module is merged the same way, and the invocation is kept
    aside for export. During JSON export of a module that has not been applied yet,
    a foreign invocation is left in place and the imported module is not changed.

    A second call on the same invocation does not copy its body again.
    """
    if getattr(invocation, "_rfc8791_applied", False):
        return None
    if not invocation.argument:
        raise YangSyntaxError("augment-structure requires an absolute path argument")
    target = resolve_augment_structure_target(context_module, invocation.argument)
    foreign = _target_module(context_module, invocation.argument) is not context_module
    if foreign and _export_view():
        # The invocation is the JSON form. Merging would edit the imported module.
        return invocation
    copies = [copy_yang_statement(x) for x in invocation.statements]
    _merge_uses_if_features_into_grouping_roots(copies, list(invocation.if_features))
    _merge_uses_when_into_grouping_roots(copies, _when_for_merge(invocation.when))
    for node in copies:
        node.augment_structure = invocation.argument  # type: ignore[attr-defined]
        node.augment_structure_module = context_module.name  # type: ignore[attr-defined]
    tlist: YangStatementList = target  # type: ignore[assignment]
    for copied in copies:
        tlist.statements.append(copied)
    invocation._rfc8791_applied = True  # type: ignore[attr-defined]
    if foreign and getattr(invocation, "_rfc8791_root", False):
        invocation._rfc8791_foreign = True  # type: ignore[attr-defined]
    return None
