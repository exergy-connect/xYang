"""
Helpers for RFC 7950 ``description`` / ``reference`` substatements on schema nodes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from . import keywords as kw

if TYPE_CHECKING:
    from .statement_parsers import StatementParsers


def with_metadata_substatements(
    parsers: StatementParsers,
    dispatch: dict[str, Callable[..., Any]],
) -> dict[str, Callable[..., Any]]:
    """Return *dispatch* with common RFC 7950 metadata substatement handlers."""
    out = dict(dispatch)
    out.setdefault(kw.DESCRIPTION, parsers.parse_description)
    out.setdefault(kw.REFERENCE, parsers.parse_reference)
    out.setdefault(kw.UNITS, parsers.parse_units)
    # RFC 7950 §7.21.2 — allowed on typedef, grouping, feature, data defs, etc.
    out.setdefault(kw.STATUS, parsers.parse_status_ignored)
    return out


def with_data_node_substatements(
    parsers: StatementParsers,
    dispatch: dict[str, Callable[..., Any]],
) -> dict[str, Callable[..., Any]]:
    """Like :func:`with_metadata_substatements`, plus ``config`` (RFC 7950 §7.21.1)."""
    out = with_metadata_substatements(parsers, dispatch)
    out.setdefault(kw.CONFIG, parsers.parse_config)
    out.setdefault(kw.STATUS, parsers.parse_status_ignored)
    # RFC 7950 §7.13 — ``typedef`` allowed in container, list, choice, case, augment, …
    out.setdefault(kw.TYPEDEF, parsers.parse_typedef)
    return out
