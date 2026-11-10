"""Normalize RFC 7951 and dict-style instance JSON into one tree.

This is the only code that knows about either encoding. Validators see its
output: containers are objects, lists are arrays of objects with key leaves
filled in, member names follow ``instance_member_keys``, ``empty`` is
``null``, and ``int64`` / ``uint64`` / ``decimal64`` use one canonical value.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from ..ast import (
    YangAnydataStmt,
    YangAnyxmlStmt,
    YangCaseStmt,
    YangChoiceStmt,
    YangContainerStmt,
    YangInputStmt,
    YangLeafListStmt,
    YangLeafStmt,
    YangListStmt,
    YangNotificationStmt,
    YangOutputStmt,
    YangRpcStmt,
    YangStatement,
    YangTypeStmt,
)
from ..module import YangModule
from ..validator.type_checker import TypeChecker
from ..xpath.evaluator import XPathEvaluator
from ..xpath.node import Context, Node
from .rfc7951 import defining_module_name, instance_member_keys

_INT64 = frozenset({"int64", "uint64"})
_DECIMAL = frozenset({"decimal64", "number"})
_STRINGISH = frozenset(
    {
        "string",
        "enumeration",
        "bits",
        "binary",
        "identityref",
        "instance-identifier",
        "leafref",
    }
)
_INTEGER_KEY = frozenset({"int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64", "integer"})
_BUILTINS = (
    _INT64
    | _DECIMAL
    | _STRINGISH
    | _INTEGER_KEY
    | frozenset({"boolean", "empty", "union", "int8", "int16", "int32", "uint8", "uint16", "uint32"})
)

_checker = TypeChecker()
_evaluator = XPathEvaluator()


@dataclass
class NormalizationError:
    """An encoding error reported against the normalized tree."""

    pointer: str
    code: str
    message: str


class NormalizedInstance(dict):
    """Normalized document. ``normalization_errors`` are encoding failures."""

    def __init__(self, mapping: Optional[dict] = None) -> None:
        super().__init__(mapping or {})
        self.normalization_errors: list[NormalizationError] = []


def _pointer(tokens: list[str]) -> str:
    if not tokens:
        return ""
    escaped = [token.replace("~", "~0").replace("/", "~1") for token in tokens]
    return "/" + "/".join(escaped)


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, Decimal) or isinstance(right, Decimal):
        try:
            return Decimal(str(left)) == Decimal(str(right))
        except (InvalidOperation, ValueError):
            return False
    return left == right


def _canonical_key(stmt: YangStatement, parent_module: str) -> str:
    keys = instance_member_keys(stmt, parent_module)
    if not keys:
        return stmt.name or ""
    return next(iter(keys))


def _defining(stmt: YangStatement, parent_module: str) -> str:
    return defining_module_name(stmt, parent_module)


def _iter_data_nodes(schema: Any):
    """Data nodes directly under *schema*, with choice and case flattened."""
    if isinstance(schema, YangChoiceStmt):
        seen: set[int] = set()
        cases = list(schema.cases)
        cases.extend(s for s in schema.statements if isinstance(s, YangCaseStmt))
        for case in cases:
            if id(case) in seen:
                continue
            seen.add(id(case))
            yield from _iter_data_nodes(case)
        return
    for stmt in getattr(schema, "statements", []) or []:
        if isinstance(stmt, (YangNotificationStmt, YangRpcStmt, YangInputStmt, YangOutputStmt)):
            continue
        if isinstance(stmt, YangChoiceStmt):
            yield from _iter_data_nodes(stmt)
            continue
        if isinstance(stmt, YangCaseStmt):
            yield from _iter_data_nodes(stmt)
            continue
        if isinstance(
            stmt,
            (YangLeafStmt, YangLeafListStmt, YangListStmt, YangContainerStmt, YangAnydataStmt, YangAnyxmlStmt),
        ):
            yield stmt


def _resolve_name(key: str, children: list[YangStatement], parent_module: str) -> list[YangStatement]:
    if ":" in key:
        module_name, _, local = key.partition(":")
        if not module_name or not local:
            return []
        return [child for child in children if child.name == local and _defining(child, parent_module) == module_name]
    return [child for child in children if child.name == key]


def _unwrap(type_stmt: Optional[YangTypeStmt], module: Optional[YangModule], seen: Optional[set] = None):
    """Follow typedefs to a builtin or union. Prefixed typedefs resolve through imports."""
    if type_stmt is None:
        return None
    seen = set() if seen is None else seen
    marker = (id(module), type_stmt.prefix, type_stmt.name)
    if marker in seen:
        return type_stmt
    seen.add(marker)
    if type_stmt.name in _BUILTINS and not type_stmt.prefix:
        return type_stmt
    target = module
    if type_stmt.prefix:
        if module is None or not hasattr(module, "resolve_prefixed_module"):
            return type_stmt
        target = module.resolve_prefixed_module(type_stmt.prefix)
        if target is None:
            return type_stmt
    getter = getattr(target, "get_typedef", None)
    typedef = getter(type_stmt.name) if getter else None
    if typedef is not None and getattr(typedef, "type", None) is not None:
        return _unwrap(typedef.type, target, seen)
    return type_stmt


def _accepts(value: Any, type_stmt: YangTypeStmt, module: Optional[YangModule]) -> bool:
    node = Node(None, module, None)
    ctx = Context(current=node, root=node, path_cache={})
    try:
        issues = _checker.check(value, type_stmt, "", None, module, ctx, _evaluator)
    except Exception:
        return False
    return not issues


def _string_member_accepts(value: str, members: list[YangTypeStmt], module: Optional[YangModule]) -> bool:
    """True when a string-typed union member accepts *value* as written."""
    for member in members:
        eff = _unwrap(member, module)
        if eff is None:
            continue
        if eff.name == "union":
            if _string_member_accepts(value, eff.types, module):
                return True
            continue
        if eff.name in _STRINGISH and _accepts(value, member, module):
            return True
    return False


def _canon_int64(value: Any) -> Any:
    """int64/uint64 as one Python int, from a JSON number or an RFC 7951 string."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        try:
            return int(value)
        except (OverflowError, ValueError):
            return value
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value.strip())
    return value


