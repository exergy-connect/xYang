"""
Identity derivation graph (RFC 7950) for a single YANG module.

Edges: child identity -> each name in ``YangIdentityStmt.bases`` (DAG, multi-base).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Set

if TYPE_CHECKING:
    from .module import YangModule


def qualified_identity_name(module: "YangModule", local_name: str) -> str:
    """Return ``prefix:local`` for this module."""
    p = (module.prefix or "").strip('"\'')
    return f"{p}:{local_name}"


def resolve_identity_qname(module: "YangModule", qname: str) -> Optional[str]:
    """
    Resolve a qualified identity string (``prefix:name``) to local identity name, or None.

    Only the module's own prefix is recognized (single-module scope).
    """
    if ":" not in qname:
        return None
    pref, local = qname.split(":", 1)
    mod_pref = (module.prefix or "").strip('"\'')
    if pref != mod_pref:
        return None
    if local not in module.identities:
        return None
    return local


def strict_ancestors(module: "YangModule", local_name: str) -> Set[str]:
    """Set of strict ancestors of ``local_name`` (reachable via ``bases`` edges upward)."""
    seen: Set[str] = set()
    stack = [local_name]
    while stack:
        cur = stack.pop()
        stmt = module.identities.get(cur)
        if not stmt:
            continue
        for b in stmt.bases:
            if b not in seen:
                seen.add(b)
                stack.append(b)
    return seen


def descendant_closure(module: "YangModule", base_local: str) -> Set[str]:
    """
    Identities that have ``base_local`` as an ancestor or equal (valid ``identityref`` to ``base``).

    Walk downward: any identity that lists base_local in its transitive bases... Actually:
    valid identityref to base B = identities I such that B is in ancestors(I) ∪ {I} when I==B.

    Equivalently: I == B or B ∈ strict_ancestors(I) ... No: "derived from B" means B is on path upward from I.

    I is valid for identityref base B iff I == B or B is a strict ancestor of I... No:
    RFC: identityref to base animal allows animal, mammal, dog — identities **derived from** animal.

    So I is valid iff I == animal OR animal ∈ strict_ancestors(I)? Mammal has base animal, so ancestors of mammal include... strict_ancestors(mammal) = {animal}. So mammal != animal but animal is ancestor — valid.

    Dog: strict_ancestors(dog) = {mammal, animal}. Valid for base animal.

    Condition: base_local == I or base_local ∈ strict_ancestors(I).

    Descendant closure from base B (including B): all I such that B == I or B ∈ strict_ancestors(I).

    Algorithm: reverse graph — children[C] = identities that have C in bases (direct). BFS from base_local.
    """
    children: dict[str, Set[str]] = {}
    for name, stmt in module.identities.items():
        for b in stmt.bases:
            children.setdefault(b, set()).add(name)

    out: Set[str] = {base_local}
    stack = [base_local]
    while stack:
        cur = stack.pop()
        for ch in children.get(cur, ()):
            if ch not in out:
                out.add(ch)
                stack.append(ch)
    return out


def is_derived_from_strict(
    module: "YangModule", value_local: str, target_local: str
) -> bool:
    """True iff value identity is a strict descendant of target (target is proper ancestor)."""
    if value_local == target_local:
        return False
    anc = strict_ancestors(module, value_local)
    return target_local in anc


def is_derived_from_or_self(
    module: "YangModule", value_local: str, target_local: str
) -> bool:
    if value_local == target_local:
        return True
    return is_derived_from_strict(module, value_local, target_local)


def identityref_value_valid(
    module: "YangModule", value_local: str, identityref_bases: list[str]
) -> bool:
    """
    RFC 7950: value must be derived from **every** base in ``identityref_bases`` (intersection).
    """
    if not identityref_bases:
        return False
    for b in identityref_bases:
        allowed = descendant_closure(module, b)
        if value_local not in allowed:
            return False
    return True
