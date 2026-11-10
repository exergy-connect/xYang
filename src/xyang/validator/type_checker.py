"""
Type checker for YANG document validation.
"""

from __future__ import annotations

import base64
import binascii
import logging
import re
from typing import Any, List, Optional

from ..ast import YangTypeStmt
from ..json.integer_bounds import YANG_INTEGER_BOUNDS
from ..errors import XPathSyntaxError
from ..identity_graph import (
    identityref_value_valid,
    resolve_identity_qname_pair,
)
from ..identifier_ref import format_identifier_ref
from ..module import YangModule
from ..xpath import XPathParser
from ..xpath.ast import ASTNode, PathNode
from ..xpath.node import Context, Node

logger = logging.getLogger("xyang.validator")

# (code, message). Codes are the ones previously inferred from message text.
TypeIssue = tuple[str, str]


def _issue(code: str, message: str) -> TypeIssue:
    return (code, message)


def _json_type_name(value: Any) -> str:
    """RFC 8259 type name of an instance value (``number``, ``boolean``, ``null``, ...)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _instance_identifier_path_errors(
    expr: ASTNode,
    value_repr: str,
    ctx: Context,
    evaluator: Any,
) -> List[TypeIssue]:
    """Path shape and require-instance target check for a parsed instance-identifier.

    Kept as a module function so ``isinstance(expr, PathNode)`` and uses of
    ``PathNode`` (e.g. ``is_absolute``) stay in one scope; some linters do not
    narrow types across call boundaries or after ``try``/``except`` assignments.
    """
    if not isinstance(expr, PathNode):
        return [
            _issue(
                "instance-identifier",
                "instance-identifier: value must be a path expression (e.g. /top/leaf)",
            )
        ]
    if not expr.is_absolute:
        return [
            _issue(
                "instance-identifier",
                "instance-identifier: only absolute paths are supported " "(path must start with '/')",
            )
        ]
    nodes = evaluator.eval(expr, ctx, ctx.root)
    if not nodes:
        return [
            _issue(
                "instance-identifier",
                f"instance-identifier: no instance at path {value_repr!r} " "(require-instance is true)",
            )
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


def _type_has_restrictions(type_stmt: YangTypeStmt) -> bool:
    """True when this ``type`` statement adds range, length, or pattern restrictions."""
    if type_stmt.range or type_stmt.length:
        return True
    return bool(type_stmt.patterns)


_INTEGER_TYPE_NAMES = frozenset(
    {
        "int8",
        "int16",
        "int32",
        "int64",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
        "integer",
    }
)
_DECIMAL_TYPE_NAMES = frozenset({"decimal64", "number"})
_STRING_TYPE_NAMES = frozenset(
    {
        "string",
        "entity-name",
        "field-name",
        "identifier",
        "date",
        "date-and-time",
        "qualified-source",
    }
)


class TypeChecker:
    """
    Checks a data value against a YangTypeStmt.
    Returns ``(code, message)`` pairs (empty = valid).
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
    ) -> List[TypeIssue]:
        """
        leafref_current: node to use as current() for leafref path resolution (typically
        the parent of the leaf). If None, ctx.current is used.
        """
        name = type_stmt.name

        if type_stmt.prefix:
            if not isinstance(root_schema, YangModule):
                return []
            ext = root_schema.resolve_prefixed_module(type_stmt.prefix)
            if ext is None:
                return [_issue("type", f"unknown type prefix {type_stmt.prefix!r} in type {name!r}")]
            typedef = ext.get_typedef(name)
            if typedef is not None and typedef.type is not None:
                return self._check_typedef_reference(
                    value,
                    type_stmt,
                    typedef.type,
                    path,
                    root_data,
                    root_schema,
                    ctx,
                    evaluator,
                    leafref_current,
                )
            return [_issue("type", f"unknown typedef {name!r} in imported module {type_stmt.prefix!r}")]

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
            return self._check_instance_identifier(value, type_stmt, ctx, evaluator)
        if name == "leafref":
            return self._check_leafref(
                value,
                type_stmt,
                path,
                ctx=ctx,
                evaluator=evaluator,
                leafref_current=leafref_current,
            )
        if name in _STRING_TYPE_NAMES:
            return self._check_string(value, type_stmt)
        # version-string and other typedefs: resolve via get_typedef so pattern/constraints apply
        if name in _INTEGER_TYPE_NAMES:
            return self._check_integer(value, type_stmt)
        if name in _DECIMAL_TYPE_NAMES:
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
                return self._check_typedef_reference(
                    value,
                    type_stmt,
                    typedef.type,
                    path,
                    root_data,
                    root_schema,
                    ctx,
                    evaluator,
                    leafref_current,
                )
        return []

    def _check_typedef_reference(
        self,
        value: Any,
        type_stmt: YangTypeStmt,
        typedef_type: YangTypeStmt,
        path: str,
        root_data: Any,
        root_schema: Any,
        ctx: Context,
        evaluator: Any,
        leafref_current: Optional[Node],
    ) -> List[TypeIssue]:
        """Validate the typedef chain, then restrictions on the referring ``type``.

        Each level checks its own ``range`` / ``length`` / ``pattern`` after the
        base type accepts the value (RFC 7950 §9.2.4).
        """
        errors = self.check(
            value,
            typedef_type,
            path,
            root_data,
            root_schema,
            ctx,
            evaluator,
            leafref_current,
        )
        if errors or not _type_has_restrictions(type_stmt):
            return errors
        return self._check_restrictions_on_builtin(value, type_stmt, root_schema)

    def _builtin_name(self, type_stmt: YangTypeStmt, root_schema: Any) -> str:
        """Follow ``type_stmt`` through typedefs to the underlying built-in name."""
        seen: set[tuple[Optional[str], str]] = set()
        current: Optional[YangTypeStmt] = type_stmt
        schema: Any = root_schema
        for _ in range(64):
            if current is None:
                return ""
            name = current.name
            prefix = current.prefix
            key = (prefix, name)
            if key in seen:
                return name
            seen.add(key)
            lookup_schema = schema
            if prefix:
                if not isinstance(schema, YangModule):
                    return name
                lookup_schema = schema.resolve_prefixed_module(prefix)
                if lookup_schema is None:
                    return name
            getter = getattr(lookup_schema, "get_typedef", None)
            typedef = getter(name) if callable(getter) else None
            if typedef is None or typedef.type is None:
                return name
            schema = lookup_schema
            current = typedef.type
        return current.name if current is not None else ""

    def _check_restrictions_on_builtin(
        self,
        value: Any,
        type_stmt: YangTypeStmt,
        root_schema: Any,
    ) -> List[TypeIssue]:
        """Apply ``type_stmt`` restrictions using the chain's built-in checker."""
        builtin = self._builtin_name(type_stmt, root_schema)
        if builtin in _INTEGER_TYPE_NAMES:
            return self._check_integer(value, type_stmt)
        if builtin in _DECIMAL_TYPE_NAMES:
            return self._check_decimal(value, type_stmt)
        if builtin == "binary":
            return self._check_binary(value, type_stmt)
        if builtin in _STRING_TYPE_NAMES:
            return self._check_string(value, type_stmt)
        return []

    def _check_identityref(self, value: Any, type_stmt: YangTypeStmt, root_schema: Any) -> List[TypeIssue]:
        if not isinstance(value, str):
            return [_issue("identityref", f"identityref value must be a string, got {type(value).__name__}")]
        if not isinstance(root_schema, YangModule):
            return [_issue("identityref", "identityref validation requires module schema")]
        bases = getattr(type_stmt, "identityref_bases", None) or []
        if not bases:
            return [_issue("identityref", "identityref type has no base identities")]
        if resolve_identity_qname_pair(root_schema, value) is None:
            return [_issue("identityref", f"identityref value {value!r} does not resolve to a known identity")]
        if not identityref_value_valid(root_schema, value, bases):
            bases_fmt = [format_identifier_ref(b) for b in bases]
            return [
                _issue(
                    "identityref",
                    f"identityref value {value!r} is not derived from all bases {bases_fmt!r}",
                )
            ]
        return []

    def _check_instance_identifier(
        self,
        value: Any,
        type_stmt: YangTypeStmt,
        ctx: Context,
        evaluator: Any,
    ) -> List[TypeIssue]:
        """RFC 7950 instance-identifier: string path; optional require-instance existence check."""
        if not isinstance(value, str):
            return [
                _issue(
                    "instance-identifier",
                    f"instance-identifier value must be a string, got {type(value).__name__}",
                )
            ]
        if not getattr(type_stmt, "require_instance", True):
            return []
        s = value.strip()
        if not s:
            return [
                _issue(
                    "instance-identifier",
                    "instance-identifier path must not be empty when require-instance is true",
                )
            ]
        try:
            parsed = XPathParser(s).parse()
        except XPathSyntaxError as e:
            return [_issue("instance-identifier", f"instance-identifier: invalid path expression ({e})")]
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
    ) -> List[TypeIssue]:
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
        return [_issue("union", f"Value {value!r} does not match any union member type ({names})")]

    def _check_leafref(
        self,
        value: Any,
        type_stmt: YangTypeStmt,
        node_path: str,
        ctx: Context,
        evaluator: Any,
        leafref_current: Optional[Node] = None,
    ) -> List[TypeIssue]:
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
                return [_issue("leafref", f"Leafref relative path {path_str!r} requires context node")]
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
                _issue(
                    "leafref",
                    f"Leafref value {value!r} not found via path {path_str!r} " "(require-instance is true)",
                )
            ]
        return []

    def _check_string(self, value: Any, type_stmt: YangTypeStmt) -> List[TypeIssue]:
        if not isinstance(value, str):
            return [_issue("type", f"Expected string, got {_json_type_name(value)}")]
        errors: List[TypeIssue] = []
        s = value
        if type_stmt.length:
            issue = self._length_issue(len(s), type_stmt.length, binary=False)
            if issue is not None:
                errors.append(issue)
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
                    errors.append(_issue("pattern", _pattern_entry_violation_message(p, default=default_msg)))
        if type_stmt.enums:
            if s not in [str(e) for e in type_stmt.enums]:
                errors.append(
                    _issue(
                        "enum",
                        f"Value {s!r} is not one of: " f"{', '.join(str(e) for e in type_stmt.enums)}",
                    )
                )
        return errors

    def _check_integer(self, value: Any, type_stmt: YangTypeStmt) -> List[TypeIssue]:
        # bool is a subclass of int; int(True) is 1 and must not pass as an integer.
        # A non-integral float (1.5) must not be truncated by int().
        # Numeric strings stay accepted here (see #63); this check does not add a lenient mode.
        if isinstance(value, bool):
            return [_issue("type", f"Expected integer, got {_json_type_name(value)}")]
        if isinstance(value, int):
            n = value
        elif isinstance(value, float):
            if not value.is_integer():
                return [_issue("type", f"Expected integer, got {_json_type_name(value)}")]
            try:
                n = int(value)
            except (OverflowError, ValueError):
                return [_issue("type", f"Expected integer, got {_json_type_name(value)}")]
        else:
            try:
                n = int(value)
            except (TypeError, ValueError):
                return [_issue("type", f"Expected integer, got {_json_type_name(value)}")]
        if type_stmt.range:
            issue = self._numeric_range_issue(n, type_stmt.range)
            if issue is not None:
                return [issue]
        bounds = YANG_INTEGER_BOUNDS.get(type_stmt.name or "")
        if bounds:
            lo, hi = bounds
            if n < lo:
                return [_issue("range", f"Value {n} is less than minimum {lo}")]
            if n > hi:
                return [_issue("range", f"Value {n} exceeds maximum {hi}")]
        return []

    def _check_decimal(self, value: Any, type_stmt: YangTypeStmt) -> List[TypeIssue]:
        # bool is a subclass of int; float(True) is 1.0 and must not pass as a number.
        if isinstance(value, bool):
            return [_issue("type", f"Expected number, got {_json_type_name(value)}")]
        try:
            n = float(value)
        except (TypeError, ValueError):
            return [_issue("type", f"Value {value!r} is not a valid number")]
        if type_stmt.range:
            issue = self._numeric_range_issue(n, type_stmt.range)
            if issue is not None:
                return [issue]
        fd = getattr(type_stmt, "fraction_digits", None)
        if fd is not None and fd >= 0:
            s = str(value).strip()
            if "." in s:
                frac = s.split(".", 1)[1]
                if len(frac) > int(fd):
                    return [
                        _issue(
                            "fraction-digits",
                            f"Value has more than {fd} fraction digits (decimal64 fraction-digits)",
                        )
                    ]
        return []

    def _check_boolean(self, value: Any) -> List[TypeIssue]:
        if value not in (True, False, "true", "false"):
            return [_issue("type", f"Value {value!r} is not a valid boolean (expected true or false)")]
        return []

    def _check_enum(self, value: Any, type_stmt: YangTypeStmt) -> List[TypeIssue]:
        if not type_stmt.enums:
            return [
                _issue(
                    "enum",
                    "enumeration type has no enum definitions in schema; cannot validate instance data",
                )
            ]
        allowed = [str(e) for e in type_stmt.enums]
        if str(value) not in allowed:
            return [
                _issue(
                    "enum",
                    f"Value {value!r} is not one of the allowed enum values: " f"{', '.join(allowed)}",
                )
            ]
        return []

    def _check_bits(self, value: Any, type_stmt: YangTypeStmt) -> List[TypeIssue]:
        """RFC 7950 bits: instance is a space-separated list of bit names (JSON: string)."""
        if not isinstance(value, str):
            return [
                _issue(
                    "bits",
                    f"bits value must be a string (space-sep bit names), got {type(value).__name__}",
                )
            ]
        bits = type_stmt.bits or []
        allowed = {b.name for b in bits}
        if not allowed:
            return [_issue("bits", "bits type has no bit definitions")]
        parts = [p for p in (s.strip() for s in value.split()) if p]
        seen: set[str] = set()
        for token in parts:
            if token in seen:
                return [_issue("bits", f"Duplicate bit {token!r} in bits value")]
            seen.add(token)
            if token not in allowed:
                return [_issue("bits", f"Unknown bit {token!r}; allowed: {', '.join(sorted(allowed))}")]
        return []

    def _check_empty(self, value: Any) -> List[TypeIssue]:
        # RFC 7951 empty is null. ``[null]`` is rewritten to null before this check.
        if value is not None:
            return [_issue("type", f"Empty type leaf should have no value, got {value!r}")]
        return []

    def _check_binary(self, value: Any, type_stmt: YangTypeStmt) -> List[TypeIssue]:
        """RFC 7950 binary: base64 in JSON; ``length`` applies to decoded octet count."""
        if not isinstance(value, str):
            return [
                _issue(
                    "type",
                    f"binary value must be a base64-encoded string, got {type(value).__name__}",
                )
            ]
        s = value.strip()
        try:
            if not s:
                decoded = b""
            else:
                decoded = base64.b64decode(s, validate=True)
        except binascii.Error:
            return [_issue("type", "binary value is not valid base64")]
        if type_stmt.length:
            issue = self._length_issue(len(decoded), type_stmt.length, binary=True)
            if issue is not None:
                return [issue]
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
                return [_issue("pattern", _pattern_entry_violation_message(p, default=default_msg))]
        return []

    def _parse_ranges(self, text: str) -> list[tuple[Optional[float], Optional[float]]]:
        """Split a YANG range or length on ``|``, then each part on ``..``.

        ``min`` / ``max`` are open ends (``None``). A single value ``n`` is ``(n, n)``.
        """
        bands: list[tuple[Optional[float], Optional[float]]] = []
        for raw in text.split("|"):
            part = raw.strip()
            if not part:
                continue
            if ".." in part:
                lo_s, hi_s = part.split("..", 1)
                lo_s = lo_s.strip()
                hi_s = hi_s.strip()
                lo = None if lo_s == "min" else self._to_num(lo_s)
                hi = None if hi_s == "max" else self._to_num(hi_s)
                bands.append((lo, hi))
            else:
                n = self._to_num(part)
                bands.append((n, n))
        return bands

    def _range_miss(
        self,
        n: float,
        bands: list[tuple[Optional[float], Optional[float]]],
    ) -> Optional[tuple[str, float]]:
        """When ``n`` misses every band, ``('min', lo)`` or ``('max', hi)``.

        Below the first band's lower bound is a minimum violation. Any other miss
        is reported against the greatest upper bound the value exceeds.
        """
        if not bands:
            return None
        for lo, hi in bands:
            if (lo is None or n >= lo) and (hi is None or n <= hi):
                return None
        first_lo = bands[0][0]
        if first_lo is not None and n < first_lo:
            return ("min", first_lo)
        exceeded = [hi for _lo, hi in bands if hi is not None and n > hi]
        if exceeded:
            return ("max", max(exceeded))
        for _lo, hi in bands:
            if hi is not None:
                return ("max", hi)
        return ("max", n)

    def _numeric_range_issue(self, n: float, text: str) -> Optional[TypeIssue]:
        miss = self._range_miss(n, self._parse_ranges(text))
        if miss is None:
            return None
        kind, bound = miss
        if kind == "min":
            return _issue("range", f"Value {n} is less than minimum {bound}")
        return _issue("range", f"Value {n} exceeds maximum {bound}")

    def _length_issue(self, n: int, text: str, *, binary: bool) -> Optional[TypeIssue]:
        miss = self._range_miss(n, self._parse_ranges(text))
        if miss is None:
            return None
        kind, bound = miss
        if binary:
            shown = int(bound)
            if kind == "min":
                return _issue("length", f"binary decoded length {n} octets is less than minimum {shown}")
            return _issue("length", f"binary decoded length {n} octets exceeds maximum {shown}")
        if kind == "min":
            return _issue("length", f"String length {n} is less than minimum {bound}")
        return _issue("length", f"String length {n} exceeds maximum {bound}")

    def _to_num(self, s: str) -> Optional[float]:
        try:
            return int(s)
        except ValueError:
            try:
                return float(s)
            except ValueError:
                return None
