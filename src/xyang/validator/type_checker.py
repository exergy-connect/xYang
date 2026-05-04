"""
Type checker for YANG document validation.
"""

from __future__ import annotations

import base64
import binascii
import logging
import re
import sys
from typing import Any, List, Optional

from ..ast import YangTypeStmt
from ..errors import XPathSyntaxError
from ..identity_graph import (
    identityref_value_valid,
    resolve_identity_qname_pair,
)
from ..module import YangModule
from ..xpath import XPathParser
from ..xpath.ast import ASTNode, PathNode
from ..xpath.node import Context, Node

logger = logging.getLogger("xyang.validator")


def _instance_identifier_path_errors(
    expr: ASTNode,
    value_repr: str,
    ctx: Context,
    evaluator: Any,
) -> List[str]:
    """Path shape and require-instance target check for a parsed instance-identifier.

    Kept as a module function so ``isinstance(expr, PathNode)`` and uses of
    ``PathNode`` (e.g. ``is_absolute``) stay in one scope; some linters do not
    narrow types across call boundaries or after ``try``/``except`` assignments.
    """
    if not isinstance(expr, PathNode):
        return [
            "instance-identifier: value must be a path expression (e.g. /top/leaf)"
        ]
    if not expr.is_absolute:
        return [
            "instance-identifier: only absolute paths are supported "
            "(path must start with '/')"
        ]
    nodes = evaluator.eval(expr, ctx, ctx.root)
    if not nodes:
        return [
            f"instance-identifier: no instance at path {value_repr!r} "
            "(require-instance is true)"
        ]
    return []


