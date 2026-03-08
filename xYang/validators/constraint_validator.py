"""
Constraint validator for YANG must/when statements.
"""

import logging
import re
from typing import Any, Dict, List, Iterator, Optional
from ..module import YangModule
from ..ast import YangStatement, YangLeafStmt, YangListStmt, YangContainerStmt, YangLeafListStmt
from ..xpath import XPathEvaluator
from ..xpath.context import Context
from ..xpath.utils import xpath_string

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
        self._validation_root = root  # Keep full root for navigation in recursive calls (Phase 1)

        logger.info("Starting must statement validation, root keys: %s", list(root.keys()) if isinstance(root, dict) else "N/A")

        # Create evaluator with root context
        # Note: Caches are cleared at YangValidator level, so each validation starts fresh
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
        """Get root_data for navigation. Prefer validation root so recursive must validation
        always navigates from the full tree (e.g. parent_path ['data-model'] from leaf
        allow_unlimited_fields resolves correctly in Phase 1)."""
        if getattr(self, '_validation_root', None) is not None:
            return self._validation_root
        return evaluator.root_data if hasattr(evaluator, 'root_data') else fallback
    
    def _create_evaluator_context(
        self,
        context_path: List[str],
        root_data: Dict[str, Any]
    ) -> Context:
        """
        Create evaluator context for must constraint evaluation.
    
        Args:
            context_path: Current path in data structure
            root_data: Root data structure
            
        Returns:
            Context object for evaluation
        """
        from ..xpath.context import Context
        
        # Navigate to current data context
        current_data = self._navigate_path(root_data, context_path)
        
        # Create context with appropriate data
        # For primitive values (like leaf values), set data to the primitive so that
        # . (current node) returns the value directly, while current() can still navigate
        # via original_context_path to get the same value
        if current_data is not None and not isinstance(current_data, (dict, list)):
            # Primitive value - set data to the primitive for . to work correctly
            # but keep root_data for current() navigation
            data = current_data
        elif current_data is not None:
            data = current_data
        else:
            # Path doesn't exist - use root_data as fallback
            data = root_data
        
        return Context(
            data=data,
            context_path=context_path.copy() if context_path else [],
            original_context_path=context_path.copy() if context_path else [],
            original_data=root_data,
            root_data=root_data
        )
    
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
    
    def _process_dynamic_error_message(
        self,
        error_message: str,
        evaluator: XPathEvaluator,
        context: Context
    ) -> str:
        """
        Process error message with dynamic XPath expressions in curly braces.
        
        Replaces expressions like {current()} or {../../name} with their evaluated values.
        Uses Python f-string style syntax: {expression}
        
        Args:
            error_message: Error message template with optional {expression} placeholders
            evaluator: XPath evaluator for evaluating expressions
            context: Context for evaluation
            
        Returns:
            Error message with XPath expressions replaced by their values
        """
        if not error_message or '{' not in error_message:
            return error_message
        
        # Pattern to match {expression} where expression is an XPath expression
        # This handles nested braces by matching from innermost to outermost
        pattern = r'\{([^}]+)\}'
        
        def replace_match(match: re.Match) -> str:
            """Replace a single {expression} match with its evaluated value."""
            xpath_expr = match.group(1)
            try:
                # Evaluate the XPath expression
                value = evaluator.evaluate_value(xpath_expr, context=context)
                # Convert to string using XPath string conversion rules
                return xpath_string(value)
            except Exception as e:
                # If evaluation fails, include the expression and error in the message
                logger.debug(
                    "Failed to evaluate XPath expression '%s' in error message: %s",
                    xpath_expr, e
                )
                return f"<{xpath_expr} evaluation failed: {e}>"
        
        # Replace all {expression} patterns
        processed_message = re.sub(pattern, replace_match, error_message)
        return processed_message
    
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
        
        # Create evaluator context
        context = self._create_evaluator_context(child_path, root_data)
        
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
            
            # Check if field exists in parent data context
            # Navigate to parent to check if field exists there
            parent_path = child_path[:-1] if len(child_path) > 0 else []
            parent_data = self._navigate_path(root_data, parent_path) if parent_path else root_data
            field_exists = (
                isinstance(parent_data, dict) and actual_schema_node.name in parent_data
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
                # Create context for this specific child path
                child_context = self._create_evaluator_context(child_path, root_data)
                self._evaluate_must_constraint(evaluator, must, actual_schema_node.name, actual_schema_node.mandatory, child_context, actual_schema_node)
        
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
                # Create evaluator context for this specific value
                # current() should be bound to this value
                value_path = child_path + [value_idx]
                value_context = self._create_evaluator_context(value_path, root_data)
                
                # Evaluate each must constraint for this value
                for must in child_stmt.must_statements:
                    logger.debug("Evaluating must constraint for leaf-list %s value[%d]=%s in list item", 
                               child_stmt.name, value_idx, value)
                    self._evaluate_must_constraint(evaluator, must, f"{child_stmt.name}[{value_idx}]", False, value_context, child_stmt)
        
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
                    child_context = self._create_evaluator_context(child_path, root_data)
                    self._evaluate_must_constraint(evaluator, must, child_stmt.name, False, child_context, child_stmt)
            
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
                        # Context is created per-statement in _validate_must_in_statement
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
                                    # Context is created per-statement in _validate_must_in_statement
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
        context: Context,
        stmt: YangStatement = None
    ) -> None:
        """
        Evaluate a must constraint and add error if it fails.
        
        Args:
            evaluator: XPath evaluator
            must_expr: Must statement with expression and error_message
            field_name: Name of field being validated (for error messages)
            is_mandatory: Whether the field is mandatory
            context: Context for evaluation (required, never None)
            stmt: The schema statement being validated (optional, for type checking)
        
        Note:
            The deref() function validation is handled by the deref evaluator itself.
            If deref() is called on a non-leafref node, it will return None, causing
            the constraint to fail naturally. No special-case logic is needed here.
        """
        
        # Debug: Log constraint evaluation
        context_path = context.original_context_path if context.original_context_path else context.context_path
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
        
        ast = getattr(must_expr, 'ast', None)
        if ast is None:
            expr_str = must_expr.expression if hasattr(must_expr, 'expression') else str(must_expr)
            self.errors.append(
                f"Must constraint has no AST (expression not parsed during YANG parsing): {expr_str!r}"
            )
            return
        try:
            result = evaluator.evaluate_ast(ast, context)
            if logger.isEnabledFor(logging.DEBUG):
                raw_result = evaluator.evaluate_value_ast(ast, context)
                logger.debug(
                    "Must constraint result for %s: %s (raw: %s, expression: %s)",
                    field_name, result, raw_result, getattr(must_expr, 'expression', '')
                )
            if not result:
                # Use error_message if available, otherwise fall back to description, then generic message
                base_error_msg = (
                    must_expr.error_message or 
                    (must_expr.description if hasattr(must_expr, 'description') and must_expr.description else None) or
                    f"Must constraint failed for {field_name}"
                )
                # Process dynamic error message with XPath expressions
                processed_error_msg = self._process_dynamic_error_message(
                    base_error_msg, evaluator, context
                )
                error_msg = f"{processed_error_msg} (path: {context_path})"
                logger.warning("Must constraint failed for %s: %s", field_name, error_msg)
                self.errors.append(error_msg)
        except Exception as e:
            # Log evaluation failures for debugging
            logger.warning(
                "Must constraint evaluation failed for %s: %s (expression: %s, context_path=%s)",
                field_name, e, must_expr.expression, getattr(evaluator, 'context_path', [])
            )
            # Add error if field is mandatory, syntax/parse error, or deref() failure (require-instance violation)
            is_deref_error = "deref() failed" in str(e) or "require-instance" in str(e).lower()
            if is_mandatory or "syntax" in str(e).lower() or "parse" in str(e).lower() or is_deref_error:
                # For deref errors, include the exception details in the error message
                # This ensures the specific deref() failure is visible to the user
                if is_deref_error:
                    # Include both the error_message (if available) and the deref() error details
                    base_msg = (
                        must_expr.error_message or 
                        (must_expr.description if hasattr(must_expr, 'description') and must_expr.description else None) or
                        f"Must constraint evaluation failed for {field_name}"
                    )
                    # Process dynamic error message with XPath expressions
                    processed_msg = self._process_dynamic_error_message(
                        base_msg, evaluator, context
                    )
                    error_msg = f"{processed_msg}: {e}"
                else:
                    # Use error_message if available, otherwise fall back to description, then generic message
                    base_msg = (
                        must_expr.error_message or 
                        (must_expr.description if hasattr(must_expr, 'description') and must_expr.description else None) or
                        f"Must constraint evaluation failed for {field_name}"
                    )
                    # Process dynamic error message with XPath expressions
                    processed_msg = self._process_dynamic_error_message(
                        base_msg, evaluator, context
                    )
                    error_msg = f"{processed_msg}: {e}"
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
        
        # Create evaluator context
        context = self._create_evaluator_context(current_path, root_data)
        
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
            # Use passed statement's must_statements if resolved node has none (Phase 1: ensure
            # top-level leaves like allow_unlimited_fields are validated when resolution loses musts)
            musts_to_eval = getattr(actual_schema_node, 'must_statements', None) or []
            if not musts_to_eval and hasattr(stmt, 'must_statements') and stmt.must_statements:
                musts_to_eval = stmt.must_statements
                logger.debug(
                    "Using passed statement must_statements for leaf %s (resolved node had none)",
                    actual_schema_node.name
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
                len(musts_to_eval) > 0, current_path,
                self._get_schema_path_for_node(actual_schema_node)
            )

            # Skip validation if the field doesn't exist (optional fields)
            if not field_exists:
                if not (actual_schema_node.mandatory or (hasattr(actual_schema_node, 'default') and actual_schema_node.default is not None)):
                    logger.debug("Skipping validation for optional missing field: %s", actual_schema_node.name)
                    return  # Skip validation for missing optional fields

            # Evaluate must constraints (from resolved node or passed statement fallback)
            logger.debug("Evaluating %d must constraints for leaf %s", len(musts_to_eval), actual_schema_node.name)
            for must in musts_to_eval:
                # Create context for this evaluation
                leaf_context = self._create_evaluator_context(current_path, root_data)
                self._evaluate_must_constraint(evaluator, must, actual_schema_node.name, actual_schema_node.mandatory, leaf_context, actual_schema_node)
        
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
                # Create evaluator context for this specific value
                # current() should be bound to this value
                value_path = current_path + [value_idx]
                value_context = self._create_evaluator_context(value_path, root_data)
                
                # Evaluate each must constraint for this value
                for must in stmt.must_statements:
                    logger.debug("Evaluating must constraint for leaf-list %s value[%d]=%s", 
                               stmt.name, value_idx, value)
                    self._evaluate_must_constraint(evaluator, must, f"{stmt.name}[{value_idx}]", False, value_context, stmt)
                
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
                # YangListStmt stores must statements in must_statements attribute (created dynamically by parser)
                # Fallback to checking statements list if must_statements doesn't exist
                from ..ast import YangMustStmt
                if hasattr(stmt, 'must_statements'):
                    must_statements = stmt.must_statements
                else:
                    must_statements = [s for s in stmt.statements if isinstance(s, YangMustStmt)] if hasattr(stmt, 'statements') else []
                list_data = container_data if isinstance(container_data, list) else None
                if list_data:
                    # Evaluate must constraints for each list item
                    for idx, item in enumerate(list_data):
                        item_path = current_path + [idx]
                        item_context = self._create_evaluator_context(item_path, root_data)
                        for must in must_statements:
                            self._evaluate_must_constraint(evaluator, must, f"{stmt.name}[{idx}]", False, item_context, stmt)
                else:
                    # List doesn't exist or is not a list - evaluate at list level
                    list_context = self._create_evaluator_context(current_path, root_data)
                    for must in must_statements:
                        self._evaluate_must_constraint(evaluator, must, stmt.name, False, list_context, stmt)
            else:
                # Container: evaluate must constraints at container level
                if hasattr(stmt, 'must_statements'):
                    container_context = self._create_evaluator_context(current_path, root_data)
                    for must in stmt.must_statements:
                        self._evaluate_must_constraint(evaluator, must, stmt.name, False, container_context, stmt)
        
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
                        # Context is created per-statement in _validate_must_in_statement
                        # Validate child statements for this list item
                        # Use a helper to validate children without double recursion
                        # Traverse uses statements by following grouping references
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
                # Traverse uses statements by following grouping references
                child_statements = stmt.statements
                logger.debug("Non-list statement %s, validating %d children", stmt.name if hasattr(stmt, 'name') else type(stmt).__name__, len(child_statements))
                for child in child_statements:
                    # Navigate to child data from root_data
                    child_data = self._navigate_path(root_data, current_path)
                    if child_data is None:
                        child_data = root_data
                    logger.debug("Validating child %s of %s", child.name if hasattr(child, 'name') else type(child).__name__, stmt.name if hasattr(stmt, 'name') else type(stmt).__name__)
                    self._validate_must_in_statement(child_data, child, evaluator, current_path)
    