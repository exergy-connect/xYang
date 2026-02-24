"""
Abstract Syntax Tree (AST) nodes for YANG statements.
"""

from typing import List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class YangStatement:
    """Base class for all YANG statements."""
    name: str
    description: str = ""
    statements: List['YangStatement'] = field(default_factory=list)




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
class YangContainerStmt(YangStatement):
    """Container statement."""
    presence: Optional[str] = None
    when: Optional['YangWhenStmt'] = None
    must_statements: List['YangMustStmt'] = field(default_factory=list)


@dataclass
class YangListStmt(YangStatement):
    """List statement."""
    key: Optional[str] = None
    min_elements: Optional[int] = None
    max_elements: Optional[int] = None
    when: Optional['YangWhenStmt'] = None


@dataclass
class YangLeafStmt(YangStatement):
    """Leaf statement."""
    type: Optional[YangTypeStmt] = None
    mandatory: bool = False
    default: Optional[Any] = None
    must_statements: List['YangMustStmt'] = field(default_factory=list)
    when: Optional['YangWhenStmt'] = None


@dataclass
class YangLeafListStmt(YangStatement):
    """Leaf-list statement."""
    type: Optional[YangTypeStmt] = None
    min_elements: Optional[int] = None
    max_elements: Optional[int] = None
    must_statements: List['YangMustStmt'] = field(default_factory=list)


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
class YangRefineStmt(YangStatement):
    """Refine statement - modifies nodes from a grouping when using it."""
    target_path: str = ""  # Path to the node being refined (e.g., "type", "required")


@dataclass
class YangChoiceStmt(YangStatement):
    """Choice statement - defines mutually exclusive alternatives."""
    mandatory: bool = False
    cases: List['YangCaseStmt'] = field(default_factory=list)


@dataclass
class YangCaseStmt(YangStatement):
    """Case statement - defines one alternative in a choice."""
    pass