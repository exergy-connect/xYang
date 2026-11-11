"""rpc and action input and output instances (RFC 7950 §7.14, §7.15, accessible tree §6.4.1).

The module and the caller's data are never modified. The accessible tree is built from
a shallow copy of the module. For an rpc, its top level holds the server data nodes plus
one operation node named after the rpc. For an action, the operation node is a child of
the container or list instance the action is invoked on; the statements on the way there
are copied so the module keeps its own. The operation node carries the ``input`` or
``output`` body as its children.

An action is named by the RFC 8040 §3.5.3 data resource identifier of its node, the path a
RESTCONF client POSTs to under ``{+restconf}/data``: ``/module:container/list=key1,key2/action``.
"""

from __future__ import annotations

import copy
import dataclasses
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import unquote

from ..ast import (
    YangActionStmt,
    YangCaseStmt,
    YangChoiceStmt,
    YangContainerStmt,
    YangInputStmt,
    YangListStmt,
    YangOutputStmt,
    YangRpcStmt,
    YangStatement,
)
from ..encoding.rfc7951 import defining_module_name
from ..module import YangModule

DIRECTIONS = ("input", "output")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")


@dataclass
class ParentStep:
    """One container or list on the way to an action's parent instance.

    ``wrappers`` are the ``choice`` / ``case`` statements between the previous data node and
    ``stmt``; ``keys`` are the decoded key values of a list instance.
    """

    stmt: YangStatement
    keys: Optional[tuple[str, ...]] = None
    wrappers: list[YangStatement] = field(default_factory=list)


@dataclass
class OperationTarget:
    """The rpc or action an instance belongs to and, for an action, its parent instance."""

    operation: YangRpcStmt
    module_name: str
    label: str
    parents: list[ParentStep] = field(default_factory=list)


def check_operation_options(rpc: Optional[str], action: Optional[str], direction: str, context: object) -> None:
    """Reject option combinations that make no sense; ``ValueError`` is a usage error."""
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be 'input' or 'output', got {direction!r}")
    if rpc is not None and action is not None:
        raise ValueError("rpc and action are mutually exclusive")
    if rpc is None and action is None:
        if direction != "input":
            raise ValueError("direction applies only together with rpc or action")
        if context is not None:
            raise ValueError("context applies only together with rpc or action")
    if rpc is not None and (not isinstance(rpc, str) or not rpc):
        raise ValueError("rpc must be a non-empty rpc name")
    if action is not None:
        if not isinstance(action, str) or not action:
            raise ValueError("action must be the data resource identifier of an action (RFC 8040 §3.5.3)")
        if context is None:
            raise ValueError(
                "action needs context: the instance it is invoked on must be in the server data (RFC 7950 §7.15)"
            )
    if context is not None and not isinstance(context, dict):
        raise ValueError("context must be a JSON object")


def find_rpc(module: YangModule, name: str) -> OperationTarget:
    for stmt in module.statements:
        if type(stmt) is YangRpcStmt and stmt.name == name:
            return OperationTarget(stmt, module.name, f"rpc '{name}'")
    known = sorted(s.name for s in module.statements if type(s) is YangRpcStmt and s.name)
    listing = ", ".join(known) if known else "none"
    raise ValueError(f"module '{module.name}' has no rpc '{name}' (rpcs: {listing})")


def _parse_api_path(text: str) -> list[tuple[Optional[str], str, Optional[tuple[str, ...]]]]:
    """``[(module, identifier, keys)]`` for an RFC 8040 §3.5.3 api-path."""
    if not text.startswith("/") or text == "/":
        raise ValueError(f"action {text!r} must be a data resource identifier such as /module:list=key/action")
    segments = []
    for raw in text[1:].split("/"):
        ident, has_keys, key_text = raw.partition("=")
        module_name, colon, name = ident.rpartition(":")
        if not colon:
            module_name, name = "", ident
        if (colon and not _IDENTIFIER.fullmatch(module_name)) or not _IDENTIFIER.fullmatch(name):
            raise ValueError(f"action {text!r}: {raw!r} is not an api-identifier (RFC 8040 §3.5.3)")
        keys = tuple(unquote(value) for value in key_text.split(",")) if has_keys else None
        segments.append((module_name or None, name, keys))
    if segments[0][0] is None:
        raise ValueError(f"action {text!r}: the first segment must be module-qualified (RFC 8040 §3.5.3)")
    return segments


def _find_data_child(
    parent: Any, name: str, module_name: str, host: str
) -> tuple[Optional[YangStatement], list[YangStatement]]:
    """Data-node child of ``parent`` named ``name`` in ``module_name``, through choice and case."""
    for stmt in getattr(parent, "statements", []) or []:
        if isinstance(stmt, YangRpcStmt):
            continue
        if isinstance(stmt, (YangChoiceStmt, YangCaseStmt)):
            branches = list(stmt.cases) if isinstance(stmt, YangChoiceStmt) else [stmt]
            if isinstance(stmt, YangChoiceStmt):
                branches += [s for s in stmt.statements if isinstance(s, YangCaseStmt) and s not in branches]
            for branch in branches:
                found, wrappers = _find_data_child(branch, name, module_name, host)
                if found is not None:
                    middle = [] if branch is stmt else [branch]
                    return found, [stmt, *middle, *wrappers]
            continue
        if stmt.name == name and defining_module_name(stmt, host) == module_name:
            return stmt, []
    return None, []


