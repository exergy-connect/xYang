"""
YANG module representation.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, TYPE_CHECKING
from dataclasses import dataclass, field

from .ast import YangStatementList

if TYPE_CHECKING:
    from .ast import YangIdentityStmt, YangStatement, YangTypedefStmt


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
    # Set when this tree was parsed from a submodule (belongs-to argument).
    belongs_to_module: str = ""
    typedefs: Dict[str, 'YangTypedefStmt'] = field(default_factory=dict)
    identities: Dict[str, 'YangIdentityStmt'] = field(default_factory=dict)
    groupings: Dict[str, 'YangStatement'] = field(default_factory=dict)
    # Declared ``feature`` names in this module (RFC 7950 §7.18.1).
    features: Set[str] = field(default_factory=set)
    # Per-feature ``if-feature`` substatements (RFC 7950 §7.20.1.1); AND of expressions.
    feature_if_features: Dict[str, List[str]] = field(default_factory=dict)
    # import prefix (local) -> parsed module (RFC 7950 ``import``).
    import_prefixes: Dict[str, "YangModule"] = field(default_factory=dict)

    def own_prefix_stripped(self) -> str:
        return (self.prefix or "").strip("'\"")

    def resolve_prefixed_module(self, prefix: str) -> Optional["YangModule"]:
        """Module for ``prefix`` in this module's scope (own prefix or ``import``)."""
        if prefix == self.own_prefix_stripped():
            return self
        return self.import_prefixes.get(prefix)

    def get_typedef(self, name: str) -> Optional['YangTypedefStmt']:
        """Get a typedef by name."""
        return self.typedefs.get(name)
    
    def get_grouping(self, name: str) -> Optional['YangStatement']:
        """Get a grouping by name."""
        return self.groupings.get(name)

    def get_identity(self, name: str) -> Optional['YangIdentityStmt']:
        """Get an identity by name."""
        return self.identities.get(name)
