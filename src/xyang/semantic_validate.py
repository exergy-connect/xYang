"""
Post-parse semantic checks that are not encoded in the grammar alone.
"""

from __future__ import annotations

from .ast import (
    YangChoiceStmt,
    YangContainerStmt,
    YangGroupingStmt,
    YangListStmt,
    YangStatement,
)
from .errors import YangSemanticError
from .module import YangModule


def validate_choice_case_unique_child_names(module: YangModule) -> None:
    """RFC 7950 §7.9: case branches share one namespace; identifiers must be unique across cases."""
    for stmt in module.statements:
        _walk(stmt)
    for grouping in module.groupings.values():
        for stmt in grouping.statements:
            _walk(stmt)


def _validate_choice(choice: YangChoiceStmt) -> None:
    seen: dict[str, str] = {}
    for case in choice.cases:
        for sub in case.statements:
            seg = sub.get_schema_node()
            if seg is None:
                continue
            if seg in seen:
                prev_case = seen[seg]
                raise YangSemanticError(
                    f"Choice {choice.name!r}: schema node {seg!r} appears in case "
                    f"{prev_case!r} and again in case {case.name!r} "
                    "(RFC 7950: names of nodes in the cases of a choice must be unique)."
                )
            seen[seg] = case.name


def _walk(stmt: YangStatement) -> None:
    if isinstance(stmt, YangChoiceStmt):
        _validate_choice(stmt)
        for case in stmt.cases:
            for child in case.statements:
                _walk(child)
    elif isinstance(stmt, (YangContainerStmt, YangListStmt, YangGroupingStmt)):
        for child in stmt.statements:
            _walk(child)
