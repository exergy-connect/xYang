"""
YANG module representation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
from dataclasses import dataclass, field

from .ast import YangStatementList

if TYPE_CHECKING:
    from .ast import YangExtensionStmt, YangIdentityStmt, YangStatement, YangTypedefStmt


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
    reference: str = ""
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
    # The module this included submodule was merged into. Its definitions are
    # visible across that module (RFC 7950 §5.1).
    included_parent: Optional["YangModule"] = None
    # Submodule that contributed an included feature, or its if-feature list.
    # The same submodule reached twice is one definition.
    feature_included_from: Dict[str, str] = field(default_factory=dict)
    feature_if_included_from: Dict[str, str] = field(default_factory=dict)
    # Submodule names whose statements are already on this module.
    included_submodules: Set[str] = field(default_factory=set)
    # extension name -> extension definition from this module.
    extensions: Dict[str, "YangExtensionStmt"] = field(default_factory=dict)
    # Generic runtime storage for extension callbacks.
    extension_runtime: Dict[str, Any] = field(default_factory=dict)

    def own_prefix_stripped(self) -> str:
        return (self.prefix or "").strip("'\"")

    def defining_module(self) -> "YangModule":
        """The module this tree belongs to. An included submodule resolves to its parent."""
        scope: YangModule = self
        while scope.included_parent is not None:
            scope = scope.included_parent
        return scope

    def resolve_prefixed_module(self, prefix: str) -> Optional["YangModule"]:
        """Module for ``prefix`` in this module's scope (own prefix or ``import``)."""
        if prefix == self.own_prefix_stripped():
            return self
        return self.import_prefixes.get(prefix)

    def resolve_prefix_to_module_name(self, prefix: str) -> Optional[str]:
        """Name of the module ``prefix`` is bound to here (a submodule resolves to its parent module)."""
        target = self.resolve_prefixed_module(prefix)
        if target is None:
            return None
        return target.belongs_to_module or target.name

    def get_typedef(self, name: str) -> Optional['YangTypedefStmt']:
        """Get a typedef by name."""
        return self.typedefs.get(name)
    
    def get_grouping(self, name: str) -> Optional['YangStatement']:
        """Get a grouping by name."""
        return self.groupings.get(name)

    def get_identity(self, name: str) -> Optional['YangIdentityStmt']:
        """Get an identity by name."""
        return self.identities.get(name)

    def get_extension(self, name: str) -> Optional["YangExtensionStmt"]:
        """Get an extension definition by local name."""
        return self.extensions.get(name)


def resolve_typedef(type_stmt: Any, fallback: Any) -> tuple[Optional["YangTypedefStmt"], Optional["YangModule"]]:
    """``(typedef, module)`` a derived ``type`` names, resolved where the ``type`` was written.

    The writing module (``type_stmt.scope``, set by the parser) resolves prefixes and
    top-level typedef names (RFC 7950 §7.13). Unprefixed references also check the typedef
    scope against the reference context (§5.5). A ``type`` without a scope (built from the native JSON
    form) resolves in *fallback*. ``(None, None)`` when the prefix or the typedef is unknown.
    """
    scope = getattr(type_stmt, "scope", None) or fallback
    if not isinstance(scope, YangModule):
        return None, None
    scope = scope.defining_module()
    prefix = getattr(type_stmt, "prefix", None)
    target = scope.resolve_prefixed_module(prefix) if prefix else scope
    if target is None:
        return None, None
    from .typedef_scope import in_scope

    context = getattr(type_stmt, "context", None) or ""
    direct = target.typedefs.get(type_stmt.name)
    candidates = [direct] if direct is not None else [td for td in target.typedefs.values() if td.name == type_stmt.name]
    for td in candidates:
        if (td.scope is None if prefix else in_scope(td.scope, context)):
            return td, target
    return None, None
