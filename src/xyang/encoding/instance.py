"""Walk instance JSON as written and yield one node per schema instance node.

The input document is never modified. RFC 7951 is the default; native JSON is
opt-in (``native_json=True``). ``DocumentValidator`` consumes these nodes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator, Optional

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
    YangOutputStmt,
    YangRpcStmt,
    YangStatement,
    YangTypeStmt,
)
from ..module import YangModule
from ..types.registry import (
    DECIMAL_TYPE_NAMES,
    EMPTY,
    INTEGER_TYPE_NAMES,
    NUMBER_INTEGER_NAMES,
    QUOTED_INTEGER_NAMES,
    REGISTRY,
    STRINGISH_NAMES,
)
from ..validator.type_checker import TypeChecker
from ..xpath.evaluator import XPathEvaluator
from ..xpath.node import Context, Node
from .rfc7951 import defining_module_name, member_keys_cached

_INT64 = QUOTED_INTEGER_NAMES
_DECIMAL = DECIMAL_TYPE_NAMES
_STRINGISH = STRINGISH_NAMES
_SMALL_INT = NUMBER_INTEGER_NAMES | {"integer"}
_INTEGER_KEY = INTEGER_TYPE_NAMES
_ENCODED = _INT64 | _DECIMAL | frozenset({EMPTY})
_BUILTINS = frozenset(REGISTRY) | {"number", "integer"}
_INT_TEXT = re.compile(r"-?\d+")
_DEC_TEXT = re.compile(r"-?\d+(\.\d+)?")
_NO = object()
_DATA_STMTS = (YangLeafStmt, YangLeafListStmt, YangListStmt, YangContainerStmt, YangAnydataStmt, YangAnyxmlStmt)
_checker = TypeChecker()
_evaluator = XPathEvaluator()


@dataclass
class InstanceNode:
    """One instance node. ``value`` is the decoded scalar (containers and lists use ``None``)."""

    stmt: Any
    value: Any
    pointer: str
    children: list["InstanceNode"] = field(default_factory=list)
    kind: str = ""
    errors: list[tuple[str, str]] = field(default_factory=list)
    include: bool = True
    input_key: str = ""


def _token(token: str) -> str:
    if "~" in token or "/" in token:
        return token.replace("~", "~0").replace("/", "~1")
    return token


def _join(prefix: str, token: str) -> str:
    return f"{prefix}/{_token(token)}"


def _parent_module(module: YangModule, schema: Any) -> str:
    if isinstance(schema, YangModule):
        return schema.name or module.name or ""
    return ""


def _member_key(stmt: YangStatement, parent_module: str) -> str:
    keys = member_keys_cached(stmt, parent_module)
    return next(iter(keys)) if keys else (stmt.name or "")


def _data_nodes(schema: Any) -> list[YangStatement]:
    out: list[YangStatement] = []
    if isinstance(schema, YangChoiceStmt):
        seen: set[int] = set()
        cases = list(schema.cases)
        cases.extend(s for s in schema.statements if isinstance(s, YangCaseStmt))
        for case in cases:
            if id(case) in seen:
                continue
            seen.add(id(case))
            out.extend(_data_nodes(case))
        return out
    for stmt in getattr(schema, "statements", []) or []:
        if isinstance(stmt, (YangRpcStmt, YangInputStmt, YangOutputStmt)):
            continue
        if isinstance(stmt, YangChoiceStmt):
            out.extend(_data_nodes(stmt))
            continue
        if isinstance(stmt, YangCaseStmt):
            out.extend(_data_nodes(stmt))
            continue
        if isinstance(stmt, _DATA_STMTS):
            out.append(stmt)
    return out


def _unwrap(type_stmt: Optional[YangTypeStmt], module: Optional[YangModule], seen: Optional[set] = None):
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
        return not _checker.check(value, type_stmt, "", None, module, ctx, _evaluator)
    except Exception:
        return False


def _is_int_text(value: Any) -> bool:
    return isinstance(value, str) and _INT_TEXT.fullmatch(value.strip()) is not None


def _is_dec_text(value: Any) -> bool:
    return isinstance(value, str) and _DEC_TEXT.fullmatch(value.strip()) is not None


def _native_number(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _NO
    if isinstance(value, float):
        if not value.is_integer():
            return value
        try:
            return int(value)
        except (OverflowError, ValueError):
            return _NO
    return value


def _hint(native: bool, kind: str) -> str:
    if native:
        return f"{kind} is a JSON number in native mode; the default is RFC 7951"
    return f"{kind} is a string in RFC 7951; pass --native-json for a JSON number"


def _key_names(stmt: YangListStmt) -> list[str]:
    return [part.strip() for part in stmt.key.split()] if stmt.key else []


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, Decimal) or isinstance(right, Decimal):
        try:
            return Decimal(str(left)) == Decimal(str(right))
        except (InvalidOperation, ValueError):
            return False
    return left == right


class _Walk:
    """One iteration over a document. Caches are keyed by schema object id and live for one walk."""

    def __init__(self, module: YangModule, parent_module: str, native: bool) -> None:
        self.module = module
        self.parent_module = parent_module
        self.native = native
        self._nodes: dict[int, list[YangStatement]] = {}
        self._resolved: dict[tuple[int, str, bool], list[YangStatement]] = {}
        self._unwrapped: dict[int, Any] = {}

    def data_nodes(self, schema: Any) -> list[YangStatement]:
        found = self._nodes.get(id(schema))
        if found is None:
            found = _data_nodes(schema)
            self._nodes[id(schema)] = found
        return found

    def unwrap(self, type_stmt: Optional[YangTypeStmt]) -> Any:
        if type_stmt is None:
            return None
        key = id(type_stmt)
        if key in self._unwrapped:
            return self._unwrapped[key]
        eff = _unwrap(type_stmt, self.module)
        self._unwrapped[key] = eff
        return eff

    def resolve(self, key: str, schema: Any, at_root: bool) -> list[YangStatement]:
        cache_key = (id(schema), key, at_root)
        hits = self._resolved.get(cache_key)
        if hits is None:
            hits = self._resolve(key, self.data_nodes(schema), at_root)
            self._resolved[cache_key] = hits
        return hits

    def _resolve(self, key: str, children: list[YangStatement], at_root: bool) -> list[YangStatement]:
        parent_module = self.parent_module
        if self.native:
            if ":" in key:
                module_name, _, local = key.partition(":")
                if not module_name or not local:
                    return []
                return [
                    child
                    for child in children
                    if child.name == local and defining_module_name(child, parent_module) == module_name
                ]
            return [child for child in children if child.name == key]
        hits = [child for child in children if key in member_keys_cached(child, parent_module)]
        if hits or not at_root or ":" not in key:
            return hits
        module_name, _, local = key.partition(":")
        if not module_name or not local:
            return []
        return [
            child
            for child in children
            if child.name == local and defining_module_name(child, parent_module) == module_name
        ]

    def decode(self, value: Any, type_stmt: YangTypeStmt) -> Any:
        """Return the decoded value, or ``_NO`` when this JSON type is not that member's encoding."""
        eff = self.unwrap(type_stmt)
        if eff is None:
            return value
        native = self.native
        name = eff.name
        if name == "union":
            module = self.module
            for member in eff.types or []:
                decoded = self.decode(value, member)
                if decoded is _NO:
                    continue
                if _accepts(decoded, member, module):
                    return decoded
            return value
        if name == "empty":
            if native and value is None:
                return None
            if not native and isinstance(value, list) and len(value) == 1 and value[0] is None:
                return None
            if (native and isinstance(value, list) and value == [None]) or (not native and value is None):
                return _NO
            return value
        if name in _INT64:
            if native:
                number = _native_number(value)
                return number if isinstance(number, int) else _NO
            if _is_int_text(value):
                return int(value.strip())
            return _NO
        if name in _DECIMAL:
            if native:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    return _NO
                if isinstance(value, float):
                    return Decimal(repr(value))
                return Decimal(value)
            if _is_dec_text(value):
                try:
                    return Decimal(value.strip())
                except InvalidOperation:
                    return _NO
            return _NO
        if name == "leafref" or name in _STRINGISH:
            return value
        if name == "boolean":
            if isinstance(value, bool) or value in ("true", "false"):
                return value
            return _NO
        return value

    def walk_object(self, data: dict, schema: Any, prefix: str, at_root: bool) -> list[InstanceNode]:
        nodes: list[InstanceNode] = []
        claimed: set[int] = set()
        for key, raw in data.items():
            if not isinstance(key, str):
                continue
            here = _join(prefix, key)
            hits = self.resolve(key, schema, at_root)
            if len(hits) == 0:
                nodes.append(InstanceNode(stmt=None, value=raw, pointer=here, kind="unknown", input_key=key))
                continue
            if len(hits) > 1:
                nodes.append(
                    InstanceNode(
                        stmt=None,
                        value=None,
                        pointer=here,
                        kind="ambiguous",
                        errors=[("ambiguous-name", f"member name '{key}' matches more than one node")],
                        include=False,
                    )
                )
                continue
            stmt = hits[0]
            if id(stmt) in claimed:
                continue
            claimed.add(id(stmt))
            nodes.append(self.walk_node(raw, stmt, here))
        return nodes

    def walk_node(self, raw: Any, stmt: YangStatement, pointer: str) -> InstanceNode:
        if isinstance(stmt, YangLeafStmt):
            return self.walk_leaf(raw, stmt, pointer)
        if isinstance(stmt, (YangAnydataStmt, YangAnyxmlStmt)):
            return InstanceNode(stmt=stmt, value=raw, pointer=pointer, kind="anydata")
        if isinstance(stmt, YangContainerStmt):
            if not isinstance(raw, dict):
                return InstanceNode(
                    stmt=stmt,
                    value=None,
                    pointer=pointer,
                    kind="container",
                    errors=[("type", "container must be an object")],
                    include=False,
                )
            return InstanceNode(
                stmt=stmt,
                value=None,
                pointer=pointer,
                kind="container",
                children=self.walk_object(raw, stmt, pointer, False),
            )
        if isinstance(stmt, YangListStmt):
            return self.walk_list(raw, stmt, pointer)
        if isinstance(stmt, YangLeafListStmt):
            return self.walk_leaf_list(raw, stmt, pointer)
        return InstanceNode(stmt=stmt, value=raw, pointer=pointer, kind="opaque")

    def walk_leaf(self, raw: Any, stmt: Any, pointer: str) -> InstanceNode:
        type_stmt = stmt.type
        if type_stmt is None:
            return InstanceNode(stmt=stmt, value=raw, pointer=pointer, kind="leaf")
        eff = self.unwrap(type_stmt)
        decoded = self.decode(raw, type_stmt)
        if decoded is _NO and eff is not None and eff.name in _ENCODED:
            if eff.name == "empty":
                message = (
                    "empty is null in native mode; RFC 7951 encodes empty as [null]"
                    if self.native
                    else "empty is [null] in RFC 7951; pass --native-json for null"
                )
            else:
                message = _hint(self.native, eff.name)
            return InstanceNode(
                stmt=stmt,
                value=None,
                pointer=pointer,
                kind="leaf",
                errors=[("type", message)],
                include=False,
            )
        if decoded is _NO:
            decoded = raw
        return InstanceNode(stmt=stmt, value=decoded, pointer=pointer, kind="leaf")

    def walk_leaf_list(self, raw: Any, stmt: YangLeafListStmt, pointer: str) -> InstanceNode:
        if not isinstance(raw, list):
            return InstanceNode(
                stmt=stmt,
                value=None,
                pointer=pointer,
                kind="leaf-list",
                errors=[("type", "leaf-list must be an array")],
                include=False,
            )
        items: list[InstanceNode] = []
        for index, item in enumerate(raw):
            child = self.walk_leaf(item, stmt, f"{pointer}/{index}")
            child.kind = "leaf-list-item"
            items.append(child)
        return InstanceNode(stmt=stmt, value=None, pointer=pointer, kind="leaf-list", children=items)

    def convert_key(self, text: str, leaf: YangLeafStmt) -> Any:
        if leaf.type is None:
            return text
        decoded = self.decode(text if not self.native else self.key_as_native(text, leaf), leaf.type)
        if decoded is _NO:
            # Dict keys are strings. In native mode a string key converts to the key type.
            eff = self.unwrap(leaf.type)
            if eff is not None and eff.name in _INTEGER_KEY:
                if _INT_TEXT.fullmatch(text):
                    return int(text)
            if eff is not None and eff.name in _DECIMAL and _is_dec_text(text):
                return Decimal(text)
            if eff is not None and eff.name == "boolean" and text in ("true", "false"):
                return text == "true"
            if eff is not None and eff.name in _STRINGISH:
                return text
            return _NO
        return decoded

    def key_as_native(self, text: str, leaf: YangLeafStmt) -> Any:
        eff = self.unwrap(leaf.type) if leaf.type else None
        if eff is not None and eff.name in _INTEGER_KEY:
            if _INT_TEXT.fullmatch(text):
                return int(text)
            return text
        if eff is not None and eff.name in _DECIMAL and _is_dec_text(text):
            if "." in text:
                return float(text)
            return int(text)
        if eff is not None and eff.name == "boolean" and text in ("true", "false"):
            return text == "true"
        return text

    def find_named(self, schema: YangStatement, name: str) -> Optional[YangStatement]:
        for child in self.data_nodes(schema):
            if child.name == name:
                return child
        return None

    def walk_list(self, raw: Any, stmt: YangListStmt, pointer: str) -> InstanceNode:
        native = self.native
        keys = _key_names(stmt)
        entries: list[tuple[str, Any]] = []
        errors: list[tuple[str, str]] = []
        if isinstance(raw, list):
            entries = [(str(index), item) for index, item in enumerate(raw)]
            keyed = False
        elif (
            native and isinstance(raw, dict) and len(keys) == 1 and all(isinstance(item, dict) for item in raw.values())
        ):
            entries = list(raw.items())
            keyed = True
        elif native and isinstance(raw, dict) and len(keys) != 1:
            return InstanceNode(
                stmt=stmt,
                value=None,
                pointer=pointer,
                kind="list",
                errors=[("list-encoding", "a list with more than one key must be a JSON array (--native-json)")],
                include=False,
            )
        else:
            return InstanceNode(
                stmt=stmt,
                value=None,
                pointer=pointer,
                kind="list",
                errors=[
                    ("type", "list must be an array" if not native else "list must be an array or a single-key object")
                ],
                include=False,
            )
        children: list[InstanceNode] = []
        key_leaf = self.find_named(stmt, keys[0]) if len(keys) == 1 else None
        for token, item in entries:
            entry_pointer = _join(pointer, token)
            if not isinstance(item, dict):
                children.append(
                    InstanceNode(
                        stmt=stmt,
                        value=None,
                        pointer=entry_pointer,
                        kind="entry",
                        errors=[("type", "list item must be an object")],
                        include=False,
                    )
                )
                continue
            body = self.walk_object(item, stmt, entry_pointer, False)
            if keyed and isinstance(key_leaf, YangLeafStmt):
                converted = self.convert_key(str(token), key_leaf)
                key_token = key_leaf.name or keys[0]
                present = next((child for child in body if child.stmt is key_leaf and child.include), None)
                key_pointer = _join(entry_pointer, key_token) if present is None else present.pointer
                if converted is _NO:
                    errors.append(("type", f"dict key '{token}' cannot be converted to the key type"))
                elif present is None:
                    body.insert(
                        0,
                        InstanceNode(stmt=key_leaf, value=converted, pointer=key_pointer, kind="leaf"),
                    )
                elif not _same(present.value, converted):
                    present.errors.append(("key-mismatch", f"key leaf does not match dict key '{token}'"))
            children.append(InstanceNode(stmt=stmt, value=None, pointer=entry_pointer, kind="entry", children=body))
        return InstanceNode(stmt=stmt, value=None, pointer=pointer, kind="list", children=children, errors=errors)


