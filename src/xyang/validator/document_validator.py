"""
YANG document validator.

Design
------
The validator walks the data tree in lockstep with the schema tree,
building Context and Node at the root and using Node.step / Context.child
as it descends.  At each evaluation point it calls evaluator.eval(ctx, node).

At each node the order is (RFC 7950: when before structural):
    1. when   -- usually current node context; ``when`` merged from ``uses`` uses parent of ``uses`` (§7.21.5)
    1b. JSON shape -- a present container is an object; a present list or leaf-list is an array (RFC 7951 §5)
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

import json
import logging
from typing import AbstractSet, Any, Dict, List, Optional, Tuple

from ..ast import (
    YangAnydataStmt,
    YangAnyxmlStmt,
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
from ..encoding.rfc7951 import (
    member_keys_cached,
    instance_member_lookup,
    instance_member_present,
)
from ..module import YangModule
from ..xpath.evaluator import XPathEvaluator
from ..xpath.node import Context, Node
from ..xpath.schema_nav import SchemaNav
from ..xpath.utils import yang_bool

from .if_feature_eval import build_enabled_features_map, stmt_if_features_satisfied
from .path_builder import PathBuilder
from .validator_extension import ValidatorExtension
from .type_checker import TypeChecker
from .validation_error import ValidationError, Severity

# (Context, Node) for the current parent in the data/schema walk
ParentCtx = Tuple[Context, Node]

logger = logging.getLogger("xyang.validator")

_MISSING = object()


def _descendant_value(entry: Any, path: str) -> Any:
    """Value at a ``unique`` descendant path (``a/b``) in a list entry, or ``_MISSING``."""
    cur = entry
    for seg in path.split("/"):
        if not isinstance(cur, dict) or seg not in cur:
            return _MISSING
        cur = cur[seg]
    return cur


def _unique_display(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


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
        constraint_checks: bool = True,
    ) -> None:
        self._root_schema = root_schema
        self._constraint_checks = constraint_checks
        self._enabled_features_by_module = enabled_features_by_module
        self._type_checker = TypeChecker()
        self._evaluator = XPathEvaluator()
        if isinstance(root_schema, YangModule):
            self._if_feature_module: Optional[YangModule] = root_schema
            self._enabled_features = build_enabled_features_map(root_schema, enabled_features_by_module)
        else:
            self._if_feature_module = None
            self._enabled_features = {}
        self._anydata_validation: Optional[Dict[str, Any]] = None
        self._leafref_severity = Severity.ERROR
        self._root_data: Any = None
        self._errors: List[ValidationError] = []
        self._case_stack: list[YangCaseStmt] = []
        self._case_level_data_stack: list[dict[str, Any]] = []

    def validate(
        self,
        data: Any,
        *,
        leafref_severity: Severity = Severity.ERROR,
        cache: bool = True,
        leafref_root_data: Optional[Any] = None,
        path: Optional[PathBuilder] = None,
        native_json: bool = False,
        module: Optional[YangModule] = None,
        from_iterator: bool = False,
    ) -> List[ValidationError]:
        """Validate data against the root schema.

        Walks the data tree in lockstep with the schema, evaluating when,
        must, type constraints, and leafref. Collects errors and returns
        them; does not raise.

        Args:
            data: Root data to validate (typically a dict or list).
            leafref_severity: Severity for leafref violations (ERROR or WARNING).
            cache: If True, cache XPath path results for reuse; if False, disable.
            leafref_root_data: If set, used as XPath / leafref root data instead of
                ``data`` (for validating a fragment in full-document context).
            path: Optional path prefix (e.g. subtree validation under ``anydata``).

        Returns:
            List of ValidationError (empty when valid).
        """
        encoding: list[ValidationError] = []
        pointer_map: dict[str, str] = {}
        host = module if module is not None else self._if_feature_module
        if from_iterator and host is not None and isinstance(data, dict):
            from ..encoding.instance import encoding_errors, iter_instance, project_instance

            nodes = list(iter_instance(data, host, native_json=native_json, schema=self._root_schema))
            parent = host.name if isinstance(self._root_schema, YangModule) else ""
            data, pointer_map = project_instance(nodes, parent)
            encoding = [
                ValidationError(path=ptr or "/", message=message, code=code, pointer=ptr)
                for ptr, code, message in encoding_errors(nodes)
            ]
        self._leafref_severity = leafref_severity
        self._root_data = leafref_root_data if leafref_root_data is not None else data
        self._errors = []
        self._case_stack = []
        self._case_level_data_stack = []
        self._evaluator.clear_cache_stats()
        path_cache: Dict[Any, Any] | None = {} if cache else None
        node = Node(data, self._root_schema, None)
        ctx = Context(current=node, root=node, path_cache=path_cache)
        path_builder = path if path is not None else PathBuilder()
        self._visit_children(
            data,
            self._root_schema,
            (ctx, node),
            path_builder,
            enforce_mandatory_choice=True,
        )
        if pointer_map:
            from ..encoding.instance import remap_pointer

            for err in self._errors:
                err.pointer = remap_pointer(err.pointer, pointer_map)
        return encoding + self._errors

    def _add(
        self,
        *,
        path: str,
        pointer: str,
        code: str,
        message: str,
        expression: Optional[str] = None,
        severity: Severity = Severity.ERROR,
    ) -> None:
        """Record one issue. ``path`` is the existing display path; ``pointer`` is the JSON Pointer."""
        self._errors.append(
            ValidationError(
                path=path,
                message=message,
                expression=expression,
                severity=severity,
                code=code,
                pointer=pointer,
            )
        )

    def enable_extension(self, extension: ValidatorExtension, /, **kwargs: Any) -> None:
        """Enable an optional validation extension (see ``ValidatorExtension``)."""
        if extension is ValidatorExtension.ANYDATA_VALIDATION:
            from ..ext.anydata_validation import parse_anydata_extension_kwargs

            modules, mode = parse_anydata_extension_kwargs(kwargs)
            self._anydata_validation = {"modules": modules, "mode": mode}
            return
        raise ValueError(f"unknown validator extension: {extension!r}")

    def _if_features_active(self, stmt: YangStatement) -> bool:
        if self._if_feature_module is None:
            return True
        feats = getattr(stmt, "if_features", None) or []
        return stmt_if_features_satisfied(feats, self._if_feature_module, self._enabled_features)

    def _encoding_parent_module(self) -> str:
        """Module name for RFC 7951 member encoding of children under the current subtree."""
        if isinstance(self._root_schema, YangModule):
            return self._root_schema.name
        return ""

    def _effective_value(self, data: Dict[str, Any], stmt: YangStatement) -> Any:
        """
        Return the effective value for a node:
        - instance JSON value if present (local or ``module:`` qualified)
        - SchemaNav.default(stmt) if absent and a default exists
        - None if truly absent

        Does not modify data.
        """
        val, _key = instance_member_lookup(data, stmt, self._encoding_parent_module())
        if _key is not None:
            return val
        return SchemaNav.default(stmt)

    def _child_enforce_mandatory_choice(self, owner: YangStatementList, parent_enforce: bool) -> bool:
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

    def _statement_has_matching_data(self, stmt: YangStatement, data: dict[str, Any]) -> bool:
        """True if this statement (or a nested choice branch) has a key in ``data``."""
        parent_mod = self._encoding_parent_module()
        if isinstance(
            stmt,
            (
                YangLeafStmt,
                YangAnydataStmt,
                YangAnyxmlStmt,
                YangLeafListStmt,
                YangContainerStmt,
                YangListStmt,
            ),
        ):
            return instance_member_present(data, stmt, parent_mod)
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

    def _case_has_any_stmt_data(self, case: YangCaseStmt, data: dict[str, Any]) -> bool:
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
        return self._case_has_other_stmt_data(self._case_stack[-1], self._case_level_data(), skip=choice)

    def _leaf_mandatory_must_exist(
        self,
        leaf: YangLeafStmt | YangAnydataStmt | YangAnyxmlStmt,
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
        return self._case_has_any_stmt_data(self._case_stack[-1], self._case_level_data())

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
        child_enforce = self._child_enforce_mandatory_choice(schema, enforce_mandatory_choice)
        parent_mod = self._encoding_parent_module()
        visited_names: set[str] = set()
        for stmt in schema.statements:
            if isinstance(stmt, YangChoiceStmt):
                visited_names.update(self._choice_instance_keys(stmt, data))
            else:
                visited_names.update(member_keys_cached(stmt, parent_mod))
            self._visit_stmt(stmt, data, parent_ctx, path, child_enforce)
        for key in data:
            if key not in visited_names:
                self._add(
                    path=path.child(key),
                    pointer=path.child_pointer(key),
                    code="unknown-field",
                    message=f"Unknown field '{key}'",
                )

    def _visit_stmt(
        self,
        stmt: YangStatement,
        data: Dict[str, Any],
        parent_ctx: ParentCtx,
        path: PathBuilder,
        enforce_mandatory_choice: bool,
    ) -> None:
        debug = logger.isEnabledFor(logging.DEBUG)
        if debug:
            logger.debug("_visit_stmt path=%s stmt=%s", path.current(), type(stmt).__name__)

        if isinstance(stmt, YangChoiceStmt):
            self._visit_choice(stmt, data, parent_ctx, path, enforce_mandatory_choice)
            return
        if isinstance(stmt, YangCaseStmt):
            self._case_stack.append(stmt)
            self._case_level_data_stack.append(data)
            try:
                ce = self._child_enforce_mandatory_choice(stmt, enforce_mandatory_choice)
                self._visit_children(data, stmt, parent_ctx, path, ce)
            finally:
                self._case_level_data_stack.pop()
                self._case_stack.pop()
            return

        name = stmt.name
        parent_mod = self._encoding_parent_module()
        present = instance_member_present(data, stmt, parent_mod)
        _val, json_key = instance_member_lookup(data, stmt, parent_mod)
        json_name = json_key if json_key is not None else name
        child_path = path.child(json_name)
        child_pointer = path.child_pointer(json_name)
        parent_ctx_obj, parent_node = parent_ctx

        # -- 0. if-feature (before when; inactive nodes are not in the effective schema) --
        if not self._if_features_active(stmt):
            if present:
                self._add(
                    path=child_path,
                    pointer=child_pointer,
                    code="if-feature",
                    message=(
                        f"Node '{name}' is present but its 'if-feature' "
                        "condition is false — this node must not exist"
                    ),
                )
            return

        # Need val and (curr_node, curr_ctx) for when, must, and type checks
        val = self._effective_value(data, stmt)
        curr_node = parent_node.step(val, stmt)
        curr_ctx = parent_ctx_obj.child(curr_node)

        # -- 1. when (RFC 7950: applicability first; report when-false before structural) --
        if debug:
            logger.debug("phase 1 when path=%s", child_path)
        if self._constraint_checks and isinstance(stmt, YangStatementWithWhen) and stmt.when is not None:
            if getattr(stmt.when, "evaluate_with_parent_context", False):
                when_ctx, when_node = parent_ctx_obj, parent_node
            else:
                when_ctx, when_node = curr_ctx, curr_node
            when_ok = self._eval_expr(stmt.when.ast, when_ctx, when_node)
            if when_ok is None:
                when_ok = True
            if not when_ok and present:
                self._add(
                    path=child_path,
                    pointer=child_pointer,
                    code="when",
                    message=(
                        f"Node '{name}' is present but its 'when' condition "
                        "evaluates to false — this node must not exist"
                    ),
                    expression=stmt.when.condition,
                )
                return
            if not when_ok:
                return

        # -- JSON shape (RFC 7951 §5), before structural checks. A wrong shape is an error;
        #    do not skip the node or wrap a scalar leaf-list as a one-element list. --
        if present:
            if isinstance(stmt, YangContainerStmt) and not isinstance(val, dict):
                self._add(
                    path=child_path,
                    pointer=child_pointer,
                    code="type",
                    message="container must be an object",
                )
                return
            if isinstance(stmt, YangListStmt):
                if not isinstance(val, list):
                    self._add(
                        path=child_path,
                        pointer=child_pointer,
                        code="type",
                        message="list must be an array",
                    )
                    return
                for i, entry in enumerate(val):
                    if not isinstance(entry, dict):
                        self._add(
                            path=f"{child_path}[{i}]",
                            pointer=f"{child_pointer}/{i}",
                            code="type",
                            message="list item must be an object",
                        )
            if isinstance(stmt, YangLeafListStmt) and not isinstance(val, list):
                self._add(
                    path=child_path,
                    pointer=child_pointer,
                    code="type",
                    message="leaf-list must be an array",
                )
                return

        # -- 2. Structural (mandatory, min/max-elements, presence) —
        if debug:
            logger.debug("phase 2 structural path=%s", child_path)
        if not self._check_structural(stmt, name, data, child_path, child_pointer, enforce_mandatory_choice):
            if isinstance(stmt, YangContainerStmt) and stmt.presence is None and not present:
                # RFC 7950 §7.5.1: a non-presence container exists implicitly, so
                # mandatory and min-elements below it still apply.
                empty_node = parent_node.step({}, stmt)
                path.push(name, pointer_name=json_name)
                child_enforce = self._child_enforce_mandatory_choice(stmt, enforce_mandatory_choice)
                self._visit_children({}, stmt, (parent_ctx_obj.child(empty_node), empty_node), path, child_enforce)
                path.pop()
            return

        # -- 3. must (evaluated in current node context) --
        if debug:
            logger.debug("phase 3 must path=%s", child_path)
        if self._constraint_checks and isinstance(stmt, YangStatementWithMust) and not isinstance(stmt, YangListStmt):
            if isinstance(stmt, YangLeafListStmt):
                # Leaf-list: evaluate must per element; skip when empty.
                # A non-array value was already rejected above.
                items = val if isinstance(val, list) else []
                for i, item in enumerate(items):
                    item_node = parent_node.step(item, stmt)
                    item_ctx = parent_ctx_obj.child(item_node)
                    item_path = f"{child_path}[{i}]"
                    item_pointer = f"{child_pointer}/{i}"
                    self._check_must(stmt, item_ctx, item_node, item_path, item_pointer)
            else:
                self._check_must(stmt, curr_ctx, curr_node, child_path, child_pointer)

        if isinstance(stmt, YangAnydataStmt) and self._anydata_validation is not None:
            if isinstance(val, dict):
                from ..ext.anydata_validation import run_anydata_subtree_validation

                run_anydata_subtree_validation(self, val, child_path)

        # -- 4. Type check --
        type_stmt = getattr(stmt, "type", None)
        type_name = getattr(type_stmt, "name", None) if type_stmt else None
        if debug:
            logger.debug("phase 4 type path=%s type=%s", child_path, type_name)
        if self._constraint_checks and (isinstance(stmt, YangLeafStmt) and stmt.type is not None and val is not None):
            if type_name == "leafref":
                logger.debug("phase 4 type: leafref require-instance check path=%s", child_path)
            for code, msg in self._type_checker.check(
                val,
                stmt.type,
                child_path,
                self._root_data,
                self._root_schema,
                ctx=curr_ctx,
                evaluator=self._evaluator,
                leafref_current=curr_node,
            ):
                severity = self._leafref_severity if type_name == "leafref" else Severity.ERROR
                self._add(
                    path=child_path,
                    pointer=child_pointer,
                    code=code,
                    message=msg,
                    severity=severity,
                )
        elif self._constraint_checks and isinstance(stmt, YangLeafListStmt) and stmt.type is not None:
            # A non-array value was already rejected above.
            items = val if isinstance(val, list) else []
            leaf_list_leafref = getattr(stmt.type, "name", None) == "leafref"
            for i, item in enumerate(items):
                item_node = parent_node.step(item, stmt)
                item_ctx = parent_ctx_obj.child(item_node)
                item_path = f"{child_path}[{i}]"
                item_pointer = f"{child_pointer}/{i}"
                for code, msg in self._type_checker.check(
                    item,
                    stmt.type,
                    item_path,
                    self._root_data,
                    self._root_schema,
                    ctx=item_ctx,
                    evaluator=self._evaluator,
                    leafref_current=parent_node,
                ):
                    severity = self._leafref_severity if leaf_list_leafref else Severity.ERROR
                    self._add(
                        path=item_path,
                        pointer=item_pointer,
                        code=code,
                        message=msg,
                        severity=severity,
                    )

        # -- 5. Descend --
        if debug:
            logger.debug("phase 5 descend path=%s", child_path)
        if isinstance(stmt, YangContainerStmt) and isinstance(val, dict):
            path.push(name, pointer_name=json_name)
            child_enforce = self._child_enforce_mandatory_choice(stmt, enforce_mandatory_choice)
            self._visit_children(val, stmt, (curr_ctx, curr_node), path, child_enforce)
            path.pop()
        elif isinstance(stmt, YangListStmt) and isinstance(val, list):
            key_names = [k.strip() for k in stmt.key.split()] if stmt.key else []
            self._check_list_key_uniqueness(val, key_names, name, child_path, child_pointer)
            if self._constraint_checks:
                self._check_list_unique(stmt, val, child_path, child_pointer)
            for i, entry in enumerate(val):
                if not isinstance(entry, dict):
                    continue
                path.push(
                    name,
                    self._entry_key_from_names(entry, key_names),
                    index=i,
                    pointer_name=json_name,
                )
                entry_node = Node(entry, stmt, parent_node)
                entry_ctx = curr_ctx.child(entry_node)
                if self._constraint_checks:
                    self._check_must(stmt, entry_ctx, entry_node, path.current(), path.pointer())
                entry_enforce = self._child_enforce_mandatory_choice(stmt, enforce_mandatory_choice)
                self._visit_children(entry, stmt, (entry_ctx, entry_node), path, entry_enforce)
                path.pop()

    def _choice_has_branch_data(self, choice: YangChoiceStmt, data: Dict[str, Any]) -> bool:
        """True if any schema child under any case has matching data in ``data``."""
        return any(self._case_has_any_stmt_data(c, data) for c in choice.cases)

    def _stmt_instance_keys_from_data(self, stmt: YangStatement, data: dict[str, Any]) -> set[str]:
        """Instance keys under ``data`` claimed by this statement (same nesting level)."""
        parent_mod = self._encoding_parent_module()
        keys = member_keys_cached(stmt, parent_mod)
        if isinstance(stmt, YangChoiceStmt):
            if keys & data.keys():
                return keys & data.keys()
            return self._choice_instance_keys(stmt, data)
        return keys & data.keys()

    def _choice_instance_keys(self, choice: YangChoiceStmt, data: dict[str, Any]) -> set[str]:
        """Keys in ``data`` consumed by this choice (nested choices: leaves stay at this level)."""
        if not self._if_features_active(choice):
            return set()
        active_cases = [
            c for c in choice.cases if self._if_features_active(c) and self._case_has_any_stmt_data(c, data)
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
                self._add(
                    path=path.current(),
                    pointer=path.pointer(),
                    code="if-feature",
                    message=(
                        f"Choice '{choice.name}' has data but its 'if-feature' "
                        "condition is false — this branch must not exist"
                    ),
                )
            return

        if self._constraint_checks and choice.when is not None:
            when_ok = self._eval_expr(choice.when.ast, parent_ctx_obj, parent_node)
            if when_ok is None:
                when_ok = True
            if not when_ok:
                if self._choice_has_branch_data(choice, data):
                    self._add(
                        path=path.current(),
                        pointer=path.pointer(),
                        code="when",
                        message=(
                            f"Choice '{choice.name}' has data but its 'when' "
                            "evaluates to false — this branch must not exist"
                        ),
                        expression=choice.when.condition,
                    )
                return

        active_cases: list[YangCaseStmt] = []
        for case in choice.cases:
            if not self._if_features_active(case):
                if self._case_has_any_stmt_data(case, data):
                    self._add(
                        path=path.current(),
                        pointer=path.pointer(),
                        code="if-feature",
                        message=(
                            f"Case '{case.name}' of choice '{choice.name}' has "
                            "data but its 'if-feature' condition is false — "
                            "this branch must not exist"
                        ),
                    )
                    return
                continue
            if not self._case_has_any_stmt_data(case, data):
                continue
            if self._constraint_checks and case.when is not None:
                c_ok = self._eval_expr(case.when.ast, parent_ctx_obj, parent_node)
                if c_ok is None:
                    c_ok = True
                if not c_ok:
                    self._add(
                        path=path.current(),
                        pointer=path.pointer(),
                        code="when",
                        message=(
                            f"Case '{case.name}' of choice '{choice.name}' has "
                            "data but its 'when' evaluates to false — this branch "
                            "must not exist"
                        ),
                        expression=case.when.condition,
                    )
                    return
            active_cases.append(case)

        if len(active_cases) > 1:
            names = ", ".join(c.name for c in active_cases)
            self._add(
                path=path.current(),
                pointer=path.pointer(),
                code="choice-multiple-cases",
                message=(f"Choice '{choice.name}' allows only one case; " f"data matches multiple cases: {names}"),
            )
            return

        active_case = active_cases[0] if active_cases else None

        if active_case is None:
            if self._mandatory_choice_violation(choice, data, enforce_mandatory_choice):
                self._add(
                    path=path.current(),
                    pointer=path.pointer(),
                    code="mandatory-choice",
                    message=f"Mandatory choice '{choice.name}' has no active case",
                )
            return

        # Validate only statements in the active case.
        # Do not call _visit_children here: its unknown-field check is scoped to the
        # provided schema node and would incorrectly flag sibling fields (outside this
        # choice) as unknown when validating list/container entries.
        self._case_stack.append(active_case)
        self._case_level_data_stack.append(data)
        try:
            inner_enforce = self._child_enforce_mandatory_choice(active_case, enforce_mandatory_choice)
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
        pointer: str,
        enforce_mandatory_choice: bool,
    ) -> bool:
        parent_mod = self._encoding_parent_module()
        present = instance_member_present(data, stmt, parent_mod)
        effective = self._effective_value(data, stmt)

        if isinstance(stmt, YangLeafStmt):
            # YANG type empty: leaf has no value, only presence; treat as present when key is in data
            type_name = getattr(getattr(stmt, "type", None), "name", None)
            if type_name == "empty" and present:
                return True
            if effective is None and stmt.mandatory:
                if self._leaf_mandatory_must_exist(stmt, data, enforce_mandatory_choice):
                    self._add(
                        path=path,
                        pointer=pointer,
                        code="mandatory",
                        message=f"Mandatory leaf '{name}' is missing",
                    )
            return effective is not None

        if isinstance(stmt, (YangAnydataStmt, YangAnyxmlStmt)):
            if effective is None and stmt.mandatory:
                if self._leaf_mandatory_must_exist(stmt, data, enforce_mandatory_choice):
                    kind = "anydata" if isinstance(stmt, YangAnydataStmt) else "anyxml"
                    self._add(
                        path=path,
                        pointer=pointer,
                        code="mandatory",
                        message=f"Mandatory {kind} '{name}' is missing",
                    )
            return effective is not None

        if isinstance(stmt, YangContainerStmt):
            return present

        if isinstance(stmt, (YangListStmt, YangLeafListStmt)):
            count = len(effective) if isinstance(effective, list) else (1 if effective is not None else 0)
            min_e = getattr(stmt, "min_elements", None)
            max_e = getattr(stmt, "max_elements", None)
            # RFC 7950 §7.7.5: min-elements also applies to an absent list (count 0).
            if min_e is not None and count < min_e:
                self._add(
                    path=path,
                    pointer=pointer,
                    code="min-elements",
                    message=(f"'{name}' has {count} element(s) but " f"requires at least {min_e}"),
                )
            if max_e is not None and present and count > max_e:
                self._add(
                    path=path,
                    pointer=pointer,
                    code="max-elements",
                    message=(f"'{name}' has {count} element(s) but " f"allows at most {max_e}"),
                )
            return present

        return present

    # ------------------------------------------------------------------
    # XPath evaluation
    # ------------------------------------------------------------------

    def _eval_expr(self, ast: Any, ctx: Context, node: Node) -> Optional[bool]:
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
        pointer: str,
    ) -> None:
        for must in stmt.must_statements:
            result = self._eval_expr(must.ast, ctx, node)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("must result path=%s result=%s", path, result)
            if result is None:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("must ERROR (eval failed) path=%s", path)
                self._add(
                    path=path,
                    pointer=pointer,
                    code="xpath-error",
                    message=f"Error evaluating must expression on '{stmt.name}'",
                    expression=must.expression,
                )
            elif not result:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("must FAIL (constraint not satisfied) path=%s", path)
                self._add(
                    path=path,
                    pointer=pointer,
                    code="must",
                    message=must.error_message or (f"must constraint not satisfied on '{stmt.name}'"),
                    expression=must.expression,
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
        pointer: str,
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
                key_display = ", ".join(f"{k}='{entry.get(k)}'" for k in key_names)
                self._add(
                    path=path_str,
                    pointer=pointer,
                    code="duplicate-key",
                    message=(
                        f"Duplicate key in list '{list_name}': {key_display} " f"(entries at index {first_idx} and {i})"
                    ),
                    expression="",
                )
                return True
            seen_keys[key_tuple] = i
        return False

    def _check_list_unique(self, stmt: YangListStmt, val: list, path_str: str, pointer: str) -> None:
        """RFC 7950 §7.8.3: one error per ``unique`` set whose values repeat across entries.

        Entries missing any leaf of the set are ignored.
        """
        for paths in stmt.unique:
            seen: Dict[str, int] = {}
            for i, entry in enumerate(val):
                values = [_descendant_value(entry, p) for p in paths]
                if any(v is _MISSING for v in values):
                    continue
                token = json.dumps(values, sort_keys=True, default=str)
                if token in seen:
                    shown = ", ".join(f"{p}='{_unique_display(v)}'" for p, v in zip(paths, values))
                    self._add(
                        path=path_str,
                        pointer=pointer,
                        code="unique",
                        message=(
                            f"Unique constraint violated in list '{stmt.name}': {shown} "
                            f"(entries at index {seen[token]} and {i})"
                        ),
                    )
                    break
                seen[token] = i

    def _entry_key_from_names(self, entry: Any, key_names: List[str]) -> Optional[str]:
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
