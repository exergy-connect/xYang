"""
YANG validation engine (refactored).
"""

from typing import Any, Dict, List, Tuple, Callable, Optional
from .module import YangModule
from .ast import YangStatement, YangLeafStmt, YangLeafListStmt, YangContainerStmt, YangListStmt, YangChoiceStmt, YangCaseStmt
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
        
        # Register typedefs from module into type system
        self._register_typedefs()
        
        # Create focused validators
        self.structure_validator = StructureValidator(module, evaluator_factory)
        self.type_validator = TypeValidator(self.type_system, module)
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
        
        # 3. Validate must statements (pass root data for absolute paths)
        # XPath evaluator performs type-aware coercion inline during comparisons
        self.constraint_validator.validate_must_statements(data, root_data=data)
        
        # Collect all errors and warnings
        errors = (
            self.structure_validator.errors +
            self.type_validator.errors +
            self.constraint_validator.errors +
            self.leafref_resolver.errors
        )
        warnings = self.structure_validator.warnings
        
        # Always return tuple - never raise exceptions
        # Cross-reference errors are included in the errors list
        return len(errors) == 0, errors, warnings
    
    def _register_typedefs(self) -> None:
        """Register typedefs from module into type system."""
        from .types import TypeConstraint
        
        for typedef_name, typedef_stmt in self.module.typedefs.items():
            if typedef_stmt.type:
                base_type = typedef_stmt.type.name
                
                # Extract constraints from typedef
                constraints = None
                if (typedef_stmt.type.pattern or typedef_stmt.type.length or 
                    typedef_stmt.type.range or typedef_stmt.type.enums):
                    constraints = TypeConstraint(
                        pattern=typedef_stmt.type.pattern,
                        length=typedef_stmt.type.length,
                        range=typedef_stmt.type.range,
                        enums=typedef_stmt.type.enums if typedef_stmt.type.enums else []
                    )
                
                # Register the typedef
                self.type_system.register_typedef(typedef_name, base_type, constraints)
    
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
                # Create context for evaluation
                from .xpath.context import Context
                context = Context(
                    data=data,
                    context_path=context_path.copy() if context_path else [],
                    original_context_path=context_path.copy() if context_path else [],
                    original_data=data,
                    root_data=data
                )
                # Use pre-parsed AST if available to avoid double parsing
                # YANG when statements should always have AST populated during parsing
                ast = getattr(stmt.when, 'ast', None)
                if ast is None:
                    # AST should have been populated during YANG parsing - this indicates a bug
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        "When statement AST not found for condition '%s' - will parse again. "
                        "This should not happen if YANG was parsed correctly.",
                        stmt.when.condition
                    )
                if not evaluator.evaluate(stmt.when.condition, ast=ast, context=context):
                    continue
            
            if isinstance(stmt, YangLeafStmt):
                # Validate leaf type
                self.type_validator.validate_leaf(data, stmt, context_path)
                
                # Leafref validation is lazy - only happens when deref() is called
                # or when the value is actually used in must constraints.
                # This allows OR short-circuiting to prevent unnecessary validation.
            
            elif isinstance(stmt, YangLeafListStmt):
                # Validate leaf-list type
                self.type_validator.validate_leaf_list(data, stmt)
            
            elif isinstance(stmt, YangListStmt):
                # Validate list items
                if stmt.name in data:
                    items = data[stmt.name]
                    if isinstance(items, list):
                        # Validate each list item
                        for item in items:
                            if isinstance(item, dict):
                                new_path = context_path + [stmt.name] if hasattr(stmt, 'name') else context_path
                                self._validate_types(
                                    item, stmt.statements, root_data, context_path=new_path
                                )
            
            elif isinstance(stmt, YangChoiceStmt):
                # Validate choice - exactly one case must be present if mandatory
                # At most one case can be present
                # Choice doesn't create a named node in the data - its cases do
                # So we check the current data context for case children
                choice_data = data if isinstance(data, dict) else {}
                
                # Count how many cases are present
                present_cases = []
                for case_stmt in stmt.cases:
                    # Check if any leaf from this case is present
                    case_present = False
                    for case_child in case_stmt.statements:
                        if isinstance(case_child, YangLeafStmt):
                            if case_child.name in choice_data:
                                case_present = True
                                break
                        elif hasattr(case_child, 'name') and case_child.name in choice_data:
                            case_present = True
                            break
                    
                    if case_present:
                        present_cases.append(case_stmt)
                
                # Validate choice constraints
                if stmt.mandatory:
                    if len(present_cases) == 0:
                        self.structure_validator.errors.append(
                            f"Mandatory choice '{stmt.name}' must have exactly one case present, but none found"
                        )
                    elif len(present_cases) > 1:
                        case_names = [c.name for c in present_cases]
                        self.structure_validator.errors.append(
                            f"Choice '{stmt.name}' must have exactly one case present, but found multiple: {', '.join(case_names)}"
                        )
                else:
                    if len(present_cases) > 1:
                        case_names = [c.name for c in present_cases]
                        self.structure_validator.errors.append(
                            f"Choice '{stmt.name}' can have at most one case present, but found multiple: {', '.join(case_names)}"
                        )
                
                # Validate the present case(s)
                for case_stmt in present_cases:
                    self._validate_types(
                        choice_data, case_stmt.statements, root_data, context_path=context_path
                    )
            
            elif isinstance(stmt, YangContainerStmt):
                # Validate container
                if stmt.name in data:
                    new_path = context_path + [stmt.name] if hasattr(stmt, 'name') else context_path
                    self._validate_types(
                        data[stmt.name], stmt.statements, root_data, context_path=new_path
                    )
            
            elif hasattr(stmt, 'statements'):
                # Recurse into composite statements (groupings, etc.)
                if stmt.name in data:
                    new_path = context_path + [stmt.name] if hasattr(stmt, 'name') else context_path
                    self._validate_types(
                        data[stmt.name], stmt.statements, root_data, context_path=new_path
                    )
    
    def _reset(self) -> None:
        """Reset all validators to initial state.

        Note: Caches are now per-evaluator (instance-level), so they don't need
        to be cleared here. Each validation creates a new XPathEvaluator with
        fresh caches, making parallel validations safe.
        """
        self.structure_validator.errors = []
        self.structure_validator.warnings = []
        self.type_validator.errors = []
        self.constraint_validator.errors = []
        self.leafref_resolver.errors = []
    
    def _are_all_cross_reference_errors(self, errors: List[str]) -> bool:
        """Check if all errors are cross-reference related.
        
        Cross-reference errors occur when validating individual files that reference
        entities or fields defined in other files. These are expected and should
        not trigger individual file validation.
        
        Args:
            errors: List of error messages
            
        Returns:
            True if all errors are cross-reference related, False otherwise
        """
        # Cross-reference error patterns (entity/field doesn't exist in another file)
        cross_ref_patterns = [
            "Foreign key entity must exist in the data model",
            "Foreign key field must exist in the referenced entity's fields",
            "Foreign key field must reference one of the parent entity's primary key fields",
            "Parent entity must have a primary key defined",
        ]
        
        # Check if ALL errors match cross-reference patterns
        return all(
            any(pattern in error for pattern in cross_ref_patterns)
            for error in errors
        )