def iter_instance(
    data: Any,
    module: YangModule,
    *,
    native_json: bool = False,
    schema: Any = None,
) -> Iterator[InstanceNode]:
    """Yield a node for each top-level instance node in ``data`` as written."""
    if not isinstance(data, dict):
        return
        yield  # pragma: no cover
    root = module if schema is None else schema
    walk = _Walk(module, _parent_module(module, root), native_json)
    yield from walk.walk_object(data, root, "", True)


def encoding_errors(nodes: list[InstanceNode]) -> list[tuple[str, str, str]]:
    """``(pointer, code, message)`` for encoding failures on ``nodes``."""
    found: list[tuple[str, str, str]] = []

    def walk(node: InstanceNode) -> None:
        for code, message in node.errors:
            found.append((node.pointer, code, message))
        for child in node.children:
            walk(child)

    for node in nodes:
        walk(node)
    return found


def project_instance(nodes: list[InstanceNode], parent_module: str) -> tuple[dict, dict[str, str]]:
    """Canonical tree the existing walker understands, plus input-pointer map.

    The caller's JSON is not used or modified. Pointers in the map address it.
    """
    mapping: dict[str, str] = {}
    member_keys: dict[int, str] = {}
    return _project_level(nodes, parent_module, "", mapping, member_keys), mapping


