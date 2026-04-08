"""
Abstract Syntax Tree (AST) nodes for YANG statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional
from dataclasses import dataclass, field

from .errors import YangSemanticError

if TYPE_CHECKING:
    from .xpath.ast import ASTNode, PathNode


@dataclass
class YangStatementList:
    """Base for nodes that contain a list of YANG statements (module body or statement body)."""
    statements: List['YangStatement'] = field(default_factory=list)

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
        leaves = []
        if isinstance(stmt, YangLeafStmt):
            leaves.append(stmt)
        elif isinstance(stmt, (YangContainerStmt, YangListStmt)):
            for child in stmt.statements:
                leaves.extend(self._collect_leaves(child))
        return leaves


@dataclass
class YangStatement(YangStatementList):
    """Base class for all YANG statements."""
    name: str = ""
    description: str = ""

    def get_schema_node(self) -> Optional[str]:
        """Path segment for this statement in the schema tree, or None if it adds no node.

        Used when assembling paths for ``refine`` targets and similar (e.g. ``uses`` is
        not a schema node; see :class:`YangUsesStmt`).
        """
        return None

    def child_names(self, data: dict) -> set[str]:
        return {self.name} if getattr(self, "name", None) else set()


@dataclass
class YangStatementWithMust(YangStatement):
    """Statement that can have must constraints (leaf, leaf-list, container, list)."""
    must_statements: List['YangMustStmt'] = field(default_factory=list)


@dataclass
class YangStatementWithWhen(YangStatement):
    """Statement that can have a when condition (leaf, leaf-list, container, list)."""

    when: Optional['YangWhenStmt'] = None
    # RFC 7950 / 7952: one or more ``if-feature`` substatements (AND of expressions).
    if_features: List[str] = field(default_factory=list)


@dataclass
class YangTypedefStmt(YangStatement):
    """Typedef statement."""
    type: Optional['YangTypeStmt'] = None

    def get_schema_node(self) -> Optional[str]:
        return self.name or None


@dataclass
class YangIdentityStmt(YangStatement):
    """Identity statement (RFC 7950); may have multiple ``base`` substatements (YANG 1.1)."""

    bases: List[str] = field(default_factory=list)
    if_features: List[str] = field(default_factory=list)

    def get_schema_node(self) -> Optional[str]:
        return None


@dataclass
class YangBitStmt:
    """Single bit in a ``type bits { ... }`` (RFC 7950 §9.3.4).

    ``position`` is ``None`` until the parser assigns implicit positions; after
    parsing a complete ``bits`` type, every bit has a non-negative integer position.
    """

    name: str
    position: Optional[int] = None


@dataclass
class YangTypeStmt:
    """Type statement."""
    name: str
    pattern: Optional[str] = None
    length: Optional[str] = None
    range: Optional[str] = None
    fraction_digits: Optional[int] = None
    enums: List[str] = field(default_factory=list)
    bits: List[YangBitStmt] = field(default_factory=list)  # For bits type
    types: List['YangTypeStmt'] = field(default_factory=list)  # For union types
    path: Optional["PathNode"] = None  # For leafref: parsed XPath path, set during parsing
    require_instance: bool = True  # For leafref
    identityref_bases: List[str] = field(default_factory=list)  # For identityref: one per ``base`` substatement


@dataclass
class YangContainerStmt(YangStatementWithMust, YangStatementWithWhen):
    """Container statement."""
    presence: Optional[str] = None

    def get_schema_node(self) -> Optional[str]:
        return self.name or None


@dataclass
class YangListStmt(YangStatementWithMust, YangStatementWithWhen):
    """List statement."""
    key: Optional[str] = None
    min_elements: Optional[int] = None
    max_elements: Optional[int] = None

    def get_schema_node(self) -> Optional[str]:
        return self.name or None


@dataclass
class YangLeafStmt(YangStatementWithMust, YangStatementWithWhen):
    """Leaf statement."""
    type: Optional[YangTypeStmt] = None
    mandatory: bool = False
    default: Optional[Any] = None

    def get_schema_node(self) -> Optional[str]:
        return self.name or None


@dataclass
class YangLeafListStmt(YangStatementWithMust, YangStatementWithWhen):
    """Leaf-list statement."""
    type: Optional[YangTypeStmt] = None
    min_elements: Optional[int] = None
    max_elements: Optional[int] = None

    def get_schema_node(self) -> Optional[str]:
        return self.name or None


@dataclass
class YangParsedXPathBase:
    """Base class for statements that carry a parsed XPath expression."""
    expression: str
    description: str = ""

    ast: ASTNode | None = None  # Parsed XPath AST for reuse; always set in __post_init__

    def __post_init__(self) -> None:
        # Lazily import to avoid circular dependencies at module import time.
        if self.expression:
            from .xpath import XPathParser
            self.ast = XPathParser(self.expression).parse()

@dataclass
class YangMustStmt(YangParsedXPathBase):
    """Must statement (constraint)."""
    error_message: str = ""


@dataclass
class YangWhenStmt(YangParsedXPathBase):
    """When statement (conditional). XPath lives in ``expression`` (see ``condition``)."""

    # RFC 7950 §7.21.5: ``when`` under ``uses`` uses the parent of ``uses`` as context node.
    # Set when this ``when`` is merged from a ``uses`` (or AND-merged with such a ``when``).
    evaluate_with_parent_context: bool = False

    @property
    def condition(self) -> str:
        return self.expression


@dataclass
class YangLeafrefStmt:
    """Leafref type statement."""
    path: str = ""
    require_instance: bool = True


@dataclass
class YangGroupingStmt(YangStatement):
    """Grouping statement - defines reusable schema components."""
    pass


@dataclass
class YangUsesStmt(YangStatementWithWhen):
    """Uses statement - incorporates a grouping."""

    grouping_name: str = ""
    refines: List['YangRefineStmt'] = field(default_factory=list)

    def get_schema_node(self) -> Optional[str]:
        return None


@dataclass
class YangAugmentStmt(YangStatementWithWhen):
    """Augment statement (RFC 7950). After parse, children are merged into the target node (see ``augment_expand``)."""

    augment_path: str = ""

    def get_schema_node(self) -> Optional[str]:
        return None


@dataclass
class YangRefineStmt(YangStatementWithMust):
    """Refine statement - modifies nodes from a grouping when using it."""
    target_path: str = ""  # Descendant path (e.g. "type", or schema path through choice/case nodes)
    type: Optional['YangTypeStmt'] = None  # Refined type when target is a leaf
    min_elements: Optional[int] = None  # Refined min-elements (list / leaf-list)
    max_elements: Optional[int] = None  # Refined max-elements (list / leaf-list)
    # RFC 7950 §7.13.2: leaf / choice may get a different mandatory; None = omit from refine
    refined_mandatory: Optional[bool] = None
    # RFC 7950 §7.13.2: additional if-feature expressions (AND with target node's own).
    if_features: List[str] = field(default_factory=list)


@dataclass
class YangChoiceStmt(YangStatementWithWhen):
    """Choice statement - defines mutually exclusive alternatives."""

    mandatory: bool = False
    cases: List['YangCaseStmt'] = field(default_factory=list)

    def get_schema_node(self) -> Optional[str]:
        return self.name or None

    def child_names(self, data: dict) -> set[str]:
        for case in self.cases:
            if any(getattr(s, "name", None) in data for s in case.statements):
                return {s.name for s in case.statements if getattr(s, "name", None)}
        return set()

    def validate_case_unique_child_names(self) -> None:
        """RFC 7950 §7.9: case branches share one namespace; schema node names must be unique."""
        seen: dict[str, str] = {}
        for case in self.cases:
            for sub in case.statements:
                seg = sub.get_schema_node()
                if seg is None:
                    continue
                if seg in seen:
                    prev_case = seen[seg]
                    raise YangSemanticError(
                        f"Choice {self.name!r}: schema node {seg!r} appears in case "
                        f"{prev_case!r} and again in case {case.name!r} "
                        "(RFC 7950: names of nodes in the cases of a choice must be unique)."
                    )
                seen[seg] = case.name


@dataclass
class YangCaseStmt(YangStatementWithWhen):
    """Case statement - defines one alternative in a choice."""

    def get_schema_node(self) -> Optional[str]:
        return self.name or None

    def child_names(self, data: dict) -> set[str]:
        return {s.name for s in self.statements if getattr(s, "name", None)}
