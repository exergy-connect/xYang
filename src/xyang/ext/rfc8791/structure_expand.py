"""RFC 8791 augment-structure apply callback."""

from __future__ import annotations

from ...ast import (
    YangExtensionInvocationStmt,
    YangStatement,
    YangStatementList,
)
from ...augment_expand import resolve_absolute_schema_path
from ...errors import YangSyntaxError
from ...module import YangModule
from ...refine_expand import copy_yang_statement
from ...uses_expand import (
    _merge_uses_if_features_into_grouping_roots,
    _merge_uses_when_into_grouping_roots,
)

_STRUCTURE_INDEX_KEY = "ietf-yang-structure-ext:structure-index"


def _lookup_registered_structure(
    module: YangModule,
    name: str,
) -> YangExtensionInvocationStmt | None:
    idx = module.extension_runtime.get(_STRUCTURE_INDEX_KEY)
    if not isinstance(idx, dict):
        return None
    stmt = idx.get(name)
    return stmt if isinstance(stmt, YangExtensionInvocationStmt) else None


def resolve_augment_structure_target(ctx_module: YangModule, path: str) -> YangStatement:
    """Resolve absolute augment-structure path to its target schema node."""
    return resolve_absolute_schema_path(
        ctx_module=ctx_module,
        path=path,
        kind="augment-structure",
        find_toplevel=_lookup_registered_structure,
    )


def apply_augment_structure_invocation(
    invocation: YangExtensionInvocationStmt,
    *,
    context_module: YangModule,
) -> YangStatement | None:
    """Apply one RFC 8791 augment-structure invocation.

    Returns ``None`` so the invocation node is removed after its effect is applied.
    """
    if not invocation.argument:
        raise YangSyntaxError("augment-structure requires an absolute path argument")
    target = resolve_augment_structure_target(context_module, invocation.argument)
    copies = [copy_yang_statement(x) for x in invocation.statements]
    _merge_uses_if_features_into_grouping_roots(copies, invocation.if_features)
    _merge_uses_when_into_grouping_roots(copies, invocation.when)
    tlist: YangStatementList = target  # type: ignore[assignment]
    for c in copies:
        tlist.statements.append(c)
    return None
