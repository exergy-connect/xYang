"""
Type validator for YANG data.
"""

from typing import Any, Dict, List, TYPE_CHECKING
from dataclasses import dataclass
from ..module import YangModule
from ..ast import YangLeafStmt, YangLeafListStmt
from ..types import TypeSystem

if TYPE_CHECKING:
    from ..ast import YangTypeStmt


@dataclass
class ValidationResult:
    """Result of a validation operation."""
    is_valid: bool
    error_message: str = ""  # Always present if invalid
    
    @classmethod
    def valid(cls):
        """Create a valid result."""
        return cls(True, "")
    
    @classmethod
    def invalid(cls, message: str):
        """Create an invalid result with error message."""
        return cls(False, message)


class TypeValidator:
    """Validates data types against YANG type system."""
    
    def __init__(self, type_system: TypeSystem = None):
        """
        Initialize type validator.
        
        Args:
            type_system: TypeSystem instance (creates new one if not provided)
        """
        self.type_system = type_system or TypeSystem()
        self.errors: List[str] = []
    
    def validate_leaf(
        self, 
        data: Dict[str, Any], 
        leaf: YangLeafStmt,
        context_path: List[str] = None
    ) -> None:
        """
        Validate a leaf's type.
        
        Args:
            data: Data dictionary
            leaf: Leaf statement to validate
            context_path: Current path in data structure
        """
        if leaf.name not in data:
            return  # Missing leaves handled by structure validator
        
        value = data[leaf.name]
        if leaf.type:
            # Check if it's a leafref type (handled by leafref resolver)
            if leaf.type.name == 'leafref' and leaf.type.path:
                return  # Leafref validation handled separately
            
            result = self._validate_type(value, leaf.type.name, leaf.type)
            if not result.is_valid:
                self.errors.append(f"Invalid value for leaf {leaf.name}: {result.error_message}")
    
    def validate_leaf_list(
        self, 
        data: Dict[str, Any], 
        leaf_list: YangLeafListStmt
    ) -> None:
        """
        Validate a leaf-list's type.
        
        Args:
            data: Data dictionary
            leaf_list: Leaf-list statement to validate
        """
        if leaf_list.name not in data:
            return
        
        items = data[leaf_list.name]
        if not isinstance(items, list):
            return  # Type errors handled by structure validator
        
        if leaf_list.type:
            for item in items:
                # Check if this is a union type
                if leaf_list.type.name == 'union' and hasattr(leaf_list.type, 'types') and leaf_list.type.types:
                    result = self._validate_union_type(item, leaf_list.type)
                else:
                    result = self._validate_type(item, leaf_list.type.name, leaf_list.type)
                if not result.is_valid:
                    self.errors.append(
                        f"Invalid value in leaf-list {leaf_list.name}: {result.error_message}"
                    )
    
    def _validate_union_type(
        self,
        value: Any,
        union_type_stmt: Any  # YangTypeStmt with name='union' and types list
    ) -> ValidationResult:
        """
        Validate a value against a union type by trying each member type.
        
        Args:
            value: Value to validate
            union_type_stmt: Union type statement with types list
            
        Returns:
            ValidationResult
        """
        if not hasattr(union_type_stmt, 'types') or not union_type_stmt.types:
            return ValidationResult.invalid("Union type has no member types")
        
        errors = []
        for union_member in union_type_stmt.types:
            from ..types import TypeConstraint
            constraints = TypeConstraint(
                pattern=union_member.pattern,
                length=union_member.length,
                range=union_member.range,
                fraction_digits=union_member.fraction_digits,
                enums=union_member.enums
            )
            is_valid, error_msg = self.type_system.validate(value, union_member.name, constraints)
            if is_valid:
                return ValidationResult.valid()
            if error_msg:
                errors.append(f"{union_member.name}: {error_msg}")
        
        # None of the union members matched
        return ValidationResult.invalid(
            f"Value does not match any union member type. Errors: {'; '.join(errors)}"
        )
    
    def _validate_type(
        self, 
        value: Any, 
        type_name: str, 
        type_stmt: Any  # YangTypeStmt
    ) -> ValidationResult:
        """
        Validate a value against a type.
        
        Args:
            value: Value to validate
            type_name: Type name
            type_stmt: Type statement with constraints
            
        Returns:
            ValidationResult
        """
        # Handle union types: try each type in the union until one succeeds
        if type_name == 'union' or (type_stmt and hasattr(type_stmt, 'types') and type_stmt.types):
            # This is a union type - try each member type
            if not type_stmt or not hasattr(type_stmt, 'types') or not type_stmt.types:
                return ValidationResult.invalid("Union type has no member types")
            
            errors = []
            for union_member in type_stmt.types:
                from ..types import TypeConstraint
                constraints = TypeConstraint(
                    pattern=union_member.pattern,
                    length=union_member.length,
                    range=union_member.range,
                    fraction_digits=union_member.fraction_digits,
                    enums=union_member.enums
                )
                is_valid, error_msg = self.type_system.validate(value, union_member.name, constraints)
                if is_valid:
                    return ValidationResult.valid()
                if error_msg:
                    errors.append(f"{union_member.name}: {error_msg}")
            
            # None of the union members matched
            return ValidationResult.invalid(
                f"Value does not match any union member type. Errors: {'; '.join(errors)}"
            )
        
        # Convert type_stmt to TypeConstraint
        from ..types import TypeConstraint
        
        constraints = None
        if type_stmt:
            constraints = TypeConstraint(
                pattern=type_stmt.pattern,
                length=type_stmt.length,
                range=type_stmt.range,
                fraction_digits=type_stmt.fraction_digits,
                enums=type_stmt.enums
            )
        
        is_valid, error_msg = self.type_system.validate(value, type_name, constraints)
        
        if is_valid:
            return ValidationResult.valid()
        else:
            return ValidationResult.invalid(error_msg or f"Invalid {type_name} value")