"""
YANG module representation.
"""

from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from .ast import YangStatement, YangTypedefStmt, YangLeafStmt


@dataclass
class YangModule:
    """Represents a YANG module."""

    name: str = ""
    yang_version: str = "1.1"
    namespace: str = ""
    prefix: str = ""
    organization: str = ""
    contact: str = ""
    description: str = ""
    revisions: List[Dict[str, str]] = field(default_factory=list)
    typedefs: Dict[str, 'YangTypedefStmt'] = field(default_factory=dict)
    statements: List['YangStatement'] = field(default_factory=list)

    def get_typedef(self, name: str) -> Optional['YangTypedefStmt']:
        """Get a typedef by name."""
        return self.typedefs.get(name)

    def find_statement(self, name: str) -> Optional['YangStatement']:
        """Find a statement by name."""
        for stmt in self.statements:
            if stmt.name == name:
                return stmt
        return None

    def get_all_leaves(self) -> List['YangLeafStmt']:
        """Get all leaf statements recursively."""
        leaves = []
        for stmt in self.statements:
            leaves.extend(self._collect_leaves(stmt))
        return leaves

    def _collect_leaves(self, stmt: 'YangStatement') -> List['YangLeafStmt']:
        """Recursively collect leaf statements."""
        from .ast import YangLeafStmt, YangContainerStmt, YangListStmt

        leaves = []
        if isinstance(stmt, YangLeafStmt):
            leaves.append(stmt)
        elif isinstance(stmt, (YangContainerStmt, YangListStmt)):
            for child in stmt.statements:
                leaves.extend(self._collect_leaves(child))
        return leaves
