"""
Thin wrappers over the keyword groups in :mod:`xyang.parser.dispatch_registry`.

Prefer the registry. These helpers remain so a caller can still merge the
metadata or data-node keywords into a handler map.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from . import keywords as kw
from .dispatch_registry import DATA_NODE_SUBSTATEMENTS, METADATA_SUBSTATEMENTS

if TYPE_CHECKING:
    from .statement_parsers import StatementParsers


def _metadata_handlers(parsers: StatementParsers) -> dict[str, Callable[..., Any]]:
    return {
        kw.DESCRIPTION: parsers.parse_description,
        kw.REFERENCE: parsers.parse_reference,
        kw.UNITS: parsers.parse_units,
        kw.STATUS: parsers.parse_status_ignored,
    }


def with_metadata_substatements(
    parsers: StatementParsers,
    dispatch: dict[str, Callable[..., Any]],
) -> dict[str, Callable[..., Any]]:
    """Return *dispatch* with the metadata keyword group."""
    out = dict(dispatch)
    handlers = _metadata_handlers(parsers)
    for key in METADATA_SUBSTATEMENTS:
        out.setdefault(key, handlers[key])
    return out


def with_data_node_substatements(
    parsers: StatementParsers,
    dispatch: dict[str, Callable[..., Any]],
) -> dict[str, Callable[..., Any]]:
    """Return *dispatch* with the data-node keyword group (metadata, config, typedef)."""
    out = with_metadata_substatements(parsers, dispatch)
    for key in DATA_NODE_SUBSTATEMENTS - METADATA_SUBSTATEMENTS:
        if key == kw.CONFIG:
            out.setdefault(key, parsers.parse_config)
        elif key == kw.TYPEDEF:
            out.setdefault(key, parsers.parse_typedef)
    return out
