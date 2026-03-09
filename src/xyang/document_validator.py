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

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .ast import (
    YangCaseStmt,
    YangChoiceStmt,
    YangContainerStmt,
    YangLeafListStmt,
    YangLeafStmt,
    YangListStmt,
    YangMustStmt,
    YangStatement,
    YangStatementList,
    YangStatementWithMust,
    YangStatementWithWhen,
    YangTypeStmt,
    YangWhenStmt,
)
from .xpath.evaluator import XPathEvaluator
from .xpath.node import Context, Node
from .xpath.utils import yang_bool
from .xpath.validator import Validator as XPathValidator


# =============================================================================
# Validation error
# =============================================================================


@dataclass
class ValidationError:
    """
    A single validation failure.

    path        -- XPath-like location, e.g.
                   /data-model/entities[name='foo']/fields[name='bar']/minDate
    message     -- human- and AI-readable description of what failed
    expression  -- the failing XPath expression string, if applicable
    """

    path: str
    message: str
    expression: str = ""

    def __str__(self) -> str:
        if self.expression:
            return f"{self.path}: {self.message} (expression: {self.expression})"
        return f"{self.path}: {self.message}"


# =============================================================================
# Path builder
# =============================================================================


class PathBuilder:
    """
    Maintains the current path string as the walker descends.
    List entries use key predicates: /data-model/entities[name='foo']
    """

    def __init__(self) -> None:
        self._segments: List[str] = []

    def push(self, name: str, key: Optional[str] = None) -> None:
        self._segments.append(f"{name}[{key}]" if key is not None else name)

    def pop(self) -> None:
        self._segments.pop()

    def current(self) -> str:
        return "/" + "/".join(self._segments) if self._segments else "/"

    def child(self, name: str, key: Optional[str] = None) -> str:
        seg = f"{name}[{key}]" if key is not None else name
        return self.current().rstrip("/") + "/" + seg


# =============================================================================
# Type checker
# =============================================================================


