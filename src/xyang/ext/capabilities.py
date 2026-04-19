"""Extension callback registry and generic invocation application."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Protocol, TYPE_CHECKING

from ..ast import (
    YangChoiceStmt,
    YangExtensionInvocationStmt,
    YangStatement,
    YangStatementList,
)

if TYPE_CHECKING:
    from ..module import YangModule


@dataclass(frozen=True)
class ExtensionIdentity:
    """Fully-qualified extension identity (defining module + local extension name)."""

    module_name: str
    extension_name: str


class ExtensionApplyCallback(Protocol):
    """Apply callback for one extension identity."""

    def __call__(
        self,
        invocation: YangExtensionInvocationStmt,
        context_module: "YangModule",
    ) -> Optional[YangStatement]:
        """Return replacement stmt, or ``None`` to remove invocation."""


_APPLY_CALLBACKS: Dict[ExtensionIdentity, ExtensionApplyCallback] = {}


def register_extension_apply_callback(
    identity: ExtensionIdentity,
    callback: ExtensionApplyCallback,
) -> None:
    """Register apply callback for one extension identity."""
    _APPLY_CALLBACKS[identity] = callback


def get_extension_apply_callback(identity: ExtensionIdentity) -> Optional[ExtensionApplyCallback]:
    """Return apply callback for *identity*, if one is registered."""
    return _APPLY_CALLBACKS.get(identity)


def apply_extension_invocations(module: "YangModule") -> None:
    """Walk the schema tree and apply callbacks via ``resolved_extension.apply(...)``."""

    def walk(owner: YangStatementList) -> None:
        out: list[YangStatement] = []
        for stmt in owner.statements:
            cur: Optional[YangStatement] = stmt
            if isinstance(stmt, YangExtensionInvocationStmt):
                cur = stmt.resolved_extension.apply(stmt, context_module=module)
            if cur is None:
                continue
            if isinstance(cur, YangChoiceStmt):
                for case in cur.cases:
                    walk(case)
            if hasattr(cur, "statements"):
                walk(cur)  # type: ignore[arg-type]
            out.append(cur)
        owner.statements = out

    walk(module)


__all__ = [
    "ExtensionApplyCallback",
    "ExtensionIdentity",
    "apply_extension_invocations",
    "get_extension_apply_callback",
    "register_extension_apply_callback",
]
