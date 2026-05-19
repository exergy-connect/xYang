"""Path-based refine application for ``uses`` expansion."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Callable, cast

from .errors import YangRefineTargetNotFoundError
from .xpath.ast import PathNode
from .ast import (
    YangAnydataStmt,
    YangAnyxmlStmt,
    YangAugmentStmt,
    YangCaseStmt,
    YangChoiceStmt,
    YangContainerStmt,
    YangExtensionInvocationStmt,
    YangExtensionStmt,
    YangLeafListStmt,
    YangLeafStmt,
    YangListStmt,
    YangRefineStmt,
    YangStatement,
    YangStatementWithMust,
    YangStatementWithWhen,
    YangTypedefStmt,
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
    statements: list[YangStatement], target_path: PathNode
) -> list[YangStatement]:
    """Resolve a descendant path (``a/b/c``) from roots; walk through choices/cases."""
    if not target_path.segments:
        return []
    segments = [seg.step for seg in target_path.segments]
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
            raise YangRefineTargetNotFoundError(
                r.target_path.to_string()
            )
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
            raise YangRefineTargetNotFoundError(
                r.target_path.to_string()
            )
        for node in nodes:
            apply_refine_to_node(node, r)


def _apply_refine_type(stmt: YangStatement, refine: YangRefineStmt) -> None:
    if getattr(refine, "type", None) is not None and isinstance(stmt, YangLeafStmt):
        stmt.type = refine.type
        logger.debug("refine applied type: stmt=%r refine=%r", stmt, refine)


def _apply_refine_mandatory(stmt: YangStatement, refine: YangRefineStmt) -> None:
    rm = getattr(refine, "refined_mandatory", None)
    if rm is None:
        return
    if isinstance(stmt, YangLeafStmt):
        stmt.mandatory = rm
        logger.debug("refine applied mandatory: stmt=%r mandatory=%r", stmt, rm)
    elif isinstance(stmt, YangChoiceStmt):
        stmt.mandatory = rm
        logger.debug("refine applied mandatory: choice=%r mandatory=%r", stmt, rm)


def _apply_refine_defaults(stmt: YangStatement, refine: YangRefineStmt) -> None:
    rds = getattr(refine, "refined_defaults", None) or []
    if not rds:
        return
    if isinstance(stmt, YangLeafStmt):
        stmt.default = rds[0]
        logger.debug(
            "refine applied default: stmt=%r default=%r refine=%r",
            stmt,
            stmt.default,
            refine,
        )
    elif isinstance(stmt, YangLeafListStmt):
        stmt.defaults = list(rds)
        logger.debug(
            "refine applied defaults: stmt=%r defaults=%r refine=%r",
            stmt,
            stmt.defaults,
            refine,
        )


def _apply_refine_must(stmt: YangStatement, refine: YangRefineStmt) -> None:
    if not isinstance(stmt, YangStatementWithMust):
        return
    for refine_must in refine.must_statements:
        stmt.must_statements.append(refine_must)
        logger.debug(
            "refine applied must: stmt=%r added_must=%r refine=%r",
            stmt,
            refine_must,
            refine,
        )


def _apply_refine_cardinality(stmt: YangStatement, refine: YangRefineStmt) -> None:
    if not isinstance(stmt, (YangListStmt, YangLeafListStmt)):
        return
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


def apply_refine_to_node(stmt: YangStatement, refine: YangRefineStmt) -> None:
    """Apply one ``refine`` statement to a resolved schema node."""
    _apply_refine_type(stmt, refine)
    _apply_refine_mandatory(stmt, refine)
    _apply_refine_defaults(stmt, refine)
    _apply_refine_must(stmt, refine)
    _apply_refine_cardinality(stmt, refine)
    if refine.if_features and isinstance(stmt, YangStatementWithWhen):
        stmt.if_features.extend(refine.if_features)
    refined_desc = (refine.description or "").strip()
    if refined_desc:
        stmt.description = refined_desc


def _copy_with_if_features(
    stmt: YangStatement, statements: list[YangStatement], **extra: object
) -> YangStatement:
    return replace(
        stmt,
        statements=statements,
        if_features=list(stmt.if_features),
        **extra,
    )


def _copy_choice(
    stmt: YangChoiceStmt, statements: list[YangStatement]
) -> YangStatement:
    cases = [cast(YangCaseStmt, copy_yang_statement(c)) for c in stmt.cases]
    return _copy_with_if_features(stmt, statements, cases=cases)


def _copy_uses(stmt: YangUsesStmt, statements: list[YangStatement]) -> YangStatement:
    refines = list(stmt.refines) if stmt.refines else []
    augmentations = [copy_yang_statement(a) for a in stmt.augmentations]
    return _copy_with_if_features(
        stmt, statements, refines=refines, augmentations=augmentations
    )


def _copy_extension_stmt(
    stmt: YangStatement, statements: list[YangStatement]
) -> YangStatement:
    return replace(stmt, statements=statements)


def _copy_typedef_stmt(
    stmt: YangStatement, statements: list[YangStatement]
) -> YangStatement:
    return replace(stmt, statements=statements)


def _copy_with_must(
    stmt: YangStatement, statements: list[YangStatement]
) -> YangStatement:
    must = list(stmt.must_statements) if stmt.must_statements else []
    return _copy_with_if_features(stmt, statements, must_statements=must)


def copy_yang_statement(stmt: YangStatement) -> YangStatement:
    """Deep copy of a YANG statement subtree (for ``uses`` expansion without mutating groupings).

    ``dataclasses.replace`` keeps shared references (``type``, ``when``, …) and only
    substitutes containers that must be independent after expansion.
    """
    statements = [copy_yang_statement(s) for s in stmt.statements]
    copiers: dict[type, Callable[[YangStatement, list[YangStatement]], YangStatement]] = {
        YangChoiceStmt: _copy_choice,
        YangCaseStmt: _copy_with_if_features,
        YangUsesStmt: _copy_uses,
        YangContainerStmt: _copy_with_must,
        YangListStmt: _copy_with_must,
        YangLeafStmt: _copy_with_must,
        YangLeafListStmt: _copy_with_must,
        YangAnydataStmt: _copy_with_must,
        YangAnyxmlStmt: _copy_with_must,
        YangAugmentStmt: _copy_with_if_features,
        YangExtensionInvocationStmt: _copy_with_must,
        YangExtensionStmt: _copy_extension_stmt,
        YangTypedefStmt: _copy_typedef_stmt,
    }
    copier = copiers.get(type(stmt))
    if copier is not None:
        return copier(stmt, statements)
    raise TypeError(f"Unsupported statement type for copy: {type(stmt).__name__}")
