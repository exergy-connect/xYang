"""Dispatch configuration for ``StatementParsers._parse_statement``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import AbstractSet, Optional

from ..ast import YangTypeStmt


@dataclass(frozen=True)
class StatementDispatchSpec:
    """How to parse one substatement: registry lookup, optional allowlist, type body."""

    registry_prefix: str
    unsupported_context: str
    allowed_keywords: Optional[AbstractSet[str]] = None
    type_stmt: Optional[YangTypeStmt] = None
    #: If set, use this prefix for ``{prefix}:{keyword}`` lookups instead of ``registry_prefix``.
    registry_key_prefix: Optional[str] = None
    #: If True, when the keyword is not in ``allowed_keywords``, try unsupported-skip before error.
    try_skip_when_disallowed: bool = False
    #: If set, try ``{fallback}:{keyword}`` when the primary registry key has no handler.
    fallback_registry_key_prefix: Optional[str] = None
