"""Expand ``uses`` statements and apply refines."""

from __future__ import annotations

import logging

from .ast import (
    YangChoiceStmt,
    YangStatement,
    YangStatementWithWhen,
    YangUsesStmt,
    YangWhenStmt,
)
from .errors import YangCircularUsesError, YangRefineTargetNotFoundError
from .module import YangModule
from .refine_expand import apply_refine_to_node, copy_yang_statement

logger = logging.getLogger(__name__)


def _extend_refine_path(prefix: str, segment: str) -> str:
    return f"{prefix}/{segment}" if prefix else segment


def _merge_uses_when_into_grouping_roots(
    roots: list[YangStatement],
    uses_when: YangWhenStmt | None,
) -> None:
    """RFC 7950: ``when`` on ``uses`` is ANDed onto each top-level node from the grouping."""
    if uses_when is None:
        return
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
                    expression=merged_expr, description=merged_desc
                )


def _refine_target_matches_stmt_path(target_path: str, stmt_path: str) -> bool:
    """True if *target_path* matches *stmt_path* (equality or relative-path suffix).

    *stmt_path* uses the enclosing walk's ``refine_path_prefix`` through nested ``uses`` so
    pending refines from an outer ``uses`` (e.g. ``list-composite``) still match after inner
    grouping roots are expanded (suffix match, RFC 7950 refine paths).
    """
    if not target_path or not stmt_path:
        return False
    if stmt_path == target_path:
        return True
    return stmt_path.endswith("/" + target_path)


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
        tp = getattr(r, "target_path", None) or ""
        if _refine_target_matches_stmt_path(tp, stmt_path):
            apply_refine_to_node(stmt, r)
            del refines[i]


def _expand_one_uses_stmt(
    stmt: YangUsesStmt,
    module: YangModule,
    expanding_chain: tuple[str, ...],
    refine_path_prefix: str,
    sibling_refines: list,
) -> list[YangStatement]:
    gname = stmt.grouping_name
    grouping = module.get_grouping(gname)
    if not grouping:
        logger.warning(
            "Grouping '%s' not found when expanding uses statement", gname
        )
        return []
    if gname in expanding_chain:
        logger.debug(
            "circular uses detected: chain=%r repeated=%r",
            expanding_chain,
            gname,
        )
        raise YangCircularUsesError(expanding_chain, gname)
    inner_chain = expanding_chain + (gname,)
    body = [copy_yang_statement(s) for s in grouping.statements]
    _merge_uses_when_into_grouping_roots(body, stmt.when)
    pending_refines = list(stmt.refines)
    inner_prefix = refine_path_prefix if sibling_refines else ""
    # Own refines are relative to the used grouping: inner prefix "" (e.g. ``composite/...``).
    # If sibling ``refines`` still hold ancestor pending refines, keep enclosing prefix so
    # targets like ``composite/...`` match inside nested ``uses`` (e.g. ``composite-field``).
    out = expand_uses_in_statements(
        body,
        module,
        inner_chain,
        pending_refines,
        inner_prefix,
    )
    if pending_refines:
        raise YangRefineTargetNotFoundError(pending_refines[0].target_path)
    return out


def expand_all_uses_in_module(module: YangModule) -> None:
    """Expand every ``uses`` on the module and on each grouping.

    Called from :mod:`xyang.parser.yang_parser` when a module parse finishes
    (see ``YangParser.parse_string``).
    """
    module.statements = expand_uses_in_statements(
        module.statements, module, (), []
    )
    for _name, grouping in module.groupings.items():
        grouping.statements = expand_uses_in_statements(
            grouping.statements, module, (), []
        )


def expand_uses_in_statements(
    statements: list[YangStatement],
    module: YangModule,
    expanding_chain: tuple[str, ...],
    refines: list,
    refine_path_prefix: str = "",
) -> list[YangStatement]:
    expanded: list[YangStatement] = []
    for stmt in statements:
        segment = stmt.get_schema_node()
        stmt_path = (
            _extend_refine_path(refine_path_prefix, segment)
            if segment
            else refine_path_prefix
        )
        _apply_refines_matching_path(stmt, stmt_path, refines)

        if isinstance(stmt, YangUsesStmt):
            body = _expand_one_uses_stmt(
                stmt, module, expanding_chain, refine_path_prefix, refines
            )
            expanded.extend(
                expand_uses_in_statements(
                    body, module, expanding_chain, refines, stmt_path
                )
            )
        elif isinstance(stmt, YangChoiceStmt):
            for case in stmt.cases:
                case_prefix = _extend_refine_path(stmt_path, case.name)
                case.statements = expand_uses_in_statements(
                    case.statements,
                    module,
                    expanding_chain,
                    refines,
                    case_prefix,
                )
            expanded.append(stmt)
        elif hasattr(stmt, "statements"):
            stmt.statements = expand_uses_in_statements(
                stmt.statements,
                module,
                expanding_chain,
                refines,
                stmt_path,
            )
            expanded.append(stmt)
        else:
            expanded.append(stmt)
    return expanded
