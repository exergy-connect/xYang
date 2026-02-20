"""
Constraint validator for YANG must/when statements.
"""

import logging
from typing import Any, Dict, List
from ..module import YangModule
from ..ast import YangStatement, YangLeafStmt, YangListStmt, YangContainerStmt, YangLeafListStmt
from ..xpath import XPathEvaluator

logger = logging.getLogger(__name__)


class ConstraintValidator:
    """Validates must constraints using XPath evaluator."""
    
    def __init__(self, module: YangModule, evaluator_factory=None):
        """
        Initialize constraint validator.
        
        Args:
            module: YANG module
            evaluator_factory: Factory function for creating XPathEvaluator instances
        """
        self.module = module
        self.evaluator_factory = evaluator_factory or XPathEvaluator
        self.errors: List[str] = []
    
    def validate_must_statements(self, data: Dict[str, Any], root_data: Dict[str, Any] = None) -> None:
        """
        Validate must statements using XPath evaluator.
        
        Args:
            data: Data to validate
            root_data: Root data structure (for absolute paths and cross-references)
        """
        # Use root_data if provided, otherwise use data as root
        root = root_data if root_data is not None else data
        
        logger.info("Starting must statement validation, root keys: %s", list(root.keys()) if isinstance(root, dict) else "N/A")
        
        # Create evaluator with root context
        evaluator = self.evaluator_factory(root, self.module, context_path=[])
        
        # Store root data in evaluator for absolute path resolution
        if hasattr(evaluator, 'root_data'):
            evaluator.root_data = root
        
        # Validate must statements recursively
        logger.info("Module has %d top-level statements", len(self.module.statements))
        for stmt in self.module.statements:
            logger.debug("Validating must statements in top-level statement: %s", stmt.name if hasattr(stmt, 'name') else type(stmt).__name__)
            self._validate_must_in_statement(data, stmt, evaluator, [])
    
    def _navigate_path(self, root_data: Dict[str, Any], path: List[str]) -> Any:
        """
        Navigate through data structure following the given path.
        
        Args:
            root_data: Root data structure to navigate from
            path: List of path parts (strings for dict keys, ints for list indices)
            
        Returns:
            The data at the path, or None if path doesn't exist
        """
        current = root_data
        for p in path:
            if current is None:
                return None
            if isinstance(current, dict):
                if p in current:
                    current = current[p]
                else:
                    return None
            elif isinstance(current, list):
                if isinstance(p, int) and 0 <= p < len(current):
                    current = current[p]
                else:
                    return None
            else:
                # Primitive value - can't navigate further
                return None
        return current
    
    def _get_root_data(self, evaluator: XPathEvaluator, fallback: Dict[str, Any]) -> Dict[str, Any]:
        """Get root_data from evaluator or use fallback."""
        return evaluator.root_data if hasattr(evaluator, 'root_data') else fallback
    
    def _setup_evaluator_context(
        self, 
        evaluator: XPathEvaluator, 
        context_path: List[str], 
        root_data: Dict[str, Any]
    ) -> None:
        """
        Set up evaluator context for must constraint evaluation.
        
        Args:
            evaluator: XPath evaluator to configure
            context_path: Current path in data structure
            root_data: Root data structure
        """
        evaluator.context_path = context_path
        evaluator.original_context_path = context_path.copy() if context_path else []
        evaluator.original_data = root_data
        
        # Navigate to current data context
        current_data = self._navigate_path(root_data, context_path)
        
        # Set evaluator.data appropriately
        if current_data is not None and not isinstance(current_data, (dict, list)):
            # Primitive value - use root_data so current() can navigate via context_path
            evaluator.data = root_data
        elif current_data is not None:
            evaluator.data = current_data
        else:
            # Path doesn't exist - use root_data as fallback
            evaluator.data = root_data
    
    def _resolve_schema_node_by_path(
        self,
        evaluator: XPathEvaluator,
        data_path: List[str]
    ) -> YangStatement:
        """
        Resolve a schema node by full data path.
        
        This ensures we match constraints to the correct schema node by full path,
        not just by name. For example, fields[].foreignKey.field vs computed.fields[].field
        are different schema nodes even though both have a leaf named "field".
        
        Args:
            evaluator: XPath evaluator (has access to deref_evaluator)
            data_path: Current path in data structure (may contain list indices)
            
        Returns:
            The schema node (YangStatement) at this path, or None if not found
        """
        if not hasattr(evaluator, 'deref_evaluator'):
            logger.warning("Evaluator does not have deref_evaluator, cannot resolve schema node by path")
            return None
        
        # Convert data path to schema path (removes list indices)
        schema_path = evaluator.deref_evaluator.data_path_to_schema_path(data_path)
        
        logger.debug(
            "Resolving schema node: data_path=%s -> schema_path=%s",
            data_path, schema_path
        )
        
        # Find the schema node at this path
        schema_node = evaluator.deref_evaluator.find_schema_node(schema_path)
        
        if schema_node:
            logger.debug(
                "Resolved schema node: path=%s -> node=%s (type=%s, has_must=%s)",
                schema_path,
                schema_node.name if hasattr(schema_node, 'name') else 'N/A',
                type(schema_node).__name__,
                len(schema_node.must_statements) if hasattr(schema_node, 'must_statements') else 0
            )
        else:
            logger.warning(
                "Could not resolve schema node: data_path=%s -> schema_path=%s",
                data_path, schema_path
            )
        
        return schema_node
    
    def _get_schema_path_for_node(self, node: YangStatement) -> str:
        """
        Get a human-readable schema path for a node (for logging).
        
        Args:
            node: Schema node
            
        Returns:
            String representation of the schema path
        """
        # This is a simplified version - in a full implementation, we'd walk up the tree
        # For now, just return the node name
        return node.name if hasattr(node, 'name') else type(node).__name__
    
    def _validate_child_in_list_item(
        self,
        root_data: Dict[str, Any],
        child_stmt: YangStatement,
        evaluator: XPathEvaluator,
        item_path: List[str]
    ) -> None:
        """Validate a child statement within a list item (without recursion).
        
        This is used when iterating through list items to validate child statements
        for each item. It only validates the immediate child's constraints, not grandchildren.
        """
        child_path = item_path + [child_stmt.name] if hasattr(child_stmt, 'name') else item_path
        
        logger.debug("_validate_child_in_list_item: child=%s, path=%s", 
                    child_stmt.name if hasattr(child_stmt, 'name') else type(child_stmt).__name__, 
                    child_path)
        
        # Set up evaluator context
        self._setup_evaluator_context(evaluator, child_path, root_data)
        
        # Validate must statements on this child statement only
        if isinstance(child_stmt, YangLeafStmt):
            # Resolve the schema node by full path to ensure we're validating the correct node
            actual_schema_node = self._resolve_schema_node_by_path(evaluator, child_path)
            
            # If we couldn't resolve the schema node, fall back to the passed statement
            if actual_schema_node is None:
                logger.warning(
                    "Could not resolve schema node for path %s in list item, using passed statement %s",
                    child_path, child_stmt.name
                )
                actual_schema_node = child_stmt
            elif actual_schema_node != child_stmt:
                logger.debug(
                    "Schema node mismatch in list item: path %s resolved to %s, but passed statement was %s. Using resolved node.",
                    child_path,
                    actual_schema_node.name if hasattr(actual_schema_node, 'name') else type(actual_schema_node).__name__,
                    child_stmt.name
                )
            
            # Check if field exists in current data context
            field_exists = (
                isinstance(evaluator.data, dict) and actual_schema_node.name in evaluator.data
            )
            
            logger.debug("Leaf %s in list item: field_exists=%s, mandatory=%s, has_must=%s, path=%s, resolved_schema_path=%s",
                        actual_schema_node.name, field_exists, actual_schema_node.mandatory, 
                        len(actual_schema_node.must_statements) > 0, child_path,
                        self._get_schema_path_for_node(actual_schema_node))
            
            # Skip validation if the field doesn't exist (optional fields)
            if not field_exists:
                if not (actual_schema_node.mandatory or (hasattr(actual_schema_node, 'default') and actual_schema_node.default is not None)):
                    logger.debug("Skipping validation for optional missing field in list item: %s", actual_schema_node.name)
                    return  # Skip validation for missing optional fields
            
            # Evaluate must constraints from the resolved schema node
            logger.debug("Evaluating %d must constraints for leaf %s in list item", len(actual_schema_node.must_statements), actual_schema_node.name)
            for must in actual_schema_node.must_statements:
                evaluator.original_data = root_data
                evaluator.original_context_path = child_path.copy() if child_path else []
                self._evaluate_must_constraint(evaluator, must, actual_schema_node.name, actual_schema_node.mandatory, actual_schema_node)
        
        elif isinstance(child_stmt, YangLeafListStmt):
            # Leaf-list: evaluate must constraints per-element with current() bound to each value
            # Get the leaf-list values from root_data
            leaf_list_data = self._navigate_path(root_data, child_path)
            
            # Check if field exists - navigate to parent and check
            parent_path = child_path[:-1] if len(child_path) > 0 else []
            parent_data = self._navigate_path(root_data, parent_path) if parent_path else root_data
            field_exists = (
                isinstance(parent_data, dict) and child_stmt.name in parent_data
            )
            
            logger.debug(
                "Leaf-list %s in list item: field_exists=%s, has_must=%s, path=%s, leaf_list_data=%s",
                child_stmt.name, field_exists, len(child_stmt.must_statements) > 0, child_path, 
                type(leaf_list_data).__name__ if leaf_list_data is not None else "None"
            )
            
            # Skip validation if the field doesn't exist (optional fields)
            if not field_exists:
                logger.debug("Skipping validation for optional missing leaf-list in list item: %s", child_stmt.name)
                return  # Skip validation for missing optional fields
            
            # Verify leaf-list data is actually a list
            if not isinstance(leaf_list_data, list):
                logger.debug("Leaf-list %s data is not a list (type: %s), skipping must validation", 
                           child_stmt.name, type(leaf_list_data).__name__ if leaf_list_data is not None else "None")
                return
            
            # Evaluate must constraints once per value with current() bound to each value
            logger.debug("Evaluating %d must constraints for leaf-list %s with %d values", 
                        len(child_stmt.must_statements), child_stmt.name, len(leaf_list_data))
            for value_idx, value in enumerate(leaf_list_data):
                # Set up evaluator context for this specific value
                # current() should be bound to this value
                value_path = child_path + [value_idx]
                self._setup_evaluator_context(evaluator, value_path, root_data)
                
                # Set original context so current() returns this value
                evaluator.original_data = root_data
                evaluator.original_context_path = value_path.copy() if value_path else []
                
                # Evaluate each must constraint for this value
                for must in child_stmt.must_statements:
                    logger.debug("Evaluating must constraint for leaf-list %s value[%d]=%s in list item", 
                               child_stmt.name, value_idx, value)
                    self._evaluate_must_constraint(evaluator, must, f"{child_stmt.name}[{value_idx}]", False, child_stmt)
        
        elif isinstance(child_stmt, (YangListStmt, YangContainerStmt)):
            # Check if container/list exists in data before validating
            container_data = self._navigate_path(root_data, child_path)
            if container_data is None:
                # Container/list doesn't exist in data - skip validation
                logger.debug("Container/List %s does not exist in data at path %s, skipping validation", 
                            child_stmt.name, child_path)
                return
            
            logger.debug("Container/List %s in list item: has_must=%s, path=%s",
                        child_stmt.name, hasattr(child_stmt, 'must_statements') and len(child_stmt.must_statements) > 0, child_path)
            if hasattr(child_stmt, 'must_statements'):
                for must in child_stmt.must_statements:
                    evaluator.original_data = root_data
                    evaluator.original_context_path = child_path.copy() if child_path else []
                    self._evaluate_must_constraint(evaluator, must, child_stmt.name, False, child_stmt)
            
            # If this is a list or container, we need to recurse into its items/children to validate grandchildren
            if isinstance(child_stmt, YangListStmt):
                list_data = self._navigate_path(root_data, child_path)
                logger.debug("Nested list %s: list_data type=%s, is_list=%s, path=%s", 
                            child_stmt.name, type(list_data).__name__, isinstance(list_data, list), child_path)
                if isinstance(list_data, list):
                    logger.debug("Nested list %s has %d items", child_stmt.name, len(list_data))
                    # Validate each list item
                    for idx, item in enumerate(list_data):
                        item_path = child_path + [idx]
                        logger.debug("Validating nested list item %d at path %s", idx, item_path)
                        # Set up evaluator context for this nested list item
                        self._setup_evaluator_context(evaluator, item_path, root_data)
                        # Validate child statements for this nested list item
                        for grandchild in child_stmt.statements:
                            logger.debug("Validating grandchild %s in nested list item %d", 
                                        grandchild.name if hasattr(grandchild, 'name') else type(grandchild).__name__, idx)
                            self._validate_child_in_list_item(root_data, grandchild, evaluator, item_path)
            elif isinstance(child_stmt, YangContainerStmt):
                # For containers, recurse into their children
                container_data = self._navigate_path(root_data, child_path)
                logger.debug("Nested container %s: container_data type=%s, path=%s, has_children=%s, data=%s", 
                            child_stmt.name, type(container_data).__name__, child_path, 
                            hasattr(child_stmt, 'statements') and len(child_stmt.statements) > 0,
                            str(container_data)[:100] if container_data else "None")
                # Debug: Check what data exists at parent path
                if container_data is None and len(child_path) > 0:
                    parent_path = child_path[:-1]
                    parent_data = self._navigate_path(root_data, parent_path)
                    logger.debug("  Parent path %s has data type=%s, keys=%s", 
                               parent_path, type(parent_data).__name__,
                               list(parent_data.keys())[:10] if isinstance(parent_data, dict) else f"list[{len(parent_data)}]" if isinstance(parent_data, list) else "N/A")
                if hasattr(child_stmt, 'statements') and child_stmt.statements:
                    # Validate child statements of the container
                    for grandchild in child_stmt.statements:
                        logger.debug("Validating grandchild %s in container %s", 
                                    grandchild.name if hasattr(grandchild, 'name') else type(grandchild).__name__, 
                                    child_stmt.name)
                        # If grandchild is a list, we need to handle it specially
                        if isinstance(grandchild, YangListStmt):
                            grandchild_path = child_path + [grandchild.name]
                            grandchild_data = self._navigate_path(root_data, grandchild_path)
                            logger.debug("Grandchild list %s: data type=%s, is_list=%s, path=%s, data=%s",
                                        grandchild.name, type(grandchild_data).__name__, isinstance(grandchild_data, list), grandchild_path,
                                        str(grandchild_data)[:100] if grandchild_data else "None")
                            # Note: We no longer skip computed.fields - path-based schema node resolution ensures
                            # that computed.fields[].field only gets constraints from its own schema node,
                            # not from fields[].foreignKey.field
                            if isinstance(grandchild_data, list):
                                logger.debug("Grandchild list %s has %d items", grandchild.name, len(grandchild_data))
                                for idx, item in enumerate(grandchild_data):
                                    item_path = grandchild_path + [idx]
                                    logger.debug("Validating grandchild list item %d at path %s, item keys=%s", 
                                               idx, item_path, list(item.keys())[:5] if isinstance(item, dict) else "N/A")
                                    self._setup_evaluator_context(evaluator, item_path, root_data)
                                    for great_grandchild in grandchild.statements:
                                        logger.debug("Validating great-grandchild %s in list item %d",
                                                    great_grandchild.name if hasattr(great_grandchild, 'name') else type(great_grandchild).__name__, idx)
                                        # Pass the statement for type checking in constraint evaluation
                                        self._validate_child_in_list_item(root_data, great_grandchild, evaluator, item_path)
                            else:
                                logger.warning("Grandchild list %s data is not a list at path %s", grandchild.name, grandchild_path)
                        else:
                            self._validate_child_in_list_item(root_data, grandchild, evaluator, child_path)
        
        # Note: For containers that aren't handled above, grandchildren are handled by the normal recursion path
        # when _validate_must_in_statement is called for the container statement itself
    
    def _evaluate_must_constraint(
        self,
        evaluator: XPathEvaluator,
        must_expr: Any,
        field_name: str,
        is_mandatory: bool,
        stmt: YangStatement = None
    ) -> None:
        """
        Evaluate a must constraint and add error if it fails.
        
        Args:
            evaluator: XPath evaluator
            must_expr: Must statement with expression and error_message
            field_name: Name of field being validated (for error messages)
            is_mandatory: Whether the field is mandatory
            stmt: The schema statement being validated (optional, for type checking)
        """
        # Check if constraint uses deref() - these should only be applied to leafref nodes
        # Constraints that use deref() are only valid for leafref types or containers/lists
        # that contain leafref children. For leaf statements, we must check the type.
        expression = getattr(must_expr, 'expression', '') or ''
        if 'deref(' in expression.lower():
            # Get context path to check if we're in computed.fields
            context_path = getattr(evaluator, 'original_context_path', None) or getattr(evaluator, 'context_path', [])
            
            # First check: if we're in computed.fields, never apply deref() constraints
            # (computed.fields[].field has type field-name, not leafref)
            if 'computed' in context_path:
                try:
                    computed_idx = context_path.index("computed")
                    if computed_idx + 1 < len(context_path) and context_path[computed_idx + 1] == "fields":
                        logger.debug(
                            "Skipping deref() constraint for field %s inside computed.fields (path: %s)",
                            field_name, context_path
                        )
                        return
                except (ValueError, AttributeError):
                    pass
            
            # Second check: if statement is provided, check if it's a leafref type
            if stmt:
                if isinstance(stmt, YangLeafStmt):
                    stmt_type_name = stmt.type.name if stmt.type else None
                    if stmt_type_name != 'leafref':
                        # Skip deref() constraints for non-leafref leaves
                        # This prevents foreign key constraints from being applied to computed.fields[].field
                        logger.debug(
                            "Skipping deref() constraint for non-leafref leaf %s (type: %s, path: %s)",
                            field_name, stmt_type_name, context_path
                        )
                        return
                # For containers/lists, deref() constraints are allowed (they may reference leafref children)
                # So we don't skip them here
            else:
                # If no statement provided, check context path as fallback
                # This handles cases where stmt might not be passed correctly
                if 'computed' in context_path and 'fields' in context_path:
                    try:
                        computed_idx = context_path.index("computed")
                        if computed_idx + 1 < len(context_path) and context_path[computed_idx + 1] == "fields":
                            logger.debug(
                                "Skipping deref() constraint for field %s inside computed.fields (fallback check, path: %s)",
                                field_name, context_path
                            )
                            return
                    except (ValueError, AttributeError):
                        pass
        
        # Debug: Log constraint evaluation
        context_path = getattr(evaluator, 'original_context_path', None) or getattr(evaluator, 'context_path', [])
        stmt_info = f"stmt={type(stmt).__name__}" if stmt else "stmt=None"
        if stmt and isinstance(stmt, YangLeafStmt):
            stmt_info += f", type={stmt.type.name if stmt.type else 'None'}"
        logger.info(
            "Evaluating must constraint for %s (%s): expression='%s', error_message='%s', context_path=%s",
            field_name, stmt_info,
            must_expr.expression if hasattr(must_expr, 'expression') else str(must_expr),
            must_expr.error_message if hasattr(must_expr, 'error_message') else 'N/A',
            context_path
        )
        
        try:
            # Use pre-parsed AST if available to avoid double parsing
            ast = getattr(must_expr, 'ast', None)
            result = evaluator.evaluate(must_expr.expression, ast=ast)
            logger.info(
                "Must constraint result for %s: %s (expression: %s)",
                field_name, result, must_expr.expression
            )
            if not result:
                # Use error_message if available, otherwise fall back to description, then generic message
                error_msg = (
                    must_expr.error_message or 
                    (must_expr.description if hasattr(must_expr, 'description') and must_expr.description else None) or
                    f"Must constraint failed for {field_name}"
                )
                logger.warning("Must constraint failed for %s: %s", field_name, error_msg)
                self.errors.append(error_msg)
        except Exception as e:
            # Log evaluation failures for debugging
            logger.warning(
                "Must constraint evaluation failed for %s: %s (expression: %s, context_path=%s)",
                field_name, e, must_expr.expression, getattr(evaluator, 'context_path', [])
            )
            # Only add error if field is mandatory or if it's a syntax error
            if is_mandatory or "syntax" in str(e).lower() or "parse" in str(e).lower():
                # Use error_message if available, otherwise fall back to description, then generic message
                error_msg = (
                    must_expr.error_message or 
                    (must_expr.description if hasattr(must_expr, 'description') and must_expr.description else None) or
                    f"Must constraint evaluation failed for {field_name}: {e}"
                )
                self.errors.append(error_msg)
    
    def _validate_must_in_statement(
        self, 
        data: Dict[str, Any], 
        stmt: YangStatement,
        evaluator: XPathEvaluator, 
        path: List[str]
    ) -> None:
        """
        Recursively validate must statements in a statement.
        
        Args:
            data: Data to validate (legacy parameter, not used)
            stmt: Statement to check
            evaluator: XPath evaluator (will be updated with context)
            path: Current path in data structure
        """
        current_path = path + [stmt.name] if hasattr(stmt, 'name') else path
        root_data = self._get_root_data(evaluator, data)
        
        # Set up evaluator context
        self._setup_evaluator_context(evaluator, current_path, root_data)
        
        # Validate must statements on this statement
        if isinstance(stmt, YangLeafStmt):
            # Resolve the schema node by full path to ensure we're validating the correct node
            # This prevents matching constraints from nodes with the same name but different paths
            # (e.g., fields[].foreignKey.field vs computed.fields[].field)
            actual_schema_node = self._resolve_schema_node_by_path(evaluator, current_path)
            
            # If we couldn't resolve the schema node, fall back to the passed statement
            # but log a warning
            if actual_schema_node is None:
                logger.warning(
                    "Could not resolve schema node for path %s, using passed statement %s",
                    current_path, stmt.name
                )
                actual_schema_node = stmt
            elif actual_schema_node != stmt:
                logger.debug(
                    "Schema node mismatch: path %s resolved to %s, but passed statement was %s. Using resolved node.",
                    current_path,
                    actual_schema_node.name if hasattr(actual_schema_node, 'name') else type(actual_schema_node).__name__,
                    stmt.name
                )
            
            # Check if field exists - need to check parent data, not current data
            # (current data might be the field value itself after navigation)
            parent_path = current_path[:-1] if len(current_path) > 0 else []
            parent_data = self._navigate_path(root_data, parent_path) if parent_path else root_data
            field_exists = (
                isinstance(parent_data, dict) and actual_schema_node.name in parent_data
            )
            
            logger.debug(
                "Validating leaf %s: field_exists=%s, mandatory=%s, has_must=%s, path=%s, resolved_schema_path=%s",
                actual_schema_node.name, field_exists, actual_schema_node.mandatory, 
                len(actual_schema_node.must_statements) > 0, current_path,
                self._get_schema_path_for_node(actual_schema_node)
            )
            
            # Skip validation if the field doesn't exist (optional fields)
            if not field_exists:
                if not (actual_schema_node.mandatory or (hasattr(actual_schema_node, 'default') and actual_schema_node.default is not None)):
                    logger.debug("Skipping validation for optional missing field: %s", actual_schema_node.name)
                    return  # Skip validation for missing optional fields
            
            # Evaluate must constraints from the resolved schema node
            logger.debug("Evaluating %d must constraints for leaf %s", len(actual_schema_node.must_statements), actual_schema_node.name)
            for must in actual_schema_node.must_statements:
                # Ensure original_data is set before each evaluation
                evaluator.original_data = root_data
                evaluator.original_context_path = current_path.copy() if current_path else []
                self._evaluate_must_constraint(evaluator, must, actual_schema_node.name, actual_schema_node.mandatory, actual_schema_node)
        
        elif isinstance(stmt, YangLeafListStmt):
            # Leaf-list: evaluate must constraints per-element with current() bound to each value
            # Get the leaf-list values from root_data
            leaf_list_data = self._navigate_path(root_data, current_path)
            
            # Check if field exists - navigate to parent and check
            parent_path = current_path[:-1] if len(current_path) > 0 else []
            parent_data = self._navigate_path(root_data, parent_path) if parent_path else root_data
            field_exists = (
                isinstance(parent_data, dict) and stmt.name in parent_data
            )
            
            logger.debug(
                "Validating leaf-list %s: field_exists=%s, has_must=%s, path=%s, leaf_list_data=%s",
                stmt.name, field_exists, len(stmt.must_statements) > 0, current_path, 
                type(leaf_list_data).__name__ if leaf_list_data is not None else "None"
            )
            
            # Skip validation if the field doesn't exist (optional fields)
            if not field_exists:
                logger.debug("Skipping validation for optional missing leaf-list: %s", stmt.name)
                return  # Skip validation for missing optional fields
            
            # Verify leaf-list data is actually a list
            if not isinstance(leaf_list_data, list):
                logger.debug("Leaf-list %s data is not a list (type: %s), skipping must validation", 
                           stmt.name, type(leaf_list_data).__name__ if leaf_list_data is not None else "None")
                return
            
            # Evaluate must constraints once per value with current() bound to each value
            logger.debug("Evaluating %d must constraints for leaf-list %s with %d values", 
                        len(stmt.must_statements), stmt.name, len(leaf_list_data))
            for value_idx, value in enumerate(leaf_list_data):
                # Set up evaluator context for this specific value
                # current() should be bound to this value
                value_path = current_path + [value_idx]
                self._setup_evaluator_context(evaluator, value_path, root_data)
                
                # Set original context so current() returns this value
                evaluator.original_data = root_data
                evaluator.original_context_path = value_path.copy() if value_path else []
                
                # Evaluate each must constraint for this value
                for must in stmt.must_statements:
                    logger.debug("Evaluating must constraint for leaf-list %s value[%d]=%s", 
                               stmt.name, value_idx, value)
                    self._evaluate_must_constraint(evaluator, must, f"{stmt.name}[{value_idx}]", False, stmt)
                
        elif isinstance(stmt, (YangListStmt, YangContainerStmt)):
            # Check if container/list exists in data before validating
            container_data = self._navigate_path(root_data, current_path)
            if container_data is None:
                # Container/list doesn't exist in data - skip validation
                logger.debug("Container/List %s does not exist in data at path %s, skipping validation", 
                            stmt.name if hasattr(stmt, 'name') else type(stmt).__name__, current_path)
                return
            
            # For list statements, must constraints should be evaluated for each list item
            # For container statements, must constraints are evaluated at the container level
            if isinstance(stmt, YangListStmt):
                list_data = container_data if isinstance(container_data, list) else None
                if list_data:
                    # Evaluate must constraints for each list item
                    for idx, item in enumerate(list_data):
                        item_path = current_path + [idx]
                        self._setup_evaluator_context(evaluator, item_path, root_data)
                        if hasattr(stmt, 'must_statements'):
                            for must in stmt.must_statements:
                                evaluator.original_data = root_data
                                evaluator.original_context_path = item_path.copy() if item_path else []
                                self._evaluate_must_constraint(evaluator, must, f"{stmt.name}[{idx}]", False, stmt)
                else:
                    # List doesn't exist or is not a list - evaluate at list level
                    if hasattr(stmt, 'must_statements'):
                        for must in stmt.must_statements:
                            evaluator.original_data = root_data
                            evaluator.original_context_path = current_path.copy() if current_path else []
                            self._evaluate_must_constraint(evaluator, must, stmt.name, False, stmt)
            else:
                # Container: evaluate must constraints at container level
                if hasattr(stmt, 'must_statements'):
                    for must in stmt.must_statements:
                        evaluator.original_data = root_data
                        evaluator.original_context_path = current_path.copy() if current_path else []
                        self._evaluate_must_constraint(evaluator, must, stmt.name, False, stmt)
        
        # Recurse into child statements
        if hasattr(stmt, 'statements'):
            logger.debug("Statement %s has %d child statements", stmt.name if hasattr(stmt, 'name') else type(stmt).__name__, len(stmt.statements))
            # For list statements, iterate through actual list items in data
            if isinstance(stmt, YangListStmt):
                list_data = self._navigate_path(root_data, current_path)
                logger.debug("List %s: list_data type=%s, is_list=%s", stmt.name, type(list_data).__name__, isinstance(list_data, list))
                if isinstance(list_data, list):
                    logger.debug("List %s has %d items", stmt.name, len(list_data))
                    # Validate each list item with its index in the path
                    for idx, item in enumerate(list_data):
                        item_path = current_path + [idx]
                        logger.debug("Validating list item %d at path %s", idx, item_path)
                        # Set up evaluator context for this list item
                        self._setup_evaluator_context(evaluator, item_path, root_data)
                        # Validate child statements for this list item
                        # Use a helper to validate children without double recursion
                        for child in stmt.statements:
                            logger.debug("Validating child %s in list item %d", child.name if hasattr(child, 'name') else type(child).__name__, idx)
                            self._validate_child_in_list_item(root_data, child, evaluator, item_path)
                else:
                    # List doesn't exist or is not a list - validate child statements normally
                    logger.debug("List %s data is not a list, validating children normally", stmt.name)
                    for child in stmt.statements:
                        child_data = self._navigate_path(root_data, current_path)
                        if child_data is None:
                            child_data = root_data
                        self._validate_must_in_statement(child_data, child, evaluator, current_path)
            else:
                # For non-list statements, validate child statements normally
                logger.debug("Non-list statement %s, validating %d children", stmt.name if hasattr(stmt, 'name') else type(stmt).__name__, len(stmt.statements))
                for child in stmt.statements:
                    # Navigate to child data from root_data
                    child_data = self._navigate_path(root_data, current_path)
                    if child_data is None:
                        child_data = root_data
                    logger.debug("Validating child %s of %s", child.name if hasattr(child, 'name') else type(child).__name__, stmt.name if hasattr(stmt, 'name') else type(stmt).__name__)
                    self._validate_must_in_statement(child_data, child, evaluator, current_path)