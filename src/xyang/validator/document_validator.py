"""
YANG document validator.

Design
------
The validator walks the data tree in lockstep with the schema tree,
building Context and Node at the root and using Node.step / Context.child
as it descends.  At each evaluation point it calls evaluator.eval(ctx, node).

At each node the order is (RFC 7950: when before structural):
    1. when   -- usually current node context; ``when`` merged from ``uses`` uses parent of ``uses`` (§7.21.5)
    2. structural -- mandatory, min/max-elements, presence
    3. must   -- evaluated in current node context, per entry for lists
    4. type   -- pattern, range, length, enum, leafref require-instance
    5. descend

RFC 7950 §7.9.4 mandatory ``choice`` / §7.6.5 mandatory ``leaf`` under a ``case``:
    Propagate ``enforce_mandatory_choice`` (bool): strict enforcement when true; when false,
    defer to sibling checks using the innermost ``case`` on ``_case_stack`` (pushed while
    visiting an active ``case``).
"""

from __future__ import annotations

import logging
from typing import AbstractSet, Any, Dict, List, Optional, Tuple

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
from ..module import YangModule
from ..xpath.evaluator import XPathEvaluator
from ..xpath.node import Context, Node
from ..xpath.schema_nav import SchemaNav
from ..xpath.utils import yang_bool

from .if_feature_eval import build_enabled_features_map, stmt_if_features_satisfied
from .path_builder import PathBuilder
from .type_checker import TypeChecker
from .validation_error import ValidationError, Severity

# (Context, Node) for the current parent in the data/schema walk
ParentCtx = Tuple[Context, Node]

logger = logging.getLogger("xyang.validator")