def _pattern_entry_violation_message(entry: Any, *, default: str) -> str:
    msg = default
    em = getattr(entry, "error_message", None)
    if isinstance(em, str) and em:
        msg = em
    tag = getattr(entry, "error_app_tag", None)
    if isinstance(tag, str) and tag:
        return f"{msg} (error-app-tag: {tag})"
    return msg


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

        if ":" in name:
            if not isinstance(root_schema, YangModule):
                return []
            pref, _, local = name.partition(":")
            ext = root_schema.resolve_prefixed_module(pref)
            if ext is None:
                return [f"unknown type prefix {pref!r} in type {name!r}"]
            typedef = ext.get_typedef(local)
            if typedef is not None and typedef.type is not None:
                return self.check(
                    value,
                    typedef.type,
                    path,
                    root_data,
                    root_schema,
                    ctx,
                    evaluator,
                    leafref_current,
                )
            return [f"unknown typedef {local!r} in imported module {pref!r}"]

        if name == "union":
            return self._check_union(
                value,
                type_stmt,
                path,
                root_data,
                root_schema,
                ctx=ctx,
                evaluator=evaluator,
                leafref_current=leafref_current,
            )
        if name == "identityref":
            return self._check_identityref(value, type_stmt, root_schema)
        if name == "instance-identifier":
            return self._check_instance_identifier(
                value, type_stmt, ctx, evaluator
            )
        if name == "leafref":
            return self._check_leafref(
                value,
                type_stmt,
                path,
                ctx=ctx,
                evaluator=evaluator,
                leafref_current=leafref_current,
            )
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
        if name == "bits":
            return self._check_bits(value, type_stmt)
        if name == "empty":
            return self._check_empty(value)
        if name == "binary":
            return self._check_binary(value, type_stmt)
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

    def _check_identityref(
        self, value: Any, type_stmt: YangTypeStmt, root_schema: Any
    ) -> List[str]:
        if not isinstance(value, str):
            return [f"identityref value must be a string, got {type(value).__name__}"]
        if not isinstance(root_schema, YangModule):
            return ["identityref validation requires module schema"]
        bases = getattr(type_stmt, "identityref_bases", None) or []
        if not bases:
            return ["identityref type has no base identities"]
        if resolve_identity_qname_pair(root_schema, value) is None:
            return [
                f"identityref value {value!r} does not resolve to a known identity"
            ]
        if not identityref_value_valid(root_schema, value, bases):
            return [
                f"identityref value {value!r} is not derived from all bases {bases!r}"
            ]
        return []

    def _check_instance_identifier(
        self,
        value: Any,
        type_stmt: YangTypeStmt,
        ctx: Context,
        evaluator: Any,
    ) -> List[str]:
        """RFC 7950 instance-identifier: string path; optional require-instance existence check."""
        if not isinstance(value, str):
            return [
                f"instance-identifier value must be a string, got {type(value).__name__}"
            ]
        if not getattr(type_stmt, "require_instance", True):
            return []
        s = value.strip()
        if not s:
            return ["instance-identifier path must not be empty when require-instance is true"]
        try:
            parsed = XPathParser(s).parse()
        except XPathSyntaxError as e:
            return [f"instance-identifier: invalid path expression ({e})"]
        return _instance_identifier_path_errors(parsed, value, ctx, evaluator)

    def _check_union(
        self,
        value: Any,
        type_stmt: YangTypeStmt,
        path: str,
        root_data: Any,
        root_schema: Any,
        *,
        ctx: Context,
        evaluator: Any,
        leafref_current: Optional[Node] = None,
    ) -> List[str]:
        for member in type_stmt.types:
            if not self.check(
                value,
                member,
                path,
                root_data,
                root_schema,
                ctx=ctx,
                evaluator=evaluator,
                leafref_current=leafref_current,
            ):
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
        # For relative paths and current() in predicates, use leafref_current (parent of leaf)
        current_node = leafref_current if leafref_current is not None else ctx.current
        if leafref_current is not None and leafref_current is not ctx.current:
            leafref_ctx = Context(current=leafref_current, root=ctx.root, path_cache=ctx.path_cache)
        else:
            leafref_ctx = ctx
        if path_ast.is_absolute:
            start_node = ctx.root
        else:
            if current_node is None:
                logger.debug("_check_leafref FAIL node_path=%s (no ctxt for rel path)", node_path)
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
        patterns = list(getattr(type_stmt, "patterns", None) or [])
        if patterns:
            for p in patterns:
                patt = getattr(p, "pattern", None)
                if not isinstance(patt, str) or not patt:
                    continue
                matched = re.fullmatch(patt, s) is not None
                invert = bool(getattr(p, "invert_match", False))
                if (not invert and not matched) or (invert and matched):
                    default_msg = (
                        f"Value {s!r} does not match pattern {patt!r}"
                        if not invert
                        else f"Value {s!r} matches forbidden pattern {patt!r} (invert-match)"
                    )
                    errors.append(
                        _pattern_entry_violation_message(p, default=default_msg)
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
        fd = getattr(type_stmt, "fraction_digits", None)
        if fd is not None and fd >= 0:
            s = str(value).strip()
            if "." in s:
                frac = s.split(".", 1)[1]
                if len(frac) > int(fd):
                    return [
                        f"Value has more than {fd} fraction digits (decimal64 fraction-digits)"
                    ]
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
        if not type_stmt.enums:
            return [
                "enumeration type has no enum definitions in schema; cannot validate instance data"
            ]
        allowed = [str(e) for e in type_stmt.enums]
        if str(value) not in allowed:
            return [
                f"Value {value!r} is not one of the allowed enum values: "
                f"{', '.join(allowed)}"
            ]
        return []

    def _check_bits(self, value: Any, type_stmt: YangTypeStmt) -> List[str]:
        """RFC 7950 bits: instance is a space-separated list of bit names (JSON: string)."""
        if not isinstance(value, str):
            return [
                f"bits value must be a string (space-sep bit names), got {type(value).__name__}"
            ]
        bits = type_stmt.bits or []
        allowed = {b.name for b in bits}
        if not allowed:
            return ["bits type has no bit definitions"]
        parts = [p for p in (s.strip() for s in value.split()) if p]
        seen: set[str] = set()
        for token in parts:
            if token in seen:
                return [f"Duplicate bit {token!r} in bits value"]
            seen.add(token)
            if token not in allowed:
                return [
                    f"Unknown bit {token!r}; allowed: {', '.join(sorted(allowed))}"
                ]
        return []

    def _check_empty(self, value: Any) -> List[str]:
        if value not in (None, True, "", {}):
            return [f"Empty type leaf should have no value, got {value!r}"]
        return []

    def _check_binary(self, value: Any, type_stmt: YangTypeStmt) -> List[str]:
        """RFC 7950 binary: base64 in JSON; ``length`` applies to decoded octet count."""
        if not isinstance(value, str):
            return [
                f"binary value must be a base64-encoded string, got {type(value).__name__}"
            ]
        s = value.strip()
        try:
            if not s:
                decoded = b""
            elif sys.version_info >= (3, 11):
                decoded = base64.b64decode(s, validate=True)
            else:
                decoded = base64.b64decode(s)
        except binascii.Error:
            return ["binary value is not valid base64"]
        if type_stmt.length:
            lo, hi = self._parse_range(type_stmt.length)
            n = len(decoded)
            if lo is not None and n < lo:
                return [
                    f"binary decoded length {n} octets is less than minimum {int(lo)}"
                ]
            if hi is not None and n > hi:
                return [
                    f"binary decoded length {n} octets exceeds maximum {int(hi)}"
                ]
        patterns = list(getattr(type_stmt, "patterns", None) or [])
        for p in patterns:
            patt = getattr(p, "pattern", None)
            if not isinstance(patt, str) or not patt:
                continue
            matched = re.fullmatch(patt, s) is not None
            invert = bool(getattr(p, "invert_match", False))
            if (not invert and not matched) or (invert and matched):
                default_msg = (
                    f"binary value {s!r} does not match pattern {patt!r}"
                    if not invert
                    else f"binary value {s!r} matches forbidden pattern {patt!r} (invert-match)"
                )
                return [_pattern_entry_violation_message(p, default=default_msg)]
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
