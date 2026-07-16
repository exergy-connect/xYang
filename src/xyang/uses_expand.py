"""Expand ``uses`` statements and apply refines."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import cast

from .ast import (
    YangChoiceStmt,
    YangGroupingStmt,
    YangStatement,
    YangStatementList,
    YangStatementWithWhen,
    YangTypedefStmt,
    YangUsesStmt,
    YangWhenStmt,
)
from .errors import YangCircularUsesError, YangRefineTargetNotFoundError, YangSyntaxError
from .module import YangModule
from .refine_expand import apply_refine_to_node, copy_yang_statement, find_nodes_by_refine_path
from .xpath import XPathParser
from .xpath.ast import PathNode

logger = logging.getLogger(__name__)


@dataclass
class ExpandUsesContext:
    """Mutable expansion state for ``expand_uses_in_statements``."""

    module: YangModule
    expanding_chain: tuple[str, ...] = ()
    refines: list | None = None
    refine_path_prefix: str = ""
    typedef_target: YangModule | None = None

    def __post_init__(self) -> None:
        if self.refines is None:
            self.refines = []

    @property
    def reg_module(self) -> YangModule:
        return self.typedef_target if self.typedef_target is not None else self.module


def _extend_refine_path(prefix: str, segment: str) -> str:
    return f"{prefix}/{segment}" if prefix else segment


def _register_typedef_for_uses(
    target: YangModule,
    source: YangModule,
    td: YangTypedefStmt,
) -> None:
    """Expose a grouping typedef on the module where ``uses`` is expanded (RFC 7950 scoping)."""
    name = td.name
    if name in target.typedefs:
        return
    if target is source:
        target.typedefs[name] = source.typedefs.get(name, td)
        return
    resolved = source.typedefs.get(name, td)
    target.typedefs[name] = cast(YangTypedefStmt, copy_yang_statement(resolved))


def _register_grouping_typedefs(
    target: YangModule,
    source: YangModule,
    grouping: YangGroupingStmt,
) -> None:
    """Register typedefs from a grouping onto the module that instantiates ``uses``."""
    for td_name in grouping.typedef_names:
        td = source.typedefs.get(td_name)
        if td is not None:
            _register_typedef_for_uses(target, source, td)
    for s in grouping.statements:
        if isinstance(s, YangTypedefStmt):
            _register_typedef_for_uses(target, source, s)


def _grouping_body_without_typedefs(
    target: YangModule,
    source: YangModule,
    grouping: YangGroupingStmt,
) -> list[YangStatement]:
    """Copy grouping data nodes; register typedefs on *target* first."""
    _register_grouping_typedefs(target, source, grouping)
    return [
        copy_yang_statement(s)
        for s in grouping.statements
        if not isinstance(s, YangTypedefStmt)
    ]


def _merge_uses_if_features_into_grouping_roots(
    roots: list[YangStatement],
    uses_if_features: list[str],
) -> None:
    """RFC 7950 §7.13.1: ``if-feature`` on ``uses`` ANDs with each instantiated grouping root."""
    if not uses_if_features:
        return
    for node in roots:
        if isinstance(node, YangStatementWithWhen):
            node.if_features = [*uses_if_features, *node.if_features]


def _merge_uses_when_into_grouping_roots(
    roots: list[YangStatement],
    uses_when: YangWhenStmt | None,
) -> None:
    """RFC 7950: ``when`` on ``uses`` is ANDed onto each top-level node from the grouping.

    §7.21.5: that ``when`` is evaluated with the **parent of ``uses``** as the context node.
    ``evaluate_with_parent_context`` is set so the validator uses the parent data node.
    """
    if uses_when is None:
        return
    uses_when.evaluate_with_parent_context = True
    for node in roots:
        if isinstance(node, YangStatementWithWhen):
            if node.when is None:
                node.when = uses_when
            else:
                old = node.when
                merged_expr = f"({uses_when.condition}) and ({old.condition})"
                merged_desc = (old.description or "").strip() or (
                    uses_when.description or ""
                ).strip()
                node.when = YangWhenStmt(
                    expression=merged_expr,
                    description=merged_desc,
                    evaluate_with_parent_context=True,
                )


def _refine_target_matches_stmt_path(target_path: PathNode, stmt_path: str) -> bool:
    """True if *target_path* matches *stmt_path* (equality or relative-path suffix).

    *stmt_path* uses the enclosing walk's ``refine_path_prefix`` through nested ``uses`` so
    pending refines from an outer ``uses`` (e.g. ``list-composite``) still match after inner
    grouping roots are expanded (suffix match, RFC 7950 refine paths).
    """
    if not stmt_path:
        return False
    tp = target_path.to_string()
    if not tp:
        return False
    if stmt_path == tp:
        return True
    return stmt_path.endswith("/" + tp)


def _apply_refines_matching_path(
    stmt: YangStatement,
    stmt_path: str,
    refines: list,
) -> None:
    """Pop and apply refines whose target path matches *stmt_path* (mutates *refines*)."""
    i = len(refines)
    while i:
        i -= 1
        r = refines[i]
        tp = r.target_path
        if _refine_target_matches_stmt_path(tp, stmt_path):
            apply_refine_to_node(stmt, r)
            del refines[i]


def _apply_uses_augmentations(
    body: list[YangStatement],
    uses_stmt: YangUsesStmt,
    grouping_name: str,
) -> None:
    """RFC 7950 §7.17: merge ``augment`` substatements on ``uses`` into the expanded grouping."""
    for aug in uses_stmt.augmentations:
        try:
            path_node = XPathParser(aug.augment_path).parse_path()
        except Exception as exc:
            raise YangSyntaxError(
                f"uses '{grouping_name}' augment: invalid path {aug.augment_path!r}: {exc}"
            ) from exc
        targets = find_nodes_by_refine_path(body, path_node)
        if not targets:
            raise YangSyntaxError(
                f"uses '{grouping_name}' augment: no target for path {aug.augment_path!r}"
            )
        if len(targets) != 1:
            raise YangSyntaxError(
                f"uses '{grouping_name}' augment: path {aug.augment_path!r} "
                f"matched {len(targets)} nodes, expected one"
            )
        target = targets[0]
        if not hasattr(target, "statements"):
            raise YangSyntaxError(
                f"uses '{grouping_name}' augment: target {getattr(target, 'name', '?')!r} "
                f"cannot contain schema substatements (path {aug.augment_path!r})"
            )
        copies = [copy_yang_statement(x) for x in aug.statements]
        _merge_uses_if_features_into_grouping_roots(copies, aug.if_features)
        _merge_uses_when_into_grouping_roots(copies, aug.when)
        tlist: YangStatementList = target  # type: ignore[assignment]
        tlist.statements.extend(copies)


def _resolve_uses_grouping(
    stmt: YangUsesStmt, module: YangModule
) -> tuple[str, YangModule, YangStatement] | None:
    """Resolve using parse-time ``grouping_prefix`` + ``grouping_name`` (no string split)."""
    qname = stmt.grouping_qname()
    if stmt.grouping_prefix:
        gmod = module.resolve_prefixed_module(stmt.grouping_prefix)
        lookup_name = stmt.grouping_name
    else:
        gmod = module
        lookup_name = stmt.grouping_name
    if gmod is None:
        return None
    grouping = gmod.get_grouping(lookup_name)
    if grouping is None:
        return None
    return qname, gmod, grouping


def _expand_one_uses_stmt(
    stmt: YangUsesStmt, ctx: ExpandUsesContext
) -> list[YangStatement]:
    resolved = _resolve_uses_grouping(stmt, ctx.module)
    if resolved is None:
        logger.warning(
            "Grouping '%s' not found when expanding uses statement",
            stmt.grouping_qname(),
        )
        return []
    gname, gmod, grouping = resolved
    if gname in ctx.expanding_chain:
        logger.debug(
            "circular uses detected: chain=%r repeated=%r",
            ctx.expanding_chain,
            gname,
        )
        raise YangCircularUsesError(ctx.expanding_chain, gname)
    inner_chain = ctx.expanding_chain + (gname,)
    if isinstance(grouping, YangGroupingStmt):
        body = _grouping_body_without_typedefs(ctx.module, gmod, grouping)
    else:
        body = [copy_yang_statement(s) for s in grouping.statements]
    _merge_uses_if_features_into_grouping_roots(body, stmt.if_features)
    _merge_uses_when_into_grouping_roots(body, stmt.when)
    pending_refines = list(stmt.refines)
    inner_prefix = ctx.refine_path_prefix if ctx.refines else ""
    inner_ctx = ExpandUsesContext(
        module=gmod,
        expanding_chain=inner_chain,
        refines=pending_refines,
        refine_path_prefix=inner_prefix,
        typedef_target=ctx.module,
    )
    out = expand_uses_in_statements(body, inner_ctx)
    if pending_refines:
        raise YangRefineTargetNotFoundError(pending_refines[0].target_path.to_string())
    if stmt.augmentations:
        _apply_uses_augmentations(out, stmt, gname)
    return out


def expand_all_uses_in_module(module: YangModule) -> None:
    """Expand every ``uses`` on the module and on each grouping.

    Called from :mod:`xyang.parser.yang_parser` when a module parse finishes
    (see ``YangParser.parse_string``).
    """
    root = ExpandUsesContext(module=module)
    module.statements = expand_uses_in_statements(module.statements, root)
    for _name, grouping in module.groupings.items():
        grouping.statements = expand_uses_in_statements(grouping.statements, root)


def expand_uses_in_statements(
    statements: list[YangStatement],
    ctx: ExpandUsesContext,
) -> list[YangStatement]:
    """Expand ``uses`` in *statements*.

    Nested typedefs register on ``ctx.typedef_target`` when set.
    """
    expanded: list[YangStatement] = []
    refines = ctx.refines
    assert refines is not None
    for stmt in statements:
        segment = stmt.get_schema_node()
        stmt_path = (
            _extend_refine_path(ctx.refine_path_prefix, segment)
            if segment
            else ctx.refine_path_prefix
        )
        _apply_refines_matching_path(stmt, stmt_path, refines)

        if isinstance(stmt, YangUsesStmt):
            body = _expand_one_uses_stmt(stmt, ctx)
            child_ctx = ExpandUsesContext(
                module=ctx.module,
                expanding_chain=ctx.expanding_chain,
                refines=refines,
                refine_path_prefix=stmt_path,
                typedef_target=ctx.reg_module,
            )
            expanded.extend(expand_uses_in_statements(body, child_ctx))
        elif isinstance(stmt, YangTypedefStmt):
            if ctx.typedef_target is not None:
                _register_typedef_for_uses(ctx.reg_module, ctx.module, stmt)
            else:
                expanded.append(stmt)
            continue
        elif isinstance(stmt, YangChoiceStmt):
            for case in stmt.cases:
                case_prefix = _extend_refine_path(stmt_path, case.name)
                _apply_refines_matching_path(case, case_prefix, refines)
                case_ctx = ExpandUsesContext(
                    module=ctx.module,
                    expanding_chain=ctx.expanding_chain,
                    refines=refines,
                    refine_path_prefix=case_prefix,
                    typedef_target=ctx.reg_module,
                )
                case.statements = expand_uses_in_statements(case.statements, case_ctx)
            expanded.append(stmt)
        elif hasattr(stmt, "statements"):
            child_ctx = ExpandUsesContext(
                module=ctx.module,
                expanding_chain=ctx.expanding_chain,
                refines=refines,
                refine_path_prefix=stmt_path,
                typedef_target=ctx.reg_module,
            )
            stmt.statements = expand_uses_in_statements(stmt.statements, child_ctx)
            expanded.append(stmt)
        else:
            expanded.append(stmt)
    return expanded
