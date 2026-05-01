"""Semantic validation passes for parsed, effective YANG modules."""

from __future__ import annotations

from collections.abc import Iterable

from .ast import YangChoiceStmt, YangLeafStmt, YangListStmt, YangStatement
from .errors import YangSemanticError
from .module import YangModule


def _iter_effective_statements(statements: Iterable[YangStatement]) -> Iterable[YangStatement]:
    for stmt in statements:
        yield stmt
        if isinstance(stmt, YangChoiceStmt):
            for case in stmt.cases:
                yield from _iter_effective_statements(case.statements)
        yield from _iter_effective_statements(stmt.statements)


def _validate_list_key_constraints(module: YangModule) -> None:
    for stmt in _iter_effective_statements(module.statements):
        if not isinstance(stmt, YangListStmt) or not stmt.key:
            continue
        key_leaves = {
            child.name: child
            for child in stmt.statements
            if isinstance(child, YangLeafStmt)
        }
        for key_name in stmt.key.split():
            child = key_leaves.get(key_name)
            if child is None:
                raise YangSemanticError(
                    f"List {stmt.name!r}: key leaf {key_name!r} does not exist "
                    "(RFC 7950: each list key name must refer to a child leaf)."
                )
            if child.when is not None:
                illegal = "when"
            elif child.if_features:
                illegal = "if-feature"
            else:
                illegal = None
            if illegal is None:
                continue
            raise YangSemanticError(
                f"List {stmt.name!r}: key leaf {child.name!r} must not have "
                f"{illegal!r} (RFC 7950: 'when' and 'if-feature' are illegal on list keys)."
            )


def validate_semantics(module: YangModule) -> None:
    """Run semantic checks that require the effective post-expansion schema tree."""
    _validate_list_key_constraints(module)
