"""Path-based refine application for ``uses`` expansion."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import List, cast

from .errors import YangRefineTargetNotFoundError
from .ast import (
    YangAnydataStmt,
    YangAnyxmlStmt,
    YangCaseStmt,
    YangChoiceStmt,
    YangContainerStmt,
    YangLeafListStmt,
    YangLeafStmt,
    YangListStmt,
    YangRefineStmt,
    YangStatement,
    YangStatementWithMust,
    YangStatementWithWhen,
    YangUsesStmt,
)

logger = logging.getLogger(__name__)


def statement_children(stmt: YangStatement) -> list[YangStatement]:
    """Direct schema children (choice branches flatten to case bodies)."""
    if isinstance(stmt, YangChoiceStmt):
        ch: list[YangStatement] = []
        for c in stmt.cases:
            ch.extend(c.statements)
        return ch
    return list(stmt.statements)


def find_nodes_by_refine_path(
    statements: list[YangStatement], target_path: str
) -> list[YangStatement]:
    """Resolve a descendant path (``a/b/c``) from roots; walk through choices/cases."""
    segments = [p for p in target_path.split("/") if p]
    if not segments:
        return []
    out: list[YangStatement] = []
    for root in statements:
        out.extend(_find_from_node(root, segments, 0))
    return out


def _find_from_node(
    stmt: YangStatement, segments: list[str], idx: int
) -> list[YangStatement]:
    want = segments[idx]
    last = idx == len(segments) - 1
    if getattr(stmt, "name", None) == want:
        if last:
            return [stmt]
        # A refine path may name the case after the choice (e.g. .../field-type-choice/composite-case/composite).
        # statement_children() flattens choice branches and drops case nodes, so we must walk cases by name.
        if isinstance(stmt, YangChoiceStmt) and idx + 1 < len(segments):
            case_name = segments[idx + 1]
            matches: list[YangStatement] = []
            for case in stmt.cases:
                if case.name == case_name:
                    case_last = idx + 1 == len(segments) - 1
                    if case_last:
                        return [case]
                    for ch in case.statements:
                        matches.extend(_find_from_node(ch, segments, idx + 2))
            return matches
        matches = []
        for ch in statement_children(stmt):
            matches.extend(_find_from_node(ch, segments, idx + 1))
        return matches
    # Refine paths follow the schema tree: choice/case nodes may appear as segments.
    if isinstance(stmt, YangChoiceStmt):
        for case in stmt.cases:
            if case.name == want:
                if last:
                    return [case]
                case_matches: list[YangStatement] = []
                for ch in case.statements:
                    case_matches.extend(_find_from_node(ch, segments, idx + 1))
                return case_matches
    matches = []
    for ch in statement_children(stmt):
        matches.extend(_find_from_node(ch, segments, idx))
    return matches


def apply_refines_list_cardinality(
    statements: list[YangStatement], refines: list[YangRefineStmt]
) -> None:
    """Apply only ``min-elements`` / ``max-elements`` from refines to matching lists.

    Callers must ensure refine target paths are already visible (nested ``uses``
    expanded first); see ``uses_expand`` preprocessing.
    """
    for r in refines:
        if r.min_elements is None and r.max_elements is None:
            continue
        nodes = find_nodes_by_refine_path(statements, r.target_path)
        if not nodes:
            raise YangRefineTargetNotFoundError(r.target_path)
        for node in nodes:
            if isinstance(node, (YangListStmt, YangLeafListStmt)):
                if r.min_elements is not None:
                    node.min_elements = r.min_elements
                if r.max_elements is not None:
                    node.max_elements = r.max_elements


def apply_refines_by_path(
    statements: list[YangStatement], refines: list[YangRefineStmt]
) -> None:
    """Apply type, must, min/max-elements refinements to all nodes matching each path."""
    for r in refines:
        nodes = find_nodes_by_refine_path(statements, r.target_path)
        if not nodes:
            raise YangRefineTargetNotFoundError(r.target_path)
        for node in nodes:
            apply_refine_to_node(node, r)


def apply_refine_to_node(stmt: YangStatement, refine: YangRefineStmt) -> None:
    if getattr(refine, "type", None) is not None and isinstance(stmt, YangLeafStmt):
        stmt.type = refine.type
        logger.debug("refine applied type: stmt=%r refine=%r", stmt, refine)
    rm = getattr(refine, "refined_mandatory", None)
    if rm is not None:
        if isinstance(stmt, YangLeafStmt):
            stmt.mandatory = rm
            logger.debug("refine applied mandatory: stmt=%r mandatory=%r", stmt, rm)
        elif isinstance(stmt, YangChoiceStmt):
            stmt.mandatory = rm
            logger.debug("refine applied mandatory: choice=%r mandatory=%r", stmt, rm)
    if isinstance(stmt, YangStatementWithMust):
        for refine_must in refine.must_statements:
            stmt.must_statements.append(refine_must)
            logger.debug(
                "refine applied must: stmt=%r added_must=%r refine=%r",
                stmt,
                refine_must,
                refine,
            )
    if isinstance(stmt, (YangListStmt, YangLeafListStmt)):
        if refine.min_elements is not None:
            stmt.min_elements = refine.min_elements
            logger.debug(
                "refine applied min-elements: stmt=%r min_elements=%r refine=%r",
                stmt,
                stmt.min_elements,
                refine,
            )
        if refine.max_elements is not None:
            stmt.max_elements = refine.max_elements
            logger.debug(
                "refine applied max-elements: stmt=%r max_elements=%r refine=%r",
                stmt,
                stmt.max_elements,
                refine,
            )
    if refine.if_features and isinstance(stmt, YangStatementWithWhen):
        stmt.if_features.extend(refine.if_features)


def copy_yang_statement(stmt: YangStatement) -> YangStatement:
    """Deep copy of a YANG statement subtree (for ``uses`` expansion without mutating groupings).

    ``dataclasses.replace`` keeps shared references (``type``, ``when``, …) and only
    substitutes containers that must be independent after expansion.
    """
    statements = [copy_yang_statement(s) for s in stmt.statements]

    if isinstance(stmt, YangChoiceStmt):
        cases = [cast(YangCaseStmt, copy_yang_statement(c)) for c in stmt.cases]
        return replace(
            stmt,
            statements=statements,
            cases=cases,
            if_features=list(stmt.if_features),
        )
    if isinstance(stmt, YangCaseStmt):
        return replace(
            stmt,
            statements=statements,
            if_features=list(stmt.if_features),
        )
    if isinstance(stmt, YangUsesStmt):
        refines = list(stmt.refines) if stmt.refines else []
        return replace(
            stmt,
            statements=statements,
            refines=refines,
            if_features=list(stmt.if_features),
        )
    if isinstance(
        stmt,
        (
            YangContainerStmt,
            YangListStmt,
            YangLeafStmt,
            YangLeafListStmt,
            YangAnydataStmt,
            YangAnyxmlStmt,
        ),
    ):
        must = list(stmt.must_statements) if stmt.must_statements else []
        return replace(
            stmt,
            statements=statements,
            must_statements=must,
            if_features=list(stmt.if_features),
        )
    raise TypeError(f"Unsupported statement type for copy: {type(stmt).__name__}")
