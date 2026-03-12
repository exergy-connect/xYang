"""
Type checker for YANG document validation.
"""

from __future__ import annotations

import logging
import re
from typing import Any, List, Optional

from ..ast import YangTypeStmt
from ..xpath.node import Context, Node

logger = logging.getLogger("xyang.validator")


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
        ctx: Context,
        evaluator: Any,
        leafref_current: Optional[Node] = None,
    ) -> List[str]:
        """
        leafref_current: node to use as current() for leafref path resolution (typically
        the parent of the leaf). If None, ctx.current is used.
        """
        name = type_stmt.name

        if name == "union":
            return self._check_union(value, type_stmt, path, root_data, root_schema, ctx, evaluator, leafref_current)
        if name == "leafref":
            return self._check_leafref(value, type_stmt, path, ctx=ctx, evaluator=evaluator, leafref_current=leafref_current)
        if name in (
            "string",
            "entity-name",
            "field-name",
            "identifier",
            "date",
            "date-and-time",
            "qualified-source",
        ):
            return self._check_string(value, type_stmt)
        # version-string and other typedefs: resolve via get_typedef so pattern/constraints apply
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
        # Resolve typedef and check against the underlying type
        if getattr(root_schema, "get_typedef", None) is not None:
            typedef = root_schema.get_typedef(name)
            if typedef is not None and typedef.type is not None:
                return self.check(
                    value,
                    typedef.type,
                    path,
                    root_data,
                    root_schema,
                    ctx=ctx,
                    evaluator=evaluator,
                    leafref_current=leafref_current,
                )
        return []

    def _check_union(
        self,
        value: Any,
        type_stmt: YangTypeStmt,
        path: str,
        root_data: Any,
        root_schema: Any,
        ctx: Context,
        evaluator: Any,
        leafref_current: Optional[Node] = None,
    ) -> List[str]:
        for member in type_stmt.types:
            if not self.check(value, member, path, root_data, root_schema, ctx=ctx, evaluator=evaluator, leafref_current=leafref_current):
                return []
        names = ", ".join(t.name for t in type_stmt.types)
        return [f"Value {value!r} does not match any union member type ({names})"]

    def _check_leafref(
        self,
        value: Any,
        type_stmt: YangTypeStmt,
        node_path: str,
        ctx: Context,
        evaluator: Any,
        leafref_current: Optional[Node] = None,
    ) -> List[str]:
        if not type_stmt.require_instance or not type_stmt.path:
            return []
        path_ast = type_stmt.path
        path_str = path_ast.to_string()
        logger.debug(
            "_check_leafref require-instance node_path=%s value=%r leafref_path=%s",
            node_path,
            value,
            path_str,
        )
        # For relative paths and current() in predicates, use leafref_current (parent of leaf) when provided
        current_node = leafref_current if leafref_current is not None else ctx.current
        if leafref_current is not None and leafref_current is not ctx.current:
            leafref_ctx = Context(current=leafref_current, root=ctx.root, path_cache=ctx.path_cache)
        else:
            leafref_ctx = ctx
        if path_ast.is_absolute:
            start_node = ctx.root
        else:
            if current_node is None:
                logger.debug("_check_leafref FAIL node_path=%s (no context node for relative path)", node_path)
                return [
                    f"Leafref relative path {path_str!r} requires context node"
                ]
            start_node = current_node
        target_nodes = evaluator.eval_path(path_ast, leafref_ctx, start_node)
        targets = [n.data for n in target_nodes]
        logger.debug("_check_leafref node_path=%s targets=%s", node_path, targets)
        if value not in targets:
            logger.debug(
                "_check_leafref FAIL node_path=%s value=%r not in targets (phase 4 type check)",
                node_path,
                value,
            )
            return [
                f"Leafref value {value!r} not found via path {path_str!r} "
                "(require-instance is true)"
            ]
        return []

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
