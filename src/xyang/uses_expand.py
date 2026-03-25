"""Expand ``uses`` statements and apply refines."""

from __future__ import annotations

import logging

from .ast import (
    YangChoiceStmt,
    YangLeafListStmt,
    YangListStmt,
    YangStatement,
    YangUsesStmt,
)
from .errors import YangCircularUsesError, YangRefineTargetNotFoundError
from .module import YangModule
from .refine_expand import (
    apply_refine_to_node,
    copy_yang_statement,
    uses_refine_fingerprint,
)

logger = logging.getLogger(__name__)


def _extend_refine_path(prefix: str, segment: str) -> str:
    return f"{prefix}/{segment}" if prefix else segment


def _refine_target_matches_stmt_path(target_path: str, stmt_path: str) -> bool:
    """True if *target_path* matches *stmt_path* (equality or relative-path suffix).

    *stmt_path* uses the enclosing walk's ``refine_path_prefix`` through nested ``uses`` so
    pending refines from an outer ``uses`` (e.g. ``list-composite``) still match after inner
    grouping roots are expanded (suffix match, RFC 7950 refine paths).
    """
    if not target_path or not stmt_path:
        logger.debug(
            "refine path match skip: empty target_path=%r stmt_path=%r",
            target_path,
            stmt_path,
        )
        return False
    if stmt_path == target_path:
        logger.debug(
            "refine path match exact: target_path=%r stmt_path=%r",
            target_path,
            stmt_path,
        )
        return True
    matched = stmt_path.endswith("/" + target_path)
    logger.debug(
        "refine path match suffix: target_path=%r stmt_path=%r -> %s",
        target_path,
        stmt_path,
        matched,
    )
    return matched


def _expand_one_uses_stmt(
    stmt: YangUsesStmt,
    module: YangModule,
    expanding_chain: tuple[tuple[str, tuple], ...],
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
    link = (gname, uses_refine_fingerprint(stmt.refines))
    if link in expanding_chain:
        logger.debug(
            "circular uses detected: chain=%r repeated_link=%r",
            expanding_chain,
            link,
        )
        raise YangCircularUsesError(expanding_chain, link)
    inner_chain = expanding_chain + (link,)
    body = [copy_yang_statement(s) for s in grouping.statements]
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
                    apply_refine_to_node(stmt, r)
                    del refines[i]

        # ``must false()`` marks a subtree as unreachable in the schema. Do not expand nested
        # ``uses`` or recurse into children—same rationale as skipping list bodies with
        # ``max-elements 0``: avoids infinite or cyclic grouping expansion when a refine
        # rules out a branch (e.g. disallowing ``field_type`` array under a specific ``uses``).
        if stmt.has_must_false():
            expanded.append(stmt)
            continue

        if isinstance(stmt, YangUsesStmt):
            repl = _expand_one_uses_stmt(
                stmt, module, expanding_chain, refine_path_prefix, refines
            )
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
                logger.debug(
                    "skip expanding children for %s %r at stmt_path=%r because max-elements=0",
                    type(stmt).__name__,
                    getattr(stmt, "name", None),
                    stmt_path,
                )
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
