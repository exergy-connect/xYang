"""
Schema navigation for xpath.

All knowledge of the schema object model lives here.
Uses isinstance checks against the actual AST types — no keyword strings.
Groupings are pre-expanded during parsing; uses/grouping resolution is never needed here.
"""

from typing import Any, List, Optional

from .ast import PathNode
from ..ast import (
    YangCaseStmt,
    YangChoiceStmt,
    YangLeafListStmt,
    YangLeafStmt,
    YangListStmt,
)
from .utils import coerce_default_value


class SchemaNav:
    """Schema navigation helpers."""

    @staticmethod
    def child(schema: Any, name: str) -> Optional[Any]:
        """
        Return the named child schema node.
        Descends transparently into YangChoiceStmt and YangCaseStmt,
        which are structural groupings with no data representation.
        """
        if schema is None:
            return None
        return SchemaNav._find(getattr(schema, "statements", []), name)

    @staticmethod
    def _find(stmts: list, name: str) -> Optional[Any]:
        for stmt in stmts:
            if getattr(stmt, "name", None) == name:
                return stmt
            if isinstance(stmt, YangChoiceStmt):
                for case in stmt.cases:
                    found = SchemaNav._find(getattr(case, "statements", []), name)
                    if found is not None:
                        return found
            elif isinstance(stmt, YangCaseStmt):
                found = SchemaNav._find(stmt.statements, name)
                if found is not None:
                    return found
        return None

    @staticmethod
    def default(schema: Any) -> Any:
        """
        Return the schema default for a node, or None.

        YangLeafStmt      -- schema.default (any scalar)
        YangLeafListStmt  -- [schema.default] if schema.default is not None,
                             else None. A leaf-list default is a single
                             default element; wrap it in a list to match
                             the expected data shape.
        YangChoiceStmt    -- None. Choice defaults (default case) are
                             structural and handled by the walker, not
                             by value resolution.
        YangContainerStmt -- None. Presence containers have no default;
                             non-presence containers are always implicitly
                             present when their children are present.
        YangListStmt      -- None. Lists have no default value.
        """
        if isinstance(schema, YangLeafStmt):
            d = schema.default
            if d is None:
                return None
            type_name = getattr(getattr(schema, "type", None), "name", None)
            return coerce_default_value(d, type_name)
        if isinstance(schema, YangLeafListStmt):
            d = getattr(schema, "default", None)
            if d is None:
                return None
            type_name = getattr(getattr(schema, "type", None), "name", None)
            return [coerce_default_value(d, type_name)]
        return None

    @staticmethod
    def is_list(schema: Any) -> bool:
        """True if this schema node represents a YANG list (expands to multiple data nodes)."""
        return isinstance(schema, YangListStmt)

    @staticmethod
    def is_leaf_list(schema: Any) -> bool:
        """True if this schema node represents a YANG leaf-list."""
        return isinstance(schema, YangLeafListStmt)

    @staticmethod
    def leafref_path(schema: Any) -> Optional[PathNode]:
        """Return the leafref path if this leaf is a leafref, else None."""
        if not isinstance(schema, YangLeafStmt):
            return None
        t = schema.type
        if t is not None and t.name == "leafref":
            return t.path
        return None
