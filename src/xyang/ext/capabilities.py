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


def apply_extension_invocations(module: "YangModule", *, export_view: bool = False) -> None:
    """Walk the schema tree and apply callbacks via ``resolved_extension.apply(...)``.

    ``export_view`` is set by the native JSON generator. A foreign ``sx:augment-structure``
    is then left in the tree instead of being merged into the imported module.
    Calling this twice does not apply an invocation twice: RFC 8791 callbacks no-op
    once they have run, and a removed invocation is not in the tree.
    """
    from .rfc8791.structure_expand import (
        FOREIGN_AUGMENTS,
        FOREIGN_SLOTS,
        reset_export_view,
        set_export_view,
    )

    def walk(owner: YangStatementList, *, at_root: bool) -> None:
        out: list[YangStatement] = []
        kept_extensions = 0
        for stmt in owner.statements:
            cur: Optional[YangStatement] = stmt
            if isinstance(stmt, YangExtensionInvocationStmt):
                if at_root:
                    stmt._rfc8791_root = True  # type: ignore[attr-defined]
                cur = stmt.resolved_extension.apply(stmt, context_module=module)
                if (
                    cur is None
                    and at_root
                    and getattr(stmt, "_rfc8791_foreign", False)
                    and not export_view
                ):
                    saved = module.extension_runtime.setdefault(FOREIGN_AUGMENTS, [])
                    if stmt not in saved:
                        saved.append(stmt)
                        module.extension_runtime.setdefault(FOREIGN_SLOTS, []).append(kept_extensions)
            if cur is None:
                continue
            if isinstance(cur, YangChoiceStmt):
                for case in cur.cases:
                    walk(case, at_root=False)
            if hasattr(cur, "statements"):
                walk(cur, at_root=False)  # type: ignore[arg-type]
            if at_root and isinstance(cur, YangExtensionInvocationStmt):
                kept_extensions += 1
            out.append(cur)
        owner.statements = out

    token = set_export_view(export_view)
    try:
        walk(module, at_root=True)
    finally:
        reset_export_view(token)


__all__ = [
    "ExtensionApplyCallback",
    "ExtensionIdentity",
    "apply_extension_invocations",
    "get_extension_apply_callback",
    "register_extension_apply_callback",
]