def _canon_decimal(value: Any) -> Any:
    """decimal64 as an exact ``Decimal``. Floats use ``repr``, never binary float compare."""
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation:
            return value
    return value


def _normalize_union(value: Any, union_stmt: YangTypeStmt, module: Optional[YangModule]) -> Any:
    """Pick a union member from the JSON type.

    A string is the RFC 7951 form of int64/uint64/decimal64 only when no
    string-typed member accepts it. ``"5"`` in ``union { int64; string; }``
    stays the string ``"5"``.
    """
    members = list(union_stmt.types or [])
    if isinstance(value, str):
        if _string_member_accepts(value, members, module):
            return value
        text = value.strip()
        for member in members:
            eff = _unwrap(member, module)
            if eff is None:
                continue
            if eff.name == "union":
                nested = _normalize_union(value, eff, module)
                if nested != value or _string_member_accepts(value, eff.types, module):
                    return nested
                continue
            if eff.name in _INT64 and re.fullmatch(r"-?\d+", text) and _accepts(int(text), member, module):
                return int(text)
            if eff.name in _DECIMAL:
                try:
                    decimal = Decimal(text)
                except InvalidOperation:
                    continue
                if _accepts(decimal, member, module):
                    return decimal
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        for member in members:
            eff = _unwrap(member, module)
            if eff is None:
                continue
            if eff.name in _INT64 and _accepts(value, member, module):
                return _canon_int64(value)
            if eff.name in _DECIMAL and _accepts(value, member, module):
                return _canon_decimal(value)
            if eff.name == "union":
                nested = _normalize_union(value, eff, module)
                if _accepts(nested, member, module):
                    return nested
            elif _accepts(value, member, module):
                return value
        return value
    if isinstance(value, list) and len(value) == 1 and value[0] is None:
        for member in members:
            eff = _unwrap(member, module)
            if eff is not None and eff.name == "empty":
                return None
        return value
    return value


def _normalize_leaf(value: Any, type_stmt: Optional[YangTypeStmt], module: Optional[YangModule]) -> Any:
    eff = _unwrap(type_stmt, module)
    if eff is None:
        return value
    if eff.name == "empty":
        if isinstance(value, list) and len(value) == 1 and value[0] is None:
            return None
        return value
    if eff.name == "union":
        return _normalize_union(value, eff, module)
    if eff.name in _INT64:
        return _canon_int64(value)
    if eff.name in _DECIMAL:
        return _canon_decimal(value)
    return value


def _convert_key(text: str, leaf: YangLeafStmt, module: Optional[YangModule]) -> tuple[Any, bool]:
    """Convert a JSON object key (always a string) to the key leaf's type."""
    eff = _unwrap(leaf.type, module)
    if eff is None:
        return text, True
    if eff.name == "union":
        converted = _normalize_union(text, eff, module)
        return converted, True
    if eff.name == "boolean":
        if text == "true":
            return True, True
        if text == "false":
            return False, True
        return text, False
    if eff.name == "empty":
        return text, False
    if eff.name in _INTEGER_KEY:
        if re.fullmatch(r"-?\d+", text):
            return int(text), True
        return text, False
    if eff.name in _DECIMAL:
        try:
            return Decimal(text), True
        except InvalidOperation:
            return text, False
    return text, True


def _find_named(schema: YangStatement, name: str) -> Optional[YangStatement]:
    for child in _iter_data_nodes(schema):
        if child.name == name:
            return child
    return None


