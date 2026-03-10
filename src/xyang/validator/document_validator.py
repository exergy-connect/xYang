"""
YANG document validator.

Design
------
The validator walks the data tree in lockstep with the schema tree,
maintaining a Node stack as it descends.  At each evaluation point it
calls xpath_validator.make_context() and passes the result directly to
evaluator.eval().  The validator never constructs Node objects —
that is the evaluator's domain.

At each node the order is:
    1. when   -- evaluated in parent context; false on present node = error
    2. structural -- mandatory, cardinality
    3. must   -- evaluated in current node context, per entry for lists
    4. type   -- pattern, range, length, enum, leafref require-instance
    5. descend
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..ast import (
    YangCaseStmt,
    YangChoiceStmt,
    YangContainerStmt,
    YangLeafListStmt,
    YangLeafStmt,
    YangListStmt,
    YangStatement,
    YangStatementList,
    YangStatementWithMust,
    YangStatementWithWhen,
)
from ..xpath.evaluator import XPathEvaluator
from ..xpath.node import Context, Node
from ..xpath.schema_nav import SchemaNav
from ..xpath.utils import yang_bool
from ..xpath.validator import Validator as XPathValidator

from .path_builder import PathBuilder
from .type_checker import TypeChecker
from .validation_error import ValidationError, Severity

logger = logging.getLogger("xyang.validator")


class DocumentValidator:
    """
    Validates a data document against a YANG schema.

    Maintains a Node stack via the XPathValidator as it descends.
    All XPath evaluation goes through xpath_validator.make_context()
    followed by evaluator.eval() — the validator never constructs
    Node objects directly.

    Usage:
        validator = DocumentValidator(root_schema)
        errors = validator.validate(data)
    """

    def __init__(self, root_schema: YangStatementList) -> None:
        self._root_schema = root_schema
        self._type_checker = TypeChecker()
        self._evaluator = XPathEvaluator()

    def validate(
        self,
        data: Any,
        *,
        leafref_severity: Severity = Severity.ERROR,
    ) -> List[ValidationError]:
        self._leafref_severity = leafref_severity
        self._xpath_v = XPathValidator(data, self._root_schema)
        self._root_data = data
        self._errors = []
        ctx, node = self._xpath_v.make_context(
            data, self._root_schema, parent=None
        )
        path = PathBuilder()
        self._visit_children(data, self._root_schema, (ctx, node), path)
        return self._errors

    def _effective_value(
        self, data: Dict[str, Any], name: str, stmt: YangStatement
    ) -> Any:
        """
        Return the effective value for a node:
        - data[name] if present
        - SchemaNav.default(stmt) if absent and a default exists
        - None if truly absent

        Does not modify data.
        """
        if name in data:
            return data[name]
        return SchemaNav.default(stmt)

    # ------------------------------------------------------------------
    # Tree walk
    # ------------------------------------------------------------------

    def _visit_children(
        self,
        data: Any,
        schema: YangStatementList,
        parent_ctx: tuple,
        path: PathBuilder,
    ) -> None:
        if not isinstance(data, dict):
            return
        visited_names: set[str] = set()
        for stmt in schema.statements:
            visited_names.update(stmt.child_names(data))
            self._visit_stmt(stmt, data, parent_ctx, path)
        for key in data:
            if key not in visited_names:
                self._errors.append(
                    ValidationError(
                        path=path.child(key),
                        message=f"Unknown field '{key}'",
                    )
                )

    def _visit_stmt(
        self,
        stmt: YangStatement,
        data: Dict[str, Any],
        parent_ctx: tuple,
        path: PathBuilder,
    ) -> None:
        logger.debug("_visit_stmt path=%s stmt=%s", path.current(), type(stmt).__name__)

        if isinstance(stmt, YangChoiceStmt):
            self._visit_choice(stmt, data, parent_ctx, path)
            return
        if isinstance(stmt, YangCaseStmt):
            self._visit_children(data, stmt, parent_ctx, path)
            return

        name = stmt.name
        present = name in data
        child_path = path.child(name)
        parent_ctx_obj, parent_node = parent_ctx

        # -- 2. Structural checks (need before when so we have val for context) --
        logger.debug("phase 2 structural path=%s", child_path)
        if not self._check_structural(stmt, name, data, child_path):
            return

        val = self._effective_value(data, name, stmt)
        curr_ctx, curr_node = self._xpath_v.make_context(
            val, stmt, parent=parent_node
        )

        # -- 1. when (context node is the node the when is attached to, so child) --
        logger.debug("phase 1 when path=%s", child_path)
        if isinstance(stmt, YangStatementWithWhen) and stmt.when is not None:
            when_ok = self._eval_expr(stmt.when.ast, curr_ctx, curr_node)
            if when_ok is None:
                when_ok = True
            if not when_ok and present:
                self._errors.append(
                    ValidationError(
                        path=child_path,
                        message=(
                            f"Node '{name}' is present but its 'when' condition "
                            "evaluates to false — this node must not exist"
                        ),
                        expression=stmt.when.condition,
                    )
                )
                return
            if not when_ok:
                return

        # -- 3. must (evaluated in current node context) --
        logger.debug("phase 3 must path=%s", child_path)
        if isinstance(stmt, YangStatementWithMust) and not isinstance(
            stmt, YangListStmt
        ):
            if isinstance(stmt, YangLeafListStmt):
                # Leaf-list: evaluate must per element; skip when empty
                items = (
                    val
                    if isinstance(val, list)
                    else ([val] if val is not None else [])
                )
                for i, item in enumerate(items):
                    item_ctx, item_node = self._xpath_v.make_context(
                        item, stmt, parent=parent_node
                    )
                    item_path = f"{child_path}[{i}]"
                    self._check_must(stmt, item_ctx, item_node, item_path)
            else:
                self._check_must(stmt, curr_ctx, curr_node, child_path)

        # -- 4. Type check --
        type_stmt = getattr(stmt, "type", None)
        type_name = getattr(type_stmt, "name", None) if type_stmt else None
        logger.debug("phase 4 type path=%s type=%s", child_path, type_name)
        if (
            isinstance(stmt, YangLeafStmt)
            and stmt.type is not None
            and val is not None
        ):
            if type_name == "leafref":
                logger.debug("phase 4 type: leafref require-instance check path=%s", child_path)
            for msg in self._type_checker.check(
                val,
                stmt.type,
                child_path,
                self._root_data,
                self._root_schema,
                context_node=parent_node,
                evaluator=self._evaluator,
                root_node=self._xpath_v._root,
            ):
                severity = (
                    self._leafref_severity if type_name == "leafref" else Severity.ERROR
                )
                self._errors.append(
                    ValidationError(
                        path=child_path,
                        message=msg,
                        severity=severity,
                    )
                )
        elif isinstance(stmt, YangLeafListStmt) and stmt.type is not None:
            items = (
                val if isinstance(val, list) else ([val] if val is not None else [])
            )
            leaf_list_leafref = getattr(stmt.type, "name", None) == "leafref"
            for i, item in enumerate(items):
                item_path = f"{child_path}[{i}]"
                for msg in self._type_checker.check(
                    item,
                    stmt.type,
                    item_path,
                    self._root_data,
                    self._root_schema,
                    context_node=parent_node,
                    evaluator=self._evaluator,
                    root_node=self._xpath_v._root,
                ):
                    severity = (
                        self._leafref_severity
                        if leaf_list_leafref
                        else Severity.ERROR
                    )
                    self._errors.append(
                        ValidationError(
                            path=item_path,
                            message=msg,
                            severity=severity,
                        )
                    )

        # -- 5. Descend --
        logger.debug("phase 5 descend path=%s", child_path)
        if isinstance(stmt, YangContainerStmt) and isinstance(val, dict):
            path.push(name)
            self._visit_children(val, stmt, (curr_ctx, curr_node), path)
            path.pop()
        elif isinstance(stmt, YangListStmt) and isinstance(val, list):
            key_names = [k.strip() for k in stmt.key.split()] if stmt.key else []
            if self._check_list_key_uniqueness(
                val, key_names, name, child_path
            ):
                return  # duplicate key; skip per-entry validation
            list_node = Node(val, stmt, parent_node)
            for entry in val:
                path.push(name, self._entry_key_from_names(entry, key_names))
                entry_ctx, entry_node = self._xpath_v.make_context(
                    entry, stmt, parent=list_node
                )
                self._check_must(
                    stmt, entry_ctx, entry_node, path.current()
                )
                self._visit_children(
                    entry, stmt, (entry_ctx, entry_node), path
                )
                path.pop()

    def _visit_choice(
        self,
        choice: YangChoiceStmt,
        data: Dict[str, Any],
        parent_ctx: tuple,
        path: PathBuilder,
    ) -> None:
        active_case = None
        for case in choice.cases:
            if any(
                getattr(s, "name", None) in data for s in case.statements
            ):
                active_case = case
                break

        if active_case is None:
            if choice.mandatory:
                self._errors.append(
                    ValidationError(
                        path=path.current(),
                        message=f"Mandatory choice '{choice.name}' has no active case",
                    )
                )
            return

        self._visit_children(data, active_case, parent_ctx, path)

    # ------------------------------------------------------------------
    # Structural checks
    # Returns False if the node is absent and nothing further should be done.
    # ------------------------------------------------------------------

    def _check_structural(
        self,
        stmt: YangStatement,
        name: str,
        data: Dict[str, Any],
        path: str,
    ) -> bool:
        present = name in data
        effective = self._effective_value(data, name, stmt)

        if isinstance(stmt, YangLeafStmt):
            if effective is None and stmt.mandatory:
                self._errors.append(
                    ValidationError(
                        path=path,
                        message=f"Mandatory leaf '{name}' is missing",
                    )
                )
            return effective is not None

        if isinstance(stmt, YangContainerStmt):
            return present

        if isinstance(stmt, (YangListStmt, YangLeafListStmt)):
            count = (
                len(effective)
                if isinstance(effective, list)
                else (1 if effective is not None else 0)
            )
            min_e = getattr(stmt, "min_elements", None)
            max_e = getattr(stmt, "max_elements", None)
            # Only enforce min/max when list is present (YANG: optional list may be omitted)
            if min_e is not None and present and count < min_e:
                self._errors.append(
                    ValidationError(
                        path=path,
                        message=(
                            f"'{name}' has {count} element(s) but "
                            f"requires at least {min_e}"
                        ),
                    )
                )
            if max_e is not None and present and count > max_e:
                self._errors.append(
                    ValidationError(
                        path=path,
                        message=(
                            f"'{name}' has {count} element(s) but "
                            f"allows at most {max_e}"
                        ),
                    )
                )
            return present

        return present

    # ------------------------------------------------------------------
    # XPath evaluation
    # ------------------------------------------------------------------

    def _eval_expr(
        self, ast: Any, ctx: Context, node: Node
    ) -> Optional[bool]:
        """Evaluate an XPath AST. Returns None on error."""
        if ast is None:
            return None
        try:
            return yang_bool(self._evaluator.eval(ast, ctx, node))
        except Exception:
            return None

    def _check_must(
        self,
        stmt: YangStatementWithMust,
        ctx: Context,
        node: Node,
        path: str,
    ) -> None:
        for must in stmt.must_statements:
            result = self._eval_expr(must.ast, ctx, node)
            if result is None:
                self._errors.append(
                    ValidationError(
                        path=path,
                        message=f"Error evaluating must expression on '{stmt.name}'",
                        expression=must.expression,
                    )
                )
            elif not result:
                self._errors.append(
                    ValidationError(
                        path=path,
                        message=must.error_message
                        or (f"must constraint not satisfied on '{stmt.name}'"),
                        expression=must.expression,
                    )
                )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _check_list_key_uniqueness(
        self,
        val: list,
        key_names: List[str],
        list_name: str,
        path_str: str,
    ) -> bool:
        """Report duplicate key in list. Returns True if duplicate found."""
        if not key_names:
            return False
        seen_keys: Dict[tuple, int] = {}
        for i, entry in enumerate(val):
            if not isinstance(entry, dict):
                continue
            key_tuple = tuple(entry.get(k) for k in key_names)
            if key_tuple in seen_keys:
                first_idx = seen_keys[key_tuple]
                key_display = ", ".join(
                    f"{k}='{entry.get(k)}'" for k in key_names
                )
                self._errors.append(
                    ValidationError(
                        path=path_str,
                        message=(
                            f"Duplicate key in list '{list_name}': {key_display} "
                            f"(entries at index {first_idx} and {i})"
                        ),
                        expression="",
                    )
                )
                return True
            seen_keys[key_tuple] = i
        return False

    def _entry_key_from_names(
        self, entry: Any, key_names: List[str]
    ) -> Optional[str]:
        """Path key string for a list entry from key leaf names."""
        if not isinstance(entry, dict) or not key_names:
            return None
        parts = [f"{k}='{entry.get(k)}'" for k in key_names]
        return ", ".join(parts) if parts else None

    def _entry_key(self, entry: Any, list_stmt: YangListStmt) -> Optional[str]:
        if not isinstance(entry, dict) or not list_stmt.key:
            return None
        key_names = [k.strip() for k in list_stmt.key.split()]
        return self._entry_key_from_names(entry, key_names)
