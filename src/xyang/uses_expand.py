"""Expand ``uses`` statements and apply refines."""

from __future__ import annotations

import logging

from .ast import YangChoiceStmt, YangLeafListStmt, YangListStmt, YangStatement, YangUsesStmt
from .errors import YangCircularUsesError, YangRefineTargetNotFoundError
from .module import YangModule
from .refine_expand import (
    apply_refine_to_node,
    copy_yang_statement,
    uses_refine_fingerprint,
)

logger = logging.getLogger(__name__)

# Set logging.getLogger("xyang.uses_expand").setLevel(logging.DEBUG) to trace
# ``must false()`` / refine interaction and ``uses`` expansion cycles.


def _must_expressions(stmt: YangStatement) -> tuple[str, ...]:
    """Snapshot of ``must`` XPath strings on *stmt* (for debug)."""
    musts = getattr(stmt, "must_statements", None) or []
    return tuple((getattr(m, "expression", "") or "").strip() for m in musts)


def _debug_array_branch(stmt: YangStatement, stmt_path: str, phase: str) -> None:
    """Log state of the explicit ``field_type`` array container (refine target tail ``.../array-case/array``)."""
    if not logger.isEnabledFor(logging.DEBUG):
        return
    if not stmt_path.endswith("/array-case/array"):
        return
    kind = type(stmt).__name__
    logger.debug(
        "uses_expand array-branch %s: stmt_path=%r kind=%s has_must_false=%s musts=%s",
        phase,
        stmt_path,
        kind,
        stmt.has_must_false(),
        _must_expressions(stmt),
    )


def _extend_refine_path(prefix: str, segment: str) -> str:
    return f"{prefix}/{segment}" if prefix else segment


def _refine_target_matches_stmt_path(target_path: str, stmt_path: str) -> bool:
    """True if a ``refine`` *target_path* designates *stmt_path* (relative path suffix)."""
    if not target_path or not stmt_path:
        return False
    if stmt_path == target_path:
        return True
    return stmt_path.endswith("/" + target_path)


def _expand_one_uses_stmt(
    stmt: YangUsesStmt,
    module: YangModule,
    expanding_chain: tuple[tuple[str, tuple], ...],
    refine_path_prefix: str,
) -> list[YangStatement]:
    gname = stmt.grouping_name
    grouping = module.get_grouping(gname)
    if not grouping:
        logger.warning(
            "Grouping '%s' not found when expanding uses statement", gname
        )
        return []
    link = (gname, uses_refine_fingerprint(stmt.refines))
    if link in expanding_chain:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "uses_expand circular uses: grouping=%r fingerprint=%s chain=%s",
                gname,
                link[1],
                tuple((x[0], x[1]) for x in expanding_chain),
            )
        raise YangCircularUsesError(expanding_chain, link)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "uses_expand enter uses: grouping=%r fingerprint=%s chain_depth=%d pending_refines=%d",
            gname,
            link[1],
            len(expanding_chain),
            len(stmt.refines),
        )
    inner_chain = expanding_chain + (link,)
    body = [copy_yang_statement(s) for s in grouping.statements]
    pending_refines = list(stmt.refines)
    # Prefix is the schema path to the ``uses`` insertion point so refine target paths
    # (relative to the used grouping) match stmt_path while walking nested ``uses``.
    out = expand_uses_in_statements(
        body,
        module,
        inner_chain,
        pending_refines,
        refine_path_prefix,
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
    expanding_chain: tuple[tuple[str, tuple], ...],
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

        if refines:
            i = len(refines)
            while i:
                i -= 1
                r = refines[i]
                tp = getattr(r, "target_path", None) or ""
                if _refine_target_matches_stmt_path(tp, stmt_path):
                    must_before = _must_expressions(stmt)
                    apply_refine_to_node(stmt, r)
                    if logger.isEnabledFor(logging.DEBUG):
                        added = tuple(
                            (getattr(m, "expression", "") or "").strip()
                            for m in (getattr(r, "must_statements", None) or [])
                        )
                        logger.debug(
                            "uses_expand applied refine: target_path=%r stmt_path=%r "
                            "node=%s must_before=%s must_after=%s refine_musts=%s",
                            tp,
                            stmt_path,
                            type(stmt).__name__,
                            must_before,
                            _must_expressions(stmt),
                            added,
                        )
                    del refines[i]

        _debug_array_branch(stmt, stmt_path, "after_refines")

        # ``must false()`` marks a subtree as unreachable in the schema. Do not expand nested
        # ``uses`` or recurse into children—same rationale as skipping list bodies with
        # ``max-elements 0``: avoids infinite or cyclic grouping expansion when a refine
        # rules out a branch (e.g. disallowing ``field_type`` array under a specific ``uses``).
        if stmt.has_must_false():
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "uses_expand skip must_false: stmt_path=%r kind=%s musts=%s",
                    stmt_path,
                    type(stmt).__name__,
                    _must_expressions(stmt),
                )
            expanded.append(stmt)
            continue

        _debug_array_branch(stmt, stmt_path, "expand_children")

        if isinstance(stmt, YangUsesStmt):
            repl = _expand_one_uses_stmt(stmt, module, expanding_chain, stmt_path)
            repl = expand_uses_in_statements(
                repl,
                module,
                expanding_chain,
                refines,
                stmt_path,
            )
            expanded.extend(repl)
        elif isinstance(stmt, YangChoiceStmt):
            choice_prefix = stmt_path
            for case in stmt.cases:
                case_prefix = _extend_refine_path(choice_prefix, case.name)
                case.statements = expand_uses_in_statements(
                    case.statements,
                    module,
                    expanding_chain,
                    refines,
                    case_prefix,
                )
            expanded.append(stmt)
        elif isinstance(stmt, (YangListStmt, YangLeafListStmt)):
            # Refines (or the grouping) may set max-elements 0. Do not walk list/leaf-list
            # children: no instances are allowed, and nested ``uses`` inside the list must
            # not be expanded (breaks apparent grouping cycles, e.g. refine on this list).
            if getattr(stmt, "max_elements", None) == 0:
                expanded.append(stmt)
            else:
                stmt.statements = expand_uses_in_statements(
                    stmt.statements,
                    module,
                    expanding_chain,
                    refines,
                    stmt_path,
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