def _normalize_object(
    data: dict,
    schema: Any,
    module: Optional[YangModule],
    parent_module: str,
    tokens: list[str],
    errors: list[NormalizationError],
) -> dict:
    children = list(_iter_data_nodes(schema))
    out: dict[str, Any] = {}
    claimed: set[int] = set()
    for key, value in data.items():
        if not isinstance(key, str):
            out[str(key)] = copy.deepcopy(value)
            continue
        hits = _resolve_name(key, children, parent_module)
        if len(hits) == 0:
            out[key] = copy.deepcopy(value)
            continue
        if len(hits) > 1:
            errors.append(
                NormalizationError(
                    _pointer(tokens + [key]),
                    "ambiguous-name",
                    f"member name {key!r} matches more than one node",
                )
            )
            continue
        stmt = hits[0]
        if id(stmt) in claimed:
            continue
        claimed.add(id(stmt))
        canon = _canonical_key(stmt, parent_module)
        out[canon] = _normalize_node(value, stmt, module, parent_module, tokens + [canon], errors)
    return out


def _normalize_list(
    value: Any,
    stmt: YangListStmt,
    module: Optional[YangModule],
    parent_module: str,
    tokens: list[str],
    errors: list[NormalizationError],
) -> Any:
    key_names = [part.strip() for part in stmt.key.split()] if stmt.key else []
    if isinstance(value, list):
        entries = []
        for index, entry in enumerate(value):
            if isinstance(entry, dict):
                entries.append(_normalize_object(entry, stmt, module, parent_module, tokens + [str(index)], errors))
            else:
                entries.append(copy.deepcopy(entry))
        return entries
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    if len(key_names) != 1:
        errors.append(
            NormalizationError(
                _pointer(tokens),
                "list-encoding",
                "a list with more than one key must be a JSON array",
            )
        )
        return []
    if not all(isinstance(entry, dict) for entry in value.values()):
        # Keys are leaf names (or other non-entry values), not key values.
        return copy.deepcopy(value)
    key_leaf = _find_named(stmt, key_names[0])
    entries = []
    for index, (dict_key, entry) in enumerate(value.items()):
        entry_tokens = tokens + [str(index)]
        normalized = _normalize_object(entry, stmt, module, parent_module, entry_tokens, errors)
        if isinstance(key_leaf, YangLeafStmt):
            canon_name = _canonical_key(key_leaf, parent_module)
            converted, ok = _convert_key(str(dict_key), key_leaf, module)
            key_pointer = _pointer(entry_tokens + [canon_name])
            if not ok:
                errors.append(
                    NormalizationError(
                        key_pointer,
                        "type",
                        f"dict key {dict_key!r} cannot be converted to the key type",
                    )
                )
                normalized.setdefault(canon_name, str(dict_key))
            elif canon_name in normalized:
                if not _same(normalized[canon_name], converted):
                    errors.append(
                        NormalizationError(
                            key_pointer,
                            "key-mismatch",
                            f"key leaf does not match dict key {dict_key!r}",
                        )
                    )
                else:
                    normalized[canon_name] = converted
            else:
                normalized[canon_name] = converted
        entries.append(normalized)
    return entries


def _normalize_node(
    value: Any,
    stmt: YangStatement,
    module: Optional[YangModule],
    parent_module: str,
    tokens: list[str],
    errors: list[NormalizationError],
) -> Any:
    if isinstance(stmt, (YangAnydataStmt, YangAnyxmlStmt)):
        return copy.deepcopy(value)
    if isinstance(stmt, YangListStmt):
        return _normalize_list(value, stmt, module, parent_module, tokens, errors)
    if isinstance(stmt, YangContainerStmt):
        if not isinstance(value, dict):
            return copy.deepcopy(value)
        return _normalize_object(value, stmt, module, parent_module, tokens, errors)
    if isinstance(stmt, YangLeafListStmt):
        if not isinstance(value, list):
            return copy.deepcopy(value)
        return [_normalize_leaf(item, stmt.type, module) for item in value]
    if isinstance(stmt, YangLeafStmt):
        return _normalize_leaf(value, stmt.type, module)
    return copy.deepcopy(value)


def normalize_instance(data: Any, module: YangModule, schema: Any = None) -> dict:
    """Return *data* as the canonical instance tree for *module*.

    Encoding errors (``ambiguous-name``, ``key-mismatch``, ``list-encoding``,
    and key conversions that are not possible) are stored on the returned
    dict as ``normalization_errors`` when *data* is an object.
    """
    if not isinstance(data, dict):
        return data
    root = module if schema is None else schema
    parent_module = module.name if isinstance(root, YangModule) else ""
    errors: list[NormalizationError] = []
    tree = _normalize_object(data, root, module, parent_module, [], errors)
    wrapped = NormalizedInstance(tree)
    wrapped.normalization_errors = errors
    return wrapped


__all__ = ["NormalizationError", "NormalizedInstance", "normalize_instance"]