def _project_level(
    nodes: list[InstanceNode],
    parent_module: str,
    prefix: str,
    mapping: dict[str, str],
    member_keys: dict[int, str],
) -> dict:
    out: dict[str, Any] = {}
    for node in nodes:
        if node.kind == "unknown":
            out[node.input_key] = node.value
            continue
        if not node.include or node.stmt is None:
            continue
        key = member_keys.get(id(node.stmt))
        if key is None:
            key = _member_key(node.stmt, parent_module)
            member_keys[id(node.stmt)] = key
        canon = _join(prefix, key)
        mapping[canon] = node.pointer
        kind = node.kind
        if kind == "leaf" or kind == "anydata":
            out[key] = node.value
        elif kind == "container":
            out[key] = _project_level(node.children, parent_module, canon, mapping, member_keys)
        elif kind == "list":
            rows = []
            for index, entry in enumerate(child for child in node.children if child.include):
                entry_canon = f"{canon}/{index}"
                mapping[entry_canon] = entry.pointer
                rows.append(_project_level(entry.children, parent_module, entry_canon, mapping, member_keys))
            out[key] = rows
        elif kind == "leaf-list":
            values = []
            for index, item in enumerate(child for child in node.children if child.include):
                mapping[f"{canon}/{index}"] = item.pointer
                values.append(item.value)
            out[key] = values
    return out


def remap_pointer(pointer: str, mapping: dict[str, str]) -> str:
    """Rewrite a canonical walker pointer to the input pointer."""
    if not mapping or pointer in mapping:
        return mapping.get(pointer, pointer)
    parts = pointer.split("/")
    for index in range(len(parts), 1, -1):
        prefix = "/".join(parts[:index])
        if prefix in mapping:
            rest = "/".join(parts[index:])
            base = mapping[prefix]
            return f"{base}/{rest}" if rest else base
    return pointer


__all__ = [
    "InstanceNode",
    "encoding_errors",
    "iter_instance",
    "project_instance",
    "remap_pointer",
]