class TypeChecker:
    """
    Checks a data value against a YangTypeStmt.
    Returns a list of error message strings (empty = valid).
    """

    def check(
        self,
        value: Any,
        type_stmt: YangTypeStmt,
        path: str,
        root_data: Any,
        root_schema: Any,
    ) -> List[str]:
        name = type_stmt.name

        if name == "union":
            return self._check_union(value, type_stmt, path, root_data, root_schema)
        if name == "leafref":
            return self._check_leafref(value, type_stmt, path, root_data)
        if name in (
            "string",
            "entity-name",
            "field-name",
            "identifier",
            "version-string",
            "date",
            "date-and-time",
            "qualified-source",
        ):
            return self._check_string(value, type_stmt)
        if name in (
            "int8",
            "int16",
            "int32",
            "int64",
            "uint8",
            "uint16",
            "uint32",
            "uint64",
            "integer",
        ):
            return self._check_integer(value, type_stmt)
        if name in ("decimal64", "number"):
            return self._check_decimal(value, type_stmt)
        if name == "boolean":
            return self._check_boolean(value)
        if name == "enumeration":
            return self._check_enum(value, type_stmt)
        if name == "empty":
            return self._check_empty(value)
        return []

    def _check_union(
        self,
        value: Any,
        type_stmt: YangTypeStmt,
        path: str,
        root_data: Any,
        root_schema: Any,
    ) -> List[str]:
        for member in type_stmt.types:
            if not self.check(value, member, path, root_data, root_schema):
                return []
        names = ", ".join(t.name for t in type_stmt.types)
        return [f"Value {value!r} does not match any union member type ({names})"]

    def _check_leafref(
        self,
        value: Any,
        type_stmt: YangTypeStmt,
        path: str,
        root_data: Any,
    ) -> List[str]:
        if not type_stmt.require_instance or not type_stmt.path:
            return []
        targets = self._resolve_path(type_stmt.path, root_data)
        if value not in targets:
            return [
                f"Leafref value {value!r} not found via path {type_stmt.path!r} "
                "(require-instance is true)"
            ]
        return []

    def _resolve_path(self, path_str: str, root_data: Any) -> List[Any]:
        """Walk a simple absolute path and collect leaf values."""
        parts = [p for p in path_str.strip("/").split("/") if p]
        nodes = [root_data]
        for part in parts:
            next_nodes: List[Any] = []
            for n in nodes:
                if isinstance(n, dict) and part in n:
                    v = n[part]
                    if isinstance(v, list):
                        next_nodes.extend(v)
                    elif v is not None:
                        next_nodes.append(v)
                elif isinstance(n, list):
                    for item in n:
                        if isinstance(item, dict) and part in item:
                            v = item[part]
                            if isinstance(v, list):
                                next_nodes.extend(v)
                            elif v is not None:
                                next_nodes.append(v)
            nodes = next_nodes
        return nodes

    def _check_string(
        self, value: Any, type_stmt: YangTypeStmt
    ) -> List[str]:
        errors: List[str] = []
        s = str(value) if not isinstance(value, str) else value
        if type_stmt.length:
            lo, hi = self._parse_range(type_stmt.length)
            n = len(s)
            if lo is not None and n < lo:
                errors.append(f"String length {n} is less than minimum {lo}")
            if hi is not None and n > hi:
                errors.append(f"String length {n} exceeds maximum {hi}")
        if type_stmt.pattern:
            if not re.fullmatch(type_stmt.pattern, s):
                errors.append(
                    f"Value {s!r} does not match pattern {type_stmt.pattern!r}"
                )
        if type_stmt.enums:
            if s not in [str(e) for e in type_stmt.enums]:
                errors.append(
                    f"Value {s!r} is not one of: "
                    f"{', '.join(str(e) for e in type_stmt.enums)}"
                )
        return errors

    def _check_integer(
        self, value: Any, type_stmt: YangTypeStmt
    ) -> List[str]:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return [f"Value {value!r} is not a valid integer"]
        if type_stmt.range:
            lo, hi = self._parse_range(type_stmt.range)
            if lo is not None and n < lo:
                return [f"Value {n} is less than minimum {lo}"]
            if hi is not None and n > hi:
                return [f"Value {n} exceeds maximum {hi}"]
        return []

    def _check_decimal(
        self, value: Any, type_stmt: YangTypeStmt
    ) -> List[str]:
        try:
            n = float(value)
        except (TypeError, ValueError):
            return [f"Value {value!r} is not a valid number"]
        if type_stmt.range:
            lo, hi = self._parse_range(type_stmt.range)
            if lo is not None and n < lo:
                return [f"Value {n} is less than minimum {lo}"]
            if hi is not None and n > hi:
                return [f"Value {n} exceeds maximum {hi}"]
        return []

    def _check_boolean(self, value: Any) -> List[str]:
        if value not in (True, False, "true", "false"):
            return [
                f"Value {value!r} is not a valid boolean (expected true or false)"
            ]
        return []

    def _check_enum(
        self, value: Any, type_stmt: YangTypeStmt
    ) -> List[str]:
        if type_stmt.enums and str(value) not in [str(e) for e in type_stmt.enums]:
            return [
                f"Value {value!r} is not one of the allowed enum values: "
                f"{', '.join(str(e) for e in type_stmt.enums)}"
            ]
        return []

    def _check_empty(self, value: Any) -> List[str]:
        if value not in (None, True, "", {}):
            return [f"Empty type leaf should have no value, got {value!r}"]
        return []

    def _parse_range(
        self, range_str: str
    ) -> tuple[Optional[float], Optional[float]]:
        range_str = range_str.strip()
        if ".." in range_str:
            lo_s, hi_s = range_str.split("..", 1)
            lo = None if lo_s.strip() == "min" else self._to_num(lo_s.strip())
            hi = None if hi_s.strip() == "max" else self._to_num(hi_s.strip())
            return lo, hi
        n = self._to_num(range_str)
        return n, n

    def _to_num(self, s: str) -> Optional[float]:
        try:
            return int(s)
        except ValueError:
            try:
                return float(s)
            except ValueError:
                return None


