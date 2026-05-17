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
    """Return *dispatch* with ``description`` and ``reference`` handlers (if not already set)."""
    out = dict(dispatch)
    out.setdefault(kw.DESCRIPTION, parsers.parse_description)
    out.setdefault(kw.REFERENCE, parsers.parse_reference)
    return out


def with_data_node_substatements(
    parsers: StatementParsers,
    dispatch: dict[str, Callable[..., Any]],
) -> dict[str, Callable[..., Any]]:
    """Like :func:`with_metadata_substatements`, plus ignored ``config`` (warning only)."""
    out = with_metadata_substatements(parsers, dispatch)
    out.setdefault(kw.CONFIG, parsers.parse_config_ignored)
    return out
