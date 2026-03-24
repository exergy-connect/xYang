"""
Abstract Syntax Tree (AST) nodes for YANG statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional
from dataclasses import dataclass, field

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

    def has_must_false(self) -> bool:
        """True if this node has a ``must`` with expression ``false()`` (unreachable schema)."""
        return False


@dataclass
class YangStatementWithMust(YangStatement):
    """Statement that can have must constraints (leaf, leaf-list, container, list)."""
    must_statements: List['YangMustStmt'] = field(default_factory=list)

    def has_must_false(self) -> bool:
        from .xpath.ast import ast_is_const_false

        # TODO use XPathEvaluator for more sophisticated must expression evaluation.
        for m in self.must_statements:
            if ast_is_const_false(m.ast):
                return True
        return False


@dataclass
class YangStatementWithWhen(YangStatement):
    """Statement that can have a when condition (leaf, leaf-list, container, list)."""
    when: Optional['YangWhenStmt'] = None


@dataclass
class YangTypedefStmt(YangStatement):
    """Typedef statement."""
    type: Optional['YangTypeStmt'] = None

    def get_schema_node(self) -> Optional[str]:
        return self.name or None


@dataclass
class YangTypeStmt:
    """Type statement."""
    name: str
    pattern: Optional[str] = None
    length: Optional[str] = None
    range: Optional[str] = None
    fraction_digits: Optional[int] = None
    enums: List[str] = field(default_factory=list)
    types: List['YangTypeStmt'] = field(default_factory=list)  # For union types
    path: Optional["PathNode"] = None  # For leafref: parsed XPath path, set during parsing
    require_instance: bool = True  # For leafref


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
    """When statement (conditional)."""
    def __init__(self, condition: str, description: str = ""):
        super().__init__(expression=condition)
        self.description = description

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
class YangUsesStmt(YangStatement):
    """Uses statement - incorporates a grouping."""
    grouping_name: str = ""
    refines: List['YangRefineStmt'] = field(default_factory=list)

    def get_schema_node(self) -> Optional[str]:
        return None


@dataclass
class YangRefineStmt(YangStatementWithMust):
    """Refine statement - modifies nodes from a grouping when using it."""
    target_path: str = ""  # Descendant path (e.g. "type", or schema path through choice/case nodes)
    type: Optional['YangTypeStmt'] = None  # Refined type when target is a leaf
    min_elements: Optional[int] = None  # Refined min-elements (list / leaf-list)
    max_elements: Optional[int] = None  # Refined max-elements (list / leaf-list)


@dataclass
class YangChoiceStmt(YangStatement):
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


@dataclass
class YangCaseStmt(YangStatement):
    """Case statement - defines one alternative in a choice."""

    def get_schema_node(self) -> Optional[str]:
        return self.name or None

    def child_names(self, data: dict) -> set[str]:
        return {s.name for s in self.statements if getattr(s, "name", None)}