class DocumentValidator:
    """
    Validates a data document against a YANG schema.

    Builds the root Context and Node, then descends using Node.step
    and Context.child(). XPath evaluation uses evaluator.eval(ctx, node).

    Usage:
        validator = DocumentValidator(root_schema)
        errors = validator.validate(data)
    """

    def __init__(
        self,
        root_schema: YangStatementList,
        *,
        enabled_features_by_module: Optional[Dict[str, AbstractSet[str]]] = None,
    ) -> None:
        self._root_schema = root_schema
        self._type_checker = TypeChecker()
        self._evaluator = XPathEvaluator()
        if isinstance(root_schema, YangModule):
            self._if_feature_module: Optional[YangModule] = root_schema
            self._enabled_features = build_enabled_features_map(
                root_schema, enabled_features_by_module
            )
        else:
            self._if_feature_module = None
            self._enabled_features = {}

    def validate(
        self,
        data: Any,
        *,
        leafref_severity: Severity = Severity.ERROR,
        cache: bool = True,
    ) -> List[ValidationError]:
        """Validate data against the root schema.

        Walks the data tree in lockstep with the schema, evaluating when,
        must, type constraints, and leafref. Collects errors and returns
        them; does not raise.

        Args:
            data: Root data to validate (typically a dict or list).
            leafref_severity: Severity for leafref violations (ERROR or WARNING).
            cache: If True, cache XPath path results for reuse; if False, disable.

        Returns:
            List of ValidationError (empty when valid).
        """
        self._leafref_severity = leafref_severity
        self._root_data = data
        self._errors = []
        self._case_stack: list[YangCaseStmt] = []
        self._case_level_data_stack: list[dict[str, Any]] = []
        self._evaluator.clear_cache_stats()
        path_cache: Dict[Any, Any] | None = {} if cache else None
        node = Node(data, self._root_schema, None)
        ctx = Context(current=node, root=node, path_cache=path_cache)
        path = PathBuilder()
        self._visit_children(
            data, self._root_schema, (ctx, node), path, enforce_mandatory_choice=True
        )
        return self._errors

    def _if_features_active(self, stmt: YangStatement) -> bool:
        if self._if_feature_module is None:
            return True
        feats = getattr(stmt, "if_features", None) or []
        return stmt_if_features_satisfied(
            feats, self._if_feature_module, self._enabled_features
        )

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

    def _child_enforce_mandatory_choice(
        self, owner: YangStatementList, parent_enforce: bool
    ) -> bool:
        """RFC 7950 §7.9.4: whether mandatory ``choice`` is enforced without case-sibling deferral.

        When ``False``, the innermost ``case`` on ``_case_stack`` (with data from
        ``_case_level_data_stack``) supplies §7.9.4 sibling checks at the case's JSON level.
        Non-presence containers inherit the parent flag; presence containers and lists reset to
        strict enforcement.
        """
        if isinstance(owner, YangModule):
            return True
        if isinstance(owner, YangCaseStmt):
            return False
        if isinstance(owner, YangContainerStmt):
            if owner.presence is None:
                return parent_enforce
            return True
        if isinstance(owner, YangListStmt):
            return True
        return parent_enforce

    def _statement_has_matching_data(
        self, stmt: YangStatement, data: dict[str, Any]
    ) -> bool:
        """True if this statement (or a nested choice branch) has a key in ``data``."""
        if isinstance(stmt, YangLeafStmt):
            return stmt.name in data
        if isinstance(stmt, YangLeafListStmt):
            return stmt.name in data
        if isinstance(stmt, YangContainerStmt):
            return stmt.name in data
        if isinstance(stmt, YangListStmt):
            return stmt.name in data
        if isinstance(stmt, YangChoiceStmt):
            for case in stmt.cases:
                for ch in case.statements:
                    if self._statement_has_matching_data(ch, data):
                        return True
            return False
        return False

    def _case_has_other_stmt_data(
        self,
        case: YangCaseStmt,
        data: dict[str, Any],
        skip: YangChoiceStmt,
    ) -> bool:
        """§7.9.4: any sibling under the same case has data (excluding ``skip`` choice)."""
        for s in case.statements:
            if s is skip:
                continue
            if self._statement_has_matching_data(s, data):
                return True
        return False

    def _case_has_any_stmt_data(
        self, case: YangCaseStmt, data: dict[str, Any]
    ) -> bool:
        """§7.6.5: any node from this case appears in ``data`` at the current level."""
        return any(self._statement_has_matching_data(s, data) for s in case.statements)

    def _case_level_data(self) -> dict[str, Any]:
        """Dict containing all nodes from the innermost active ``case`` (sibling keys)."""
        if self._case_level_data_stack:
            return self._case_level_data_stack[-1]
        return {}

    def _mandatory_choice_violation(
        self,
        choice: YangChoiceStmt,
        data: dict[str, Any],
        enforce_mandatory_choice: bool,
    ) -> bool:
        """True if mandatory ``choice`` with no active case should be reported (§7.9.4)."""
        if not choice.mandatory:
            return False
        if enforce_mandatory_choice:
            return True
        if not self._case_stack:
            return True
        return self._case_has_other_stmt_data(
            self._case_stack[-1], self._case_level_data(), skip=choice
        )

    def _leaf_mandatory_must_exist(
        self,
        leaf: YangLeafStmt,
        data: dict[str, Any],
        enforce_mandatory_choice: bool,
    ) -> bool:
        """RFC 7950 §7.6.5: when a mandatory leaf's absence is invalid."""
        if not leaf.mandatory:
            return False
        if enforce_mandatory_choice:
            return True
        if not self._case_stack:
            return True
        return self._case_has_any_stmt_data(
            self._case_stack[-1], self._case_level_data()
        )

    # ------------------------------------------------------------------
    # Tree walk
    # ------------------------------------------------------------------

    def _visit_children(
        self,
        data: Any,
        schema: YangStatementList,
        parent_ctx: ParentCtx,
        path: PathBuilder,
        enforce_mandatory_choice: bool,
    ) -> None:
        if not isinstance(data, dict):
            return
        child_enforce = self._child_enforce_mandatory_choice(
            schema, enforce_mandatory_choice
        )
        visited_names: set[str] = set()
        for stmt in schema.statements:
            if isinstance(stmt, YangChoiceStmt):
                visited_names.update(self._choice_instance_keys(stmt, data))
            else:
                visited_names.update(stmt.child_names(data))
            self._visit_stmt(stmt, data, parent_ctx, path, child_enforce)
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
        parent_ctx: ParentCtx,
        path: PathBuilder,
        enforce_mandatory_choice: bool,
    ) -> None:
        logger.debug("_visit_stmt path=%s stmt=%s", path.current(), type(stmt).__name__)

        if isinstance(stmt, YangChoiceStmt):
            self._visit_choice(stmt, data, parent_ctx, path, enforce_mandatory_choice)
            return
        if isinstance(stmt, YangCaseStmt):
            self._case_stack.append(stmt)
            self._case_level_data_stack.append(data)
            try:
                ce = self._child_enforce_mandatory_choice(
                    stmt, enforce_mandatory_choice
                )
                self._visit_children(data, stmt, parent_ctx, path, ce)
            finally:
                self._case_level_data_stack.pop()
                self._case_stack.pop()
            return

        name = stmt.name
        present = name in data
        child_path = path.child(name)
        parent_ctx_obj, parent_node = parent_ctx

        # -- 0. if-feature (before when; inactive nodes are not in the effective schema) --
        if not self._if_features_active(stmt):
            if present:
                self._errors.append(
                    ValidationError(
                        path=child_path,
                        message=(
                            f"Node '{name}' is present but its 'if-feature' "
                            "condition is false — this node must not exist"
                        ),
                    )
                )
            return

        # Need val and (curr_node, curr_ctx) for when, must, and type checks
        val = self._effective_value(data, name, stmt)
        curr_node = parent_node.step(val, stmt)
        curr_ctx = parent_ctx_obj.child(curr_node)

        # -- 1. when (RFC 7950: applicability first; report when-false before structural) --
        logger.debug("phase 1 when path=%s", child_path)
        if isinstance(stmt, YangStatementWithWhen) and stmt.when is not None:
            if getattr(stmt.when, "evaluate_with_parent_context", False):
                when_ctx, when_node = parent_ctx_obj, parent_node
            else:
                when_ctx, when_node = curr_ctx, curr_node
            when_ok = self._eval_expr(stmt.when.ast, when_ctx, when_node)
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

        # -- 2. Structural (mandatory, min/max-elements, presence) —
        logger.debug("phase 2 structural path=%s", child_path)
        if not self._check_structural(
            stmt, name, data, child_path, enforce_mandatory_choice
        ):
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
                    item_node = parent_node.step(item, stmt)
                    item_ctx = parent_ctx_obj.child(item_node)
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
                ctx=curr_ctx,
                evaluator=self._evaluator,
                leafref_current=curr_node,
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
                item_node = parent_node.step(item, stmt)
                item_ctx = parent_ctx_obj.child(item_node)
                item_path = f"{child_path}[{i}]"
                for msg in self._type_checker.check(
                    item,
                    stmt.type,
                    item_path,
                    self._root_data,
                    self._root_schema,
                    ctx=item_ctx,
                    evaluator=self._evaluator,
                    leafref_current=parent_node,
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
            child_enforce = self._child_enforce_mandatory_choice(
                stmt, enforce_mandatory_choice
            )
            self._visit_children(
                val, stmt, (curr_ctx, curr_node), path, child_enforce
            )
            path.pop()
        elif isinstance(stmt, YangListStmt) and isinstance(val, list):
            key_names = [k.strip() for k in stmt.key.split()] if stmt.key else []
            if self._check_list_key_uniqueness(
                val, key_names, name, child_path
            ):
                return  # duplicate key; skip per-entry validation
            for entry in val:
                path.push(name, self._entry_key_from_names(entry, key_names))
                entry_node = Node(entry, stmt, parent_node)
                entry_ctx = curr_ctx.child(entry_node)
                self._check_must(
                    stmt, entry_ctx, entry_node, path.current()
                )
                entry_enforce = self._child_enforce_mandatory_choice(
                    stmt, enforce_mandatory_choice
                )
                self._visit_children(
                    entry, stmt, (entry_ctx, entry_node), path, entry_enforce
                )
                path.pop()

    def _choice_has_branch_data(
        self, choice: YangChoiceStmt, data: Dict[str, Any]
    ) -> bool:
        """True if any schema child under any case has matching data in ``data``."""
        return any(self._case_has_any_stmt_data(c, data) for c in choice.cases)

    def _stmt_instance_keys_from_data(
        self, stmt: YangStatement, data: dict[str, Any]
    ) -> set[str]:
        """Instance keys under ``data`` claimed by this statement (same nesting level)."""
        if isinstance(stmt, YangLeafStmt):
            return {stmt.name} if stmt.name in data else set()
        if isinstance(stmt, YangLeafListStmt):
            return {stmt.name} if stmt.name in data else set()
        if isinstance(stmt, YangContainerStmt):
            return {stmt.name} if stmt.name in data else set()
        if isinstance(stmt, YangListStmt):
            return {stmt.name} if stmt.name in data else set()
        if isinstance(stmt, YangChoiceStmt):
            return self._choice_instance_keys(stmt, data)
        return set()

    def _choice_instance_keys(
        self, choice: YangChoiceStmt, data: dict[str, Any]
    ) -> set[str]:
        """Keys in ``data`` consumed by this choice (nested choices: leaves stay at this level)."""
        if not self._if_features_active(choice):
            return set()
        active_cases = [
            c
            for c in choice.cases
            if self._if_features_active(c) and self._case_has_any_stmt_data(c, data)
        ]
        if not active_cases:
            return set()
        keys: set[str] = set()
        if len(active_cases) > 1:
            for case in active_cases:
                for s in case.statements:
                    keys.update(self._stmt_instance_keys_from_data(s, data))
            return keys
        for s in active_cases[0].statements:
            keys.update(self._stmt_instance_keys_from_data(s, data))
        return keys

    def _visit_choice(
        self,
        choice: YangChoiceStmt,
        data: Dict[str, Any],
        parent_ctx: ParentCtx,
        path: PathBuilder,
        enforce_mandatory_choice: bool,
    ) -> None:
        parent_ctx_obj, parent_node = parent_ctx

        if not self._if_features_active(choice):
            if self._choice_has_branch_data(choice, data):
                self._errors.append(
                    ValidationError(
                        path=path.current(),
                        message=(
                            f"Choice '{choice.name}' has data but its 'if-feature' "
                            "condition is false — this branch must not exist"
                        ),
                    )
                )
            return

        if choice.when is not None:
            when_ok = self._eval_expr(choice.when.ast, parent_ctx_obj, parent_node)
            if when_ok is None:
                when_ok = True
            if not when_ok:
                if self._choice_has_branch_data(choice, data):
                    self._errors.append(
                        ValidationError(
                            path=path.current(),
                            message=(
                                f"Choice '{choice.name}' has data but its 'when' "
                                "evaluates to false — this branch must not exist"
                            ),
                            expression=choice.when.condition,
                        )
                    )
                return

        active_cases: list[YangCaseStmt] = []
        for case in choice.cases:
            if not self._if_features_active(case):
                if self._case_has_any_stmt_data(case, data):
                    self._errors.append(
                        ValidationError(
                            path=path.current(),
                            message=(
                                f"Case '{case.name}' of choice '{choice.name}' has "
                                "data but its 'if-feature' condition is false — "
                                "this branch must not exist"
                            ),
                        )
                    )
                    return
                continue
            if not self._case_has_any_stmt_data(case, data):
                continue
            if case.when is not None:
                c_ok = self._eval_expr(case.when.ast, parent_ctx_obj, parent_node)
                if c_ok is None:
                    c_ok = True
                if not c_ok:
                    self._errors.append(
                        ValidationError(
                            path=path.current(),
                            message=(
                                f"Case '{case.name}' of choice '{choice.name}' has "
                                "data but its 'when' evaluates to false — this branch "
                                "must not exist"
                            ),
                            expression=case.when.condition,
                        )
                    )
                    return
            active_cases.append(case)

        if len(active_cases) > 1:
            names = ", ".join(c.name for c in active_cases)
            self._errors.append(
                ValidationError(
                    path=path.current(),
                    message=(
                        f"Choice '{choice.name}' allows only one case; "
                        f"data matches multiple cases: {names}"
                    ),
                )
            )
            return

        active_case = active_cases[0] if active_cases else None

        if active_case is None:
            if self._mandatory_choice_violation(
                choice, data, enforce_mandatory_choice
            ):
                self._errors.append(
                    ValidationError(
                        path=path.current(),
                        message=f"Mandatory choice '{choice.name}' has no active case",
                    )
                )
            return

        # Validate only statements in the active case.
        # Do not call _visit_children here: its unknown-field check is scoped to the
        # provided schema node and would incorrectly flag sibling fields (outside this
        # choice) as unknown when validating list/container entries.
        self._case_stack.append(active_case)
        self._case_level_data_stack.append(data)
        try:
            inner_enforce = self._child_enforce_mandatory_choice(
                active_case, enforce_mandatory_choice
            )
            for stmt in active_case.statements:
                self._visit_stmt(stmt, data, parent_ctx, path, inner_enforce)
        finally:
            self._case_level_data_stack.pop()
            self._case_stack.pop()

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
        enforce_mandatory_choice: bool,
    ) -> bool:
        present = name in data
        effective = self._effective_value(data, name, stmt)

        if isinstance(stmt, YangLeafStmt):
            # YANG type empty: leaf has no value, only presence; treat as present when key is in data
            type_name = getattr(getattr(stmt, "type", None), "name", None)
            if type_name == "empty" and present:
                return True
            if effective is None and stmt.mandatory:
                if self._leaf_mandatory_must_exist(
                    stmt, data, enforce_mandatory_choice
                ):
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
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("must result path=%s result=%s", path, result)
            if result is None:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("must ERROR (eval failed) path=%s", path)
                self._errors.append(
                    ValidationError(
                        path=path,
                        message=f"Error evaluating must expression on '{stmt.name}'",
                        expression=must.expression,
                    )
                )
            elif not result:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("must FAIL (constraint not satisfied) path=%s", path)
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