def resolve_action(module: YangModule, path: str) -> OperationTarget:
    """Resolve an action's data resource identifier; anything that does not name one is a usage error."""
    segments = _parse_api_path(path)
    if segments[0][0] != module.name:
        raise ValueError(f"action {path!r}: the first segment must be in module '{module.name}'")
    if len(segments) < 2:
        raise ValueError(f"action {path!r} names no container or list instance to invoke the action on")
    parents: list[ParentStep] = []
    schema: Any = module
    namespace = module.name
    for module_name, name, keys in segments[:-1]:
        namespace = module_name or namespace
        stmt, wrappers = _find_data_child(schema, name, namespace, module.name)
        where = "/" + "/".join(f"{s.stmt.name}" for s in parents)
        if stmt is None:
            raise ValueError(f"action {path!r}: no container or list '{namespace}:{name}' under {where}")
        if isinstance(stmt, YangListStmt):
            key_names = stmt.key.split() if stmt.key else []
            if keys is None or len(keys) != len(key_names):
                raise ValueError(
                    f"action {path!r}: list '{name}' needs its {len(key_names)} key value(s) "
                    f"({', '.join(key_names)}) as {name}=value (RFC 8040 §3.5.3)"
                )
        elif isinstance(stmt, YangContainerStmt):
            if keys is not None:
                raise ValueError(f"action {path!r}: container '{name}' takes no key values")
        else:
            raise ValueError(f"action {path!r}: '{name}' is not a container or list")
        parents.append(ParentStep(stmt, keys, wrappers))
        schema = stmt
    module_name, name, keys = segments[-1]
    namespace = module_name or namespace
    if keys is not None:
        raise ValueError(f"action {path!r}: the action segment takes no key values")
    for stmt in schema.statements:
        if (
            isinstance(stmt, YangActionStmt)
            and stmt.name == name
            and defining_module_name(stmt, module.name) == namespace
        ):
            return OperationTarget(stmt, namespace, f"action {path!r}", parents)
    known = sorted(s.name for s in schema.statements if isinstance(s, YangActionStmt) and s.name)
    raise ValueError(
        f"action {path!r}: '{schema.name}' has no action '{namespace}:{name}' (actions: {', '.join(known) or 'none'})"
    )


def find_body(operation: YangRpcStmt, direction: str) -> Optional[YangContainerStmt]:
    wanted = YangInputStmt if direction == "input" else YangOutputStmt
    for stmt in operation.statements:
        if isinstance(stmt, wanted):
            return stmt
    return None


def operation_node(operation: YangRpcStmt, body: Optional[YangContainerStmt]) -> YangContainerStmt:
    """The operation node of RFC 7950 §6.4.1: named after the rpc or action, parameters as children."""
    owner = getattr(operation, "defining_module", None)
    if body is None:
        node = YangContainerStmt(name=operation.name)
    else:
        # A plain container, not the ``input`` / ``output`` class, which data-node walks skip.
        fields = {f.name: getattr(body, f.name) for f in dataclasses.fields(YangContainerStmt)}
        node = YangContainerStmt(**{**fields, "name": operation.name})
    node.defining_module = owner  # type: ignore[attr-defined]
    return node


def accessible_module(
    module: YangModule, target: OperationTarget, operation: YangContainerStmt
) -> tuple[YangModule, list[YangStatement]]:
    """Copy of ``module`` with the operation node in place, and the copies of the parent steps.

    rpc: the top level is the data nodes plus ``operation``; other operations are not data
    nodes and are left out. action: each statement from the top level down to the parent is
    copied, and the parent's copy has ``operation`` in place of the action.
    """
    accessible = copy.copy(module)
    if not target.parents:
        kept = [stmt for stmt in module.statements if not isinstance(stmt, YangRpcStmt)]
        accessible.statements = [*kept, operation]
        return accessible, []
    chain = [stmt for step in target.parents for stmt in (*step.wrappers, step.stmt)]
    copies: dict[int, YangStatement] = {}

    def rebuilt(node: Any, rest: list[YangStatement]) -> Any:
        if not rest:
            node.statements = [operation if s is target.operation else s for s in node.statements]
            return node
        child = copy.copy(rest[0])
        copies[id(rest[0])] = child
        rebuilt(child, rest[1:])
        node.statements = [child if s is rest[0] else s for s in node.statements]
        if isinstance(node, YangChoiceStmt):
            node.cases = [child if c is rest[0] else c for c in node.cases]
        return node

    rebuilt(accessible, chain)
    return accessible, [copies[id(step.stmt)] for step in target.parents]


def lexical(value: Any) -> str:
    """Canonical text of a decoded leaf value, as an RFC 8040 key value is written."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def wrapper_member(module_name: str, direction: str) -> str:
    """RFC 8040 §3.6 member name of the operation body: ``module:input`` or ``module:output``."""
    return f"{module_name}:{direction}"
