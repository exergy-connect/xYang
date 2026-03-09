"""
Abstract Syntax Tree (AST) nodes for YANG statements.
"""

from typing import List, Optional, Any
from dataclasses import dataclass, field


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


@dataclass
class YangStatementWithMust(YangStatement):
    """Statement that can have must constraints (leaf, leaf-list, container, list)."""
    must_statements: List['YangMustStmt'] = field(default_factory=list)


@dataclass
class YangStatementWithWhen(YangStatement):
    """Statement that can have a when condition (leaf, leaf-list, container, list)."""
    when: Optional['YangWhenStmt'] = None


@dataclass
class YangTypedefStmt(YangStatement):
    """Typedef statement."""
    type: Optional['YangTypeStmt'] = None


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
    path: Optional[str] = None  # For leafref
    require_instance: bool = True  # For leafref


@dataclass
class YangContainerStmt(YangStatementWithMust, YangStatementWithWhen):
    """Container statement."""
    presence: Optional[str] = None


@dataclass
class YangListStmt(YangStatementWithMust, YangStatementWithWhen):
    """List statement."""
    key: Optional[str] = None
    min_elements: Optional[int] = None
    max_elements: Optional[int] = None


@dataclass
class YangLeafStmt(YangStatementWithMust, YangStatementWithWhen):
    """Leaf statement."""
    type: Optional[YangTypeStmt] = None
    mandatory: bool = False
    default: Optional[Any] = None


@dataclass
class YangLeafListStmt(YangStatementWithMust, YangStatementWithWhen):
    """Leaf-list statement."""
    type: Optional[YangTypeStmt] = None
    min_elements: Optional[int] = None
    max_elements: Optional[int] = None


@dataclass
class YangMustStmt:
    """Must statement (constraint)."""
    expression: str
    error_message: str = ""
    description: str = ""
    ast: Optional[Any] = None  # Parsed XPath AST for reuse


@dataclass
class YangWhenStmt:
    """When statement (conditional)."""
    condition: str
    description: str = ""
    ast: Optional[Any] = None  # Parsed XPath AST for reuse


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


@dataclass
class YangRefineStmt(YangStatementWithMust):
    """Refine statement - modifies nodes from a grouping when using it."""
    target_path: str = ""  # Path to the node being refined (e.g., "type", "required")
    type: Optional['YangTypeStmt'] = None  # Refined type when target is a leaf


@dataclass
class YangChoiceStmt(YangStatement):
    """Choice statement - defines mutually exclusive alternatives."""
    mandatory: bool = False
    cases: List['YangCaseStmt'] = field(default_factory=list)


@dataclass
class YangCaseStmt(YangStatement):
    """Case statement - defines one alternative in a choice."""
    pass