# =============================================================================
# Document validator
# =============================================================================


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

    def validate(self, data: Any) -> List[ValidationError]:
        errors: List[ValidationError] = []
        xpath_v = XPathValidator(data, self._root_schema)
        ctx, node = xpath_v.make_context(data, self._root_schema, parent=None)
        path = PathBuilder()
        self._visit_children(
            data=data,
            schema=self._root_schema,
            parent_ctx=(ctx, node),
            xpath_v=xpath_v,
            path=path,
            errors=errors,
            root_data=data,
        )
        return errors

    # ------------------------------------------------------------------
    # Tree walk
    # ------------------------------------------------------------------

    def _visit_children(
        self,
        data: Any,
        schema: YangStatementList,
        parent_ctx: tuple,
        xpath_v: XPathValidator,
        path: PathBuilder,
        errors: List[ValidationError],
        root_data: Any,
    ) -> None:
        if not isinstance(data, dict):
            return
        for stmt in schema.statements:
            self._visit_stmt(
                stmt, data, parent_ctx, xpath_v, path, errors, root_data
            )

    def _visit_stmt(
        self,
        stmt: YangStatement,
        data: Dict[str, Any],
        parent_ctx: tuple,
        xpath_v: XPathValidator,
        path: PathBuilder,
        errors: List[ValidationError],
        root_data: Any,
    ) -> None:
        if isinstance(stmt, YangChoiceStmt):
            self._visit_choice(
                stmt, data, parent_ctx, xpath_v, path, errors, root_data
            )
            return
        if isinstance(stmt, YangCaseStmt):
            self._visit_children(
                data, stmt, parent_ctx, xpath_v, path, errors, root_data
            )
            return

        name = stmt.name
        present = name in data
        child_path = path.child(name)
        parent_ctx_obj, parent_node = parent_ctx

        # -- 1. when (evaluated in parent context) --
        if isinstance(stmt, YangStatementWithWhen) and stmt.when is not None:
            when_ok = self._eval_expr(stmt.when.ast, parent_ctx_obj, parent_node)
            if when_ok is None:
                when_ok = True
            if not when_ok and present:
                errors.append(
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

        # -- 2. Structural checks --
        if not self._check_structural(stmt, name, data, child_path, errors):
            return

        val = data.get(name)
        curr_ctx, curr_node = xpath_v.make_context(val, stmt, parent=parent_node)

        # -- 3. must (evaluated in current node context) --
        if isinstance(stmt, YangStatementWithMust) and not isinstance(
            stmt, YangListStmt
        ):
            self._check_must(stmt, curr_ctx, curr_node, child_path, errors)

        # -- 4. Type check --
        if (
            isinstance(stmt, YangLeafStmt)
            and stmt.type is not None
            and val is not None
        ):
            for msg in self._type_checker.check(
                val, stmt.type, child_path, root_data, self._root_schema
            ):
                errors.append(ValidationError(path=child_path, message=msg))
        elif isinstance(stmt, YangLeafListStmt) and stmt.type is not None:
            items = (
                val if isinstance(val, list) else ([val] if val is not None else [])
            )
            for i, item in enumerate(items):
                item_path = f"{child_path}[{i}]"
                for msg in self._type_checker.check(
                    item, stmt.type, item_path, root_data, self._root_schema
                ):
                    errors.append(ValidationError(path=item_path, message=msg))

        # -- 5. Descend --
        if isinstance(stmt, YangContainerStmt) and isinstance(val, dict):
            path.push(name)
            self._visit_children(
                val, stmt, (curr_ctx, curr_node), xpath_v, path, errors, root_data
            )
            path.pop()
        elif isinstance(stmt, YangListStmt) and isinstance(val, list):
            for entry in val:
                key = self._entry_key(entry, stmt)
                path.push(name, key)
                entry_ctx, entry_node = xpath_v.make_context(
                    entry, stmt, parent=parent_node
                )
                self._check_must(
                    stmt, entry_ctx, entry_node, path.current(), errors
                )
                self._visit_children(
                    entry,
                    stmt,
                    (entry_ctx, entry_node),
                    xpath_v,
                    path,
                    errors,
                    root_data,
                )
                path.pop()

    def _visit_choice(
        self,
        choice: YangChoiceStmt,
        data: Dict[str, Any],
        parent_ctx: tuple,
        xpath_v: XPathValidator,
        path: PathBuilder,
        errors: List[ValidationError],
        root_data: Any,
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
                errors.append(
                    ValidationError(
                        path=path.current(),
                        message=f"Mandatory choice '{choice.name}' has no active case",
                    )
                )
            return

        self._visit_children(
            data, active_case, parent_ctx, xpath_v, path, errors, root_data
        )

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
        errors: List[ValidationError],
    ) -> bool:
        present = name in data
        val = data.get(name)

        if isinstance(stmt, YangLeafStmt):
            if not present and stmt.mandatory and stmt.default is None:
                errors.append(
                    ValidationError(
                        path=path,
                        message=f"Mandatory leaf '{name}' is missing",
                    )
                )
            return present

        if isinstance(stmt, YangContainerStmt):
            return present

        if isinstance(stmt, (YangListStmt, YangLeafListStmt)):
            count = (
                len(val)
                if isinstance(val, list)
                else (1 if val is not None else 0)
            )
            min_e = getattr(stmt, "min_elements", None)
            max_e = getattr(stmt, "max_elements", None)
            # Only enforce min/max when list is present (YANG: optional list may be omitted)
            if min_e is not None and present and count < min_e:
                errors.append(
                    ValidationError(
                        path=path,
                        message=(
                            f"'{name}' has {count} element(s) but "
                            f"requires at least {min_e}"
                        ),
                    )
                )
            if max_e is not None and present and count > max_e:
                errors.append(
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
        errors: List[ValidationError],
    ) -> None:
        for must in stmt.must_statements:
            result = self._eval_expr(must.ast, ctx, node)
            if result is None:
                errors.append(
                    ValidationError(
                        path=path,
                        message=f"Error evaluating must expression on '{stmt.name}'",
                        expression=must.expression,
                    )
                )
            elif not result:
                errors.append(
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

    def _entry_key(self, entry: Any, list_stmt: YangListStmt) -> Optional[str]:
        if not isinstance(entry, dict) or not list_stmt.key:
            return None
        key_name = list_stmt.key.strip()
        val = entry.get(key_name)
        return f"{key_name}='{val}'" if val is not None else None
