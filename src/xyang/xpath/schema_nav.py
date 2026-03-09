"""
Schema navigation for xpath.

All knowledge of the schema object model lives here.
Uses isinstance checks against the actual AST types — no keyword strings.
Groupings are pre-expanded during parsing; uses/grouping resolution is never needed here.
"""

from typing import Any, List, Optional

from ..ast import (
    YangCaseStmt,
    YangChoiceStmt,
    YangLeafListStmt,
    YangLeafStmt,
    YangListStmt,
)


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
        """Return the default value for a leaf, or None."""
        if isinstance(schema, YangLeafStmt):
            return schema.default
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
    def leafref_path(schema: Any) -> Optional[str]:
        """Return the leafref path string if this leaf is a leafref, else None."""
        if not isinstance(schema, YangLeafStmt):
            return None
        t = schema.type
        if t is not None and t.name == "leafref":
            return t.path
        return None
