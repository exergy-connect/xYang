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
    # This map is the module file's own imports. A submodule's imports stay on
    # that file (``included_files``) and are not merged here.
    import_prefixes: Dict[str, "YangModule"] = field(default_factory=dict)
    # Submodule name -> the included file, which keeps its own ``import_prefixes``.
    included_files: Dict[str, "YangModule"] = field(default_factory=dict)
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

    def resolve_prefixed_module(self, prefix: str, file: str | None = None) -> Optional["YangModule"]:
        """``prefix`` -> module in the context of source file *file*.

        *file* is a submodule name (``included_from``) or None. None on a submodule
        is that submodule's own file; None on a module is the module file. The
        defining module's prefix, and a submodule's ``belongs-to`` prefix, resolve
        to the defining module in every file of that module. Other prefixes resolve
        only in the import map of file *file*.
        """
        defining = self.defining_module()
        source = self._source_file(file)
        if source is None:
            return None
        own = defining.own_prefix_stripped()
        if prefix == own or (source.own_prefix_stripped() and prefix == source.own_prefix_stripped()):
            return defining
        return source.import_prefixes.get(prefix)

    def _source_file(self, file: str | None) -> Optional["YangModule"]:
        """The module or submodule object whose imports bind prefixes in *file*."""
        defining = self.defining_module()
        if file and file != defining.name:
            found = defining.included_files.get(file)
            if found is not None:
                return found
            if self.name == file:
                return self
            return None
        if self is not defining and (self.belongs_to_module or self.included_parent is not None):
            return self
        return defining

    def resolve_prefix_to_module_name(self, prefix: str, file: str | None = None) -> Optional[str]:
        """Name of the module ``prefix`` is bound to in file *file* (a submodule resolves to its parent module)."""
        target = self.resolve_prefixed_module(prefix, file)
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
    file_scope = getattr(type_stmt, "scope", None) or fallback
    if not isinstance(file_scope, YangModule):
        return None, None
    defining = file_scope.defining_module()
    prefix = getattr(type_stmt, "prefix", None)
    # A prefixed name resolves in the file that wrote the ``type``. An unprefixed
    # name is module-wide: typedefs from every included file live on the defining module.
    target = file_scope.resolve_prefixed_module(prefix) if prefix else defining
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
