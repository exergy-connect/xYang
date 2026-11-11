"""RPC input and output instances (RFC 7950 §7.14, accessible tree §6.4.1).

The module and the caller's data are never modified. The accessible tree is built from
a shallow copy of the module whose statement list holds the server data nodes plus one
operation node named after the rpc; that node carries the ``input`` or ``output`` body
as its children.
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Optional

from ..ast import YangContainerStmt, YangInputStmt, YangOutputStmt, YangRpcStmt
from ..module import YangModule

DIRECTIONS = ("input", "output")


def check_operation_options(rpc: Optional[str], direction: str, context: object) -> None:
    """Reject option combinations that make no sense; ``ValueError`` is a usage error."""
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be 'input' or 'output', got {direction!r}")
    if rpc is None:
        if direction != "input":
            raise ValueError("direction applies only together with rpc")
        if context is not None:
            raise ValueError("context applies only together with rpc")
    elif not isinstance(rpc, str) or not rpc:
        raise ValueError("rpc must be a non-empty rpc name")


def find_rpc(module: YangModule, name: str) -> YangRpcStmt:
    for stmt in module.statements:
        if isinstance(stmt, YangRpcStmt) and stmt.name == name:
            return stmt
    known = sorted(s.name for s in module.statements if isinstance(s, YangRpcStmt) and s.name)
    listing = ", ".join(known) if known else "none"
    raise ValueError(f"module '{module.name}' has no rpc '{name}' (rpcs: {listing})")


def find_body(rpc: YangRpcStmt, direction: str) -> Optional[YangContainerStmt]:
    wanted = YangInputStmt if direction == "input" else YangOutputStmt
    for stmt in rpc.statements:
        if isinstance(stmt, wanted):
            return stmt
    return None


def operation_node(rpc: YangRpcStmt, body: Optional[YangContainerStmt]) -> YangContainerStmt:
    """The operation node of RFC 7950 §6.4.1: named after the rpc, parameters as children."""
    if body is None:
        return YangContainerStmt(name=rpc.name)
    return dataclasses.replace(body, name=rpc.name)


def accessible_module(module: YangModule, operation: YangContainerStmt) -> YangModule:
    """Copy of ``module`` whose top level is its data nodes plus ``operation``.

    Operations other than ``operation`` are not data nodes and are left out, so a path
    step to the rpc name finds the operation node and nothing else.
    """
    accessible = copy.copy(module)
    kept = [stmt for stmt in module.statements if not isinstance(stmt, YangRpcStmt)]
    accessible.statements = [*kept, operation]
    return accessible


def wrapper_member(module: YangModule, direction: str) -> str:
    """RFC 8040 §3.6 member name of the operation body: ``module:input`` or ``module:output``."""
    return f"{module.name}:{direction}"
