"""Parent statement → allowed substatements.

One frozen table. ``StatementParsers`` builds the keyword→handler maps from it.
The sets are the keywords Python accepts today, including known RFC drift.
Do not "correct" a parent here without a shared case.

Groups:

- ``METADATA_SUBSTATEMENTS``: description, reference, units, status
- ``DATA_NODE_SUBSTATEMENTS``: metadata plus config and typedef
- ``DATA_DEF_SUBSTATEMENTS``: leaf, leaf-list, container, list, choice, anydata, anyxml, uses
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from . import keywords as kw

METADATA_SUBSTATEMENTS = frozenset(
    {kw.DESCRIPTION, kw.REFERENCE, kw.UNITS, kw.STATUS}
)
DATA_NODE_SUBSTATEMENTS = METADATA_SUBSTATEMENTS | frozenset({kw.CONFIG, kw.TYPEDEF})
DATA_DEF_SUBSTATEMENTS = frozenset(
    {
        kw.LEAF,
        kw.LEAF_LIST,
        kw.CONTAINER,
        kw.LIST,
        kw.CHOICE,
        kw.ANYDATA,
        kw.ANYXML,
        kw.USES,
    }
)


@dataclass(frozen=True)
class DispatchParent:
    """RFC 7950 section (or §6.3.1 for an extension invocation) and allowed keywords."""

    rfc: str
    keywords: frozenset[str]


def _parent(rfc: str, *parts: frozenset[str]) -> DispatchParent:
    keywords: set[str] = set()
    for part in parts:
        keywords.update(part)
    return DispatchParent(rfc, frozenset(keywords))


_IO = _parent(
    "7.14.2",
    METADATA_SUBSTATEMENTS,
    DATA_DEF_SUBSTATEMENTS,
    frozenset({kw.TYPEDEF, kw.WHEN, kw.MUST, kw.IF_FEATURE}),
)

# Insertion order is the parity snapshot order. Keep the TypeScript table in this order.
_PARENTS: tuple[tuple[str, DispatchParent], ...] = (
    (
        "module",
        _parent(
            "7.1.1",
            frozenset(
                {
                    kw.LEAF,
                    kw.LIST,
                    kw.LEAF_LIST,
                    kw.CONTAINER,
                    kw.NOTIFICATION,
                    kw.RPC,
                    kw.ANYDATA,
                    kw.ANYXML,
                    kw.TYPEDEF,
                    kw.GROUPING,
                    kw.IMPORT,
                    kw.INCLUDE,
                    kw.REVISION,
                    kw.DESCRIPTION,
                    kw.REFERENCE,
                    kw.FEATURE,
                    kw.IDENTITY,
                    kw.EXTENSION,
                    kw.AUGMENT,
                    kw.DEVIATION,
                    kw.YANG_VERSION,
                    kw.NAMESPACE,
                    kw.PREFIX,
                    kw.ORGANIZATION,
                    kw.CONTACT,
                }
            ),
        ),
    ),
    (
        "submodule",
        _parent(
            "7.2.1",
            frozenset(
                {
                    kw.YANG_VERSION,
                    kw.ORGANIZATION,
                    kw.CONTACT,
                    kw.DESCRIPTION,
                    kw.REFERENCE,
                    kw.IMPORT,
                    kw.INCLUDE,
                    kw.REVISION,
                    kw.FEATURE,
                    kw.EXTENSION,
                    kw.TYPEDEF,
                    kw.IDENTITY,
                    kw.GROUPING,
                    kw.AUGMENT,
                    kw.DEVIATION,
                    kw.CONTAINER,
                    kw.LIST,
                    kw.LEAF,
                    kw.LEAF_LIST,
                    kw.ANYDATA,
                    kw.ANYXML,
                    kw.NOTIFICATION,
                }
            ),
        ),
    ),
    ("belongs-to", _parent("7.2.2", frozenset({kw.PREFIX}))),
    (
        "import",
        _parent(
            "7.1.5",
            frozenset({kw.PREFIX, kw.REFERENCE, kw.REVISION_DATE, kw.DESCRIPTION}),
        ),
    ),
    (
        "include",
        _parent(
            "7.1.6",
            frozenset({kw.PREFIX, kw.REFERENCE, kw.REVISION_DATE, kw.DESCRIPTION}),
        ),
    ),
    (
        "typedef",
        _parent("7.3.1", METADATA_SUBSTATEMENTS, frozenset({kw.TYPE, kw.DEFAULT})),
    ),
    (
        "type",
        _parent(
            "7.4.1",
            frozenset(
                {
                    kw.TYPE,
                    kw.PATTERN,
                    kw.LENGTH,
                    kw.RANGE,
                    kw.FRACTION_DIGITS,
                    kw.ENUM,
                    kw.BIT,
                    kw.PATH,
                    kw.REQUIRE_INSTANCE,
                    kw.BASE,
                    kw.UNITS,
                    kw.DESCRIPTION,
                    kw.REFERENCE,
                }
            ),
        ),
    ),
    (
        "pattern",
        _parent(
            "9.4.5",
            frozenset(
                {
                    kw.DESCRIPTION,
                    kw.REFERENCE,
                    kw.ERROR_MESSAGE,
                    kw.ERROR_APP_TAG,
                    kw.MODIFIER,
                }
            ),
        ),
    ),
    (
        "enum",
        _parent(
            "9.6.4",
            frozenset({kw.DESCRIPTION, kw.REFERENCE, kw.IF_FEATURE, kw.VALUE, kw.STATUS}),
        ),
    ),
    (
        "bit",
        _parent("9.7.4", frozenset({kw.POSITION, kw.DESCRIPTION, kw.REFERENCE})),
    ),
    (
        "identity",
        _parent("7.18.1", METADATA_SUBSTATEMENTS, frozenset({kw.BASE, kw.IF_FEATURE})),
    ),
    (
        "leaf",
        _parent(
            "7.6.2",
            DATA_NODE_SUBSTATEMENTS,
            frozenset({kw.TYPE, kw.MANDATORY, kw.DEFAULT, kw.MUST, kw.WHEN, kw.IF_FEATURE}),
        ),
    ),
    (
        "leaf-list",
        _parent(
            "7.7.3",
            DATA_NODE_SUBSTATEMENTS,
            frozenset(
                {
                    kw.TYPE,
                    kw.MIN_ELEMENTS,
                    kw.MAX_ELEMENTS,
                    kw.ORDERED_BY,
                    kw.WHEN,
                    kw.MUST,
                    kw.IF_FEATURE,
                }
            ),
        ),
    ),
    (
        "list",
        _parent(
            "7.8.1",
            DATA_NODE_SUBSTATEMENTS,
            DATA_DEF_SUBSTATEMENTS,
            frozenset(
                {
                    kw.KEY,
                    kw.UNIQUE,
                    kw.MIN_ELEMENTS,
                    kw.MAX_ELEMENTS,
                    kw.ORDERED_BY,
                    kw.WHEN,
                    kw.MUST,
                    kw.IF_FEATURE,
                    kw.NOTIFICATION,
                    kw.ACTION,
                }
            ),
        ),
    ),
    (
        "container",
        _parent(
            "7.5.2",
            DATA_NODE_SUBSTATEMENTS,
            DATA_DEF_SUBSTATEMENTS,
            frozenset(
                {
                    kw.PRESENCE,
                    kw.WHEN,
                    kw.MUST,
                    kw.GROUPING,
                    kw.IF_FEATURE,
                    kw.NOTIFICATION,
                    kw.ACTION,
                }
            ),
        ),
    ),
    (
        "grouping",
        _parent(
            "7.12.1",
            METADATA_SUBSTATEMENTS,
            DATA_DEF_SUBSTATEMENTS,
            frozenset(
                {kw.TYPEDEF, kw.GROUPING, kw.IF_FEATURE, kw.WHEN, kw.MUST, kw.NOTIFICATION, kw.ACTION}
            ),
        ),
    ),
    (
        "notification",
        _parent(
            "7.16.1",
            METADATA_SUBSTATEMENTS,
            DATA_DEF_SUBSTATEMENTS,
            frozenset({kw.TYPEDEF, kw.WHEN, kw.MUST, kw.IF_FEATURE}),
        ),
    ),
    (
        "rpc",
        _parent(
            "7.14.1",
            METADATA_SUBSTATEMENTS,
            frozenset({kw.WHEN, kw.MUST, kw.INPUT, kw.OUTPUT, kw.IF_FEATURE}),
        ),
    ),
    (
        "action",
        _parent("7.15.1", METADATA_SUBSTATEMENTS, frozenset({kw.INPUT, kw.OUTPUT, kw.IF_FEATURE})),
    ),
    ("input", _IO),
    ("output", DispatchParent("7.14.3", _IO.keywords)),
    (
        "choice",
        _parent(
            "7.9.1",
            DATA_NODE_SUBSTATEMENTS,
            frozenset({kw.WHEN, kw.IF_FEATURE, kw.CASE, kw.MANDATORY, kw.DEFAULT}),
        ),
    ),
    (
        "case",
        _parent(
            "7.9.2",
            DATA_NODE_SUBSTATEMENTS,
            DATA_DEF_SUBSTATEMENTS,
            frozenset({kw.WHEN, kw.IF_FEATURE}),
        ),
    ),
    (
        "augment",
        _parent(
            "7.17.1",
            DATA_NODE_SUBSTATEMENTS,
            DATA_DEF_SUBSTATEMENTS,
            frozenset({kw.IF_FEATURE, kw.CASE, kw.WHEN, kw.MUST, kw.NOTIFICATION, kw.ACTION}),
        ),
    ),
    (
        "uses",
        _parent(
            "7.13.1",
            METADATA_SUBSTATEMENTS,
            frozenset({kw.WHEN, kw.IF_FEATURE, kw.REFINE, kw.AUGMENT}),
        ),
    ),
    (
        "refine",
        _parent(
            "7.13.2",
            DATA_NODE_SUBSTATEMENTS,
            frozenset(
                {
                    kw.MUST,
                    kw.MIN_ELEMENTS,
                    kw.MAX_ELEMENTS,
                    kw.ORDERED_BY,
                    kw.MANDATORY,
                    kw.DEFAULT,
                    kw.IF_FEATURE,
                    kw.TYPE,
                }
            ),
        ),
    ),
    (
        "anydata",
        _parent(
            "7.10.1",
            DATA_NODE_SUBSTATEMENTS,
            frozenset({kw.WHEN, kw.MUST, kw.IF_FEATURE, kw.MANDATORY}),
        ),
    ),
    (
        "anyxml",
        _parent(
            "7.11.1",
            DATA_NODE_SUBSTATEMENTS,
            frozenset({kw.WHEN, kw.MUST, kw.IF_FEATURE, kw.MANDATORY}),
        ),
    ),
    (
        "must",
        _parent(
            "7.5.4",
            frozenset({kw.ERROR_MESSAGE, kw.ERROR_APP_TAG, kw.DESCRIPTION, kw.REFERENCE}),
        ),
    ),
    ("when", _parent("7.21.5", frozenset({kw.DESCRIPTION, kw.REFERENCE}))),
    (
        "feature",
        _parent("7.20.1", frozenset({kw.DESCRIPTION, kw.IF_FEATURE, kw.REFERENCE})),
    ),
    ("if-feature", _parent("7.20.2", frozenset({kw.DESCRIPTION, kw.REFERENCE}))),
    (
        "extension",
        _parent(
            "7.19.1",
            frozenset({kw.ARGUMENT, kw.DESCRIPTION, kw.REFERENCE, kw.IF_FEATURE}),
        ),
    ),
    ("argument", _parent("7.19.2", frozenset({kw.YIN_ELEMENT}))),
    (
        "deviation",
        _parent("7.20.3", frozenset({kw.DESCRIPTION, kw.REFERENCE, kw.DEVIATE})),
    ),
    ("revision", _parent("7.1.9", frozenset({kw.DESCRIPTION, kw.REFERENCE}))),
    (
        "extension-invocation",
        _parent(
            "6.3.1",
            frozenset(
                {
                    kw.IF_FEATURE,
                    kw.WHEN,
                    kw.MUST,
                    kw.DESCRIPTION,
                    kw.REFERENCE,
                    kw.TYPE,
                    kw.USES,
                    kw.LEAF,
                    kw.LEAF_LIST,
                    kw.CONTAINER,
                    kw.LIST,
                    kw.CHOICE,
                    kw.CASE,
                    kw.ANYDATA,
                    kw.ANYXML,
                }
            ),
        ),
    ),
    (
        "length",
        _parent(
            "9.4.4",
            frozenset({kw.ERROR_MESSAGE, kw.ERROR_APP_TAG, kw.DESCRIPTION, kw.REFERENCE}),
        ),
    ),
    (
        "range",
        _parent(
            "9.2.4",
            frozenset({kw.ERROR_MESSAGE, kw.ERROR_APP_TAG, kw.DESCRIPTION, kw.REFERENCE}),
        ),
    ),
)

DISPATCH_REGISTRY: Mapping[str, DispatchParent] = MappingProxyType(dict(_PARENTS))


def dispatch_registry_parity_snapshot() -> dict[str, dict[str, object]]:
    """``{parent: {rfc, keywords}}`` for the cross-language check."""
    return {
        name: {"rfc": spec.rfc, "keywords": sorted(spec.keywords)}
        for name, spec in DISPATCH_REGISTRY.items()
    }
