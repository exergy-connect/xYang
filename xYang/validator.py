"""
YANG validation engine (refactored).
"""

from typing import Any, Dict, List, Tuple, Callable, Optional
from .module import YangModule
from .ast import YangStatement, YangLeafStmt, YangLeafListStmt
from .types import TypeSystem
from .xpath import XPathEvaluator
from .validators import (
    StructureValidator,
    TypeValidator,
    ConstraintValidator,
    LeafrefResolver
)


class YangValidator:
    """YANG data validator (refactored to use focused validators)."""
    
    def __init__(
        self, 
        module: YangModule,
        evaluator_factory: Optional[Callable] = None,
        type_system: Optional[TypeSystem] = None
    ):
        """
        Initialize validator.
        
        Args:
            module: YANG module to validate against
            evaluator_factory: Factory for creating XPathEvaluator instances
            type_system: TypeSystem instance (creates new one if not provided)
        """
        self.module = module
        self.evaluator_factory = evaluator_factory or XPathEvaluator
        self.type_system = type_system or TypeSystem()
        
        # Create focused validators
        self.structure_validator = StructureValidator(module, evaluator_factory)
        self.type_validator = TypeValidator(self.type_system)
        self.constraint_validator = ConstraintValidator(module, evaluator_factory)
        self.leafref_resolver = LeafrefResolver(module)
    
    def validate(self, data: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
        """
        Validate data against the YANG module.
        
        Args:
            data: Data to validate
            
        Returns:
            (is_valid, errors, warnings)
        """
        # Reset all validators
        self._reset()
        
        # Store root data for leafref validation
        root_data = data
        
        # 1. Validate structure
        self.structure_validator.validate(data, self.module.statements)
        
        # 2. Validate types (including leafref preparation)
        self._validate_types(data, self.module.statements, root_data)
        
        # 3. Validate must statements
        self.constraint_validator.validate_must_statements(data)
        
        # Collect all errors and warnings
        errors = (
            self.structure_validator.errors +
            self.type_validator.errors +
            self.constraint_validator.errors +
            self.leafref_resolver.errors
        )
        warnings = self.structure_validator.warnings
        
        return len(errors) == 0, errors, warnings
    
    def _validate_types(
        self,
        data: Dict[str, Any],
        statements: List[YangStatement],
        root_data: Dict[str, Any],
        context_path: List[str] = None
    ) -> None:
        """
        Validate types recursively.
        
        Args:
            data: Data to validate
            statements: Statements to validate against
            root_data: Root data for leafref validation
            context_path: Current path in data structure
        """
        if context_path is None:
            context_path = []
        
        for stmt in statements:
            # Check when condition
            if hasattr(stmt, 'when') and stmt.when:
                evaluator = self.evaluator_factory(data, self.module, context_path=context_path)
                if not evaluator.evaluate(stmt.when.condition):
                    continue
            
            if isinstance(stmt, YangLeafStmt):
                # Validate leaf type
                self.type_validator.validate_leaf(data, stmt, context_path)
                
                # Validate leafref if applicable
                if (stmt.name in data and stmt.type and 
                    stmt.type.name == 'leafref' and stmt.type.path):
                    self.leafref_resolver.validate_leafref(
                        stmt, data[stmt.name], data, context_path, root_data
                    )
            
            elif isinstance(stmt, YangLeafListStmt):
                # Validate leaf-list type
                self.type_validator.validate_leaf_list(data, stmt)
            
            elif hasattr(stmt, 'statements'):
                # Recurse into composite statements
                if stmt.name in data:
                    new_path = context_path + [stmt.name] if hasattr(stmt, 'name') else context_path
                    self._validate_types(
                        data[stmt.name], stmt.statements, root_data, context_path=new_path
                    )
    
    def _reset(self) -> None:
        """Reset all validators to initial state."""
        self.structure_validator.errors = []
        self.structure_validator.warnings = []
        self.type_validator.errors = []
        self.constraint_validator.errors = []
        self.leafref_resolver.errors = []