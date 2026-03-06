"""
Structure validator for YANG data.
"""

from typing import Any, Dict, List
from ..module import YangModule
from ..ast import (
    YangStatement, YangLeafStmt, YangListStmt, YangLeafListStmt, YangContainerStmt, YangChoiceStmt, YangCaseStmt
)
from ..xpath import XPathEvaluator


class StructureValidator:
    """Validates data structure against YANG schema."""
    
    def __init__(self, module: YangModule, evaluator_factory=None):
        """
        Initialize structure validator.
        
        Args:
            module: YANG module to validate against
            evaluator_factory: Factory function for creating XPathEvaluator instances
        """
        self.module = module
        self.evaluator_factory = evaluator_factory or XPathEvaluator
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def validate(
        self, 
        data: Dict[str, Any], 
        statements: List[YangStatement],
        context_path: List[str] = None
    ) -> None:
        """
        Validate data structure against statements.
        
        Args:
            data: Data to validate
            statements: YANG statements to validate against
            context_path: Current path in data structure
        """
        if context_path is None:
            context_path = []
        
        # Collect all valid field names from statements (including choice cases)
        # IMPORTANT: Only collect field names from the statements passed to THIS validate() call.
        # This ensures the check is scoped to the current context, not global.
        valid_field_names = set()
        
        # First pass: collect valid field names, handling choice cases
        # Only consider fields defined in the current context's statements
        choice_data = data if isinstance(data, dict) else {}
        for stmt in statements:
            # Check when condition - skip if condition is false
            if hasattr(stmt, 'when') and stmt.when:
                evaluator = self.evaluator_factory(data, self.module, context_path=context_path)
                # Create context for evaluation
                from ..xpath.context import Context
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
                    # When condition is false, skip this statement
                    continue
            
            if isinstance(stmt, YangLeafStmt):
                if hasattr(stmt, 'name'):
                    valid_field_names.add(stmt.name)
            elif isinstance(stmt, YangListStmt):
                if hasattr(stmt, 'name'):
                    valid_field_names.add(stmt.name)
            elif isinstance(stmt, YangLeafListStmt):
                if hasattr(stmt, 'name'):
                    valid_field_names.add(stmt.name)
            elif isinstance(stmt, YangChoiceStmt):
                # Choice doesn't create a field, but its cases do
                # Check which case is present and collect its field names
                for case_stmt in stmt.cases:
                    # Check if any field from this case is present
                    case_active = False
                    for case_child in case_stmt.statements:
                        if isinstance(case_child, (YangLeafStmt, YangListStmt, YangLeafListStmt, YangContainerStmt)):
                            if hasattr(case_child, 'name') and case_child.name in choice_data:
                                case_active = True
                                break
                    
                    if case_active:
                        # This case is active - collect all its field names
                        for case_child in case_stmt.statements:
                            if isinstance(case_child, (YangLeafStmt, YangListStmt, YangLeafListStmt, YangContainerStmt)):
                                if hasattr(case_child, 'name'):
                                    valid_field_names.add(case_child.name)
            elif hasattr(stmt, 'statements'):
                # Container or other composite statement
                if hasattr(stmt, 'name'):
                    valid_field_names.add(stmt.name)
        
        # Second pass: validate the data
        for stmt in statements:
            # Check when condition - skip if condition is false
            if hasattr(stmt, 'when') and stmt.when:
                evaluator = self.evaluator_factory(data, self.module, context_path=context_path)
                # Create context for evaluation
                from ..xpath.context import Context
                context = Context(
                    data=data,
                    context_path=context_path.copy() if context_path else [],
                    original_context_path=context_path.copy() if context_path else [],
                    original_data=data,
                    root_data=data
                )
                # Use pre-parsed AST if available to avoid double parsing
                ast = getattr(stmt.when, 'ast', None)
                if ast is None:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        "When statement AST not found for condition '%s' - will parse again. "
                        "This should not happen if YANG was parsed correctly.",
                        stmt.when.condition
                    )
                if not evaluator.evaluate(stmt.when.condition, ast=ast, context=context):
                    # When condition is false, skip this statement
                    continue
            
            if isinstance(stmt, YangLeafStmt):
                self._validate_leaf(data, stmt, context_path)
            elif isinstance(stmt, YangListStmt):
                self._validate_list(data, stmt, context_path)
            elif isinstance(stmt, YangLeafListStmt):
                self._validate_leaf_list(data, stmt)
            elif hasattr(stmt, 'statements'):
                # Container or other composite statement
                if stmt.name in data:
                    new_path = context_path + [stmt.name] if hasattr(stmt, 'name') else context_path
                    child_statements = stmt.statements
                    self.validate(
                        data[stmt.name], child_statements, context_path=new_path
                    )
                elif (isinstance(stmt, YangContainerStmt) and
                      hasattr(stmt, 'presence') and stmt.presence):
                    # Presence container - if present in data, validate it
                    if stmt.name in data:
                        new_path = (context_path + [stmt.name]
                                     if hasattr(stmt, 'name') else context_path)
                        child_statements = stmt.statements
                        self.validate(
                            data[stmt.name], child_statements, context_path=new_path
                        )
        
        # Third pass: check for unknown fields (only if data is a dict)
        # IMPORTANT: Only check fields in the current data dict (local to this context).
        # Nested structures are validated recursively in separate validate() calls.
        if isinstance(data, dict):
            for field_name in data.keys():
                if field_name not in valid_field_names:
                    path_str = '/'.join(context_path) if context_path else 'root'
                    self.errors.append(
                        f"Unknown field '{field_name}' at path '{path_str}'. "
                        f"Field is not defined in the schema."
                    )
    
    def _validate_leaf(
        self, data: Dict[str, Any], leaf: YangLeafStmt, context_path: List[str]
    ) -> None:
        """Validate a leaf."""
        if leaf.name not in data:
            if leaf.mandatory:
                self.errors.append(f"Missing mandatory leaf: {leaf.name}")
            elif leaf.default is not None:
                # Default value would be applied
                pass
    
    def _validate_list(
        self, data: Dict[str, Any], list_stmt: YangListStmt, context_path: List[str]
    ) -> None:
        """Validate a list."""
        if list_stmt.name in data:
            items = data[list_stmt.name]
            if not isinstance(items, list):
                self.errors.append(
                    f"Expected list for {list_stmt.name}, got {type(items).__name__}"
                )
                return
            
            if list_stmt.min_elements is not None and len(items) < list_stmt.min_elements:
                self.errors.append(
                    f"List {list_stmt.name} has fewer than {list_stmt.min_elements} elements"
                )
            
            if list_stmt.max_elements is not None and len(items) > list_stmt.max_elements:
                self.errors.append(
                    f"List {list_stmt.name} has more than {list_stmt.max_elements} elements"
                )
            
            # Enforce list key uniqueness (YANG RFC 7950)
            if list_stmt.key and isinstance(items, list):
                key_parts = [k.strip() for k in list_stmt.key.split() if k.strip()]
                if key_parts:
                    seen_keys: List[tuple] = []
                    for idx, item in enumerate(items):
                        if not isinstance(item, dict):
                            continue
                        key_values = tuple(item.get(k) for k in key_parts)
                        if key_values in seen_keys:
                            self.errors.append(
                                f"List {list_stmt.name} has duplicate key value(s) "
                                f"{key_values} (key: {list_stmt.key})"
                            )
                            break
                        seen_keys.append(key_values)
            
            # Validate each item
            for item in items:
                if isinstance(item, dict):
                    # Pass context path for nested validation
                    item_path = (context_path + [list_stmt.name]
                                  if context_path else [list_stmt.name])
                    item_statements = list_stmt.statements
                    self.validate(item, item_statements, context_path=item_path)
    
    def _validate_leaf_list(self, data: Dict[str, Any], leaf_list: YangLeafListStmt) -> None:
        """Validate a leaf-list."""
        if leaf_list.name in data:
            items = data[leaf_list.name]
            if not isinstance(items, list):
                self.errors.append(
                    f"Expected list for {leaf_list.name}, got {type(items).__name__}"
                )
                return
            
            if leaf_list.min_elements is not None and len(items) < leaf_list.min_elements:
                self.errors.append(
                    f"Leaf-list {leaf_list.name} has fewer than "
                    f"{leaf_list.min_elements} elements"
                )
            
            if leaf_list.max_elements is not None and len(items) > leaf_list.max_elements:
                self.errors.append(
                    f"Leaf-list {leaf_list.name} has more than "
                    f"{leaf_list.max_elements} elements"
                )
    