"""
YANG module representation.
"""

from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING
from dataclasses import dataclass, field

from .ast import YangStatementList

if TYPE_CHECKING:
    from .ast import YangStatement, YangTypedefStmt


@dataclass
class YangModule(YangStatementList):
    """Represents a YANG module. Statements list inherited from YangStatementList."""

    name: str = ""
    yang_version: str = "1.1"
    namespace: str = ""
    prefix: str = ""
    organization: str = ""
    contact: str = ""
    description: str = ""
    revisions: List[Dict[str, str]] = field(default_factory=list)
    typedefs: Dict[str, 'YangTypedefStmt'] = field(default_factory=dict)
    groupings: Dict[str, 'YangStatement'] = field(default_factory=dict)

    def get_typedef(self, name: str) -> Optional['YangTypedefStmt']:
        """Get a typedef by name."""
        return self.typedefs.get(name)
    
    def get_grouping(self, name: str) -> Optional['YangStatement']:
        """Get a grouping by name."""
        return self.groupings.get(name)
