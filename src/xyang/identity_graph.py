"""
Identity derivation graph (RFC 7950) for YANG modules, including ``import`` prefixes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from .module import YangModule

IdentityPair = Tuple["YangModule", str]


def qualified_identity_name(module: "YangModule", local_name: str) -> str:
    """Return ``prefix:local`` for this module."""
    p = (module.prefix or "").strip('"\'')
    return f"{p}:{local_name}"


def resolve_identity_qname_pair(importer: "YangModule", qname: str) -> Optional[IdentityPair]:
    """
    Resolve ``prefix:name`` to (defining module, local identity name), using ``import`` map.
    """
    if ":" not in qname:
        return None
    pref, local = qname.split(":", 1)
    m = importer.resolve_prefixed_module(pref)
    if m is None or local not in m.identities:
        return None
    return (m, local)


def resolve_identity_qname(importer: "YangModule", qname: str) -> Optional[str]:
    """Local name of the identity if ``qname`` resolves in *importer* scope; else None."""
    pair = resolve_identity_qname_pair(importer, qname)
    return pair[1] if pair else None


def resolve_identity_base_ref(from_mod: "YangModule", base: str) -> Optional[IdentityPair]:
    """Resolve a ``base`` substatement (possibly prefixed) to (module, local identity)."""
    if ":" in base:
        pref, local = base.split(":", 1)
        m = from_mod.resolve_prefixed_module(pref)
        if m is None or local not in m.identities:
            return None
        return (m, local)
    if base in from_mod.identities:
        return (from_mod, base)
    return None


def _pair_key(pair: IdentityPair) -> tuple[int, str]:
    m, n = pair
    return (id(m), n)


def _pair_in_pairs(p: IdentityPair, pairs: List[IdentityPair]) -> bool:
    kp = _pair_key(p)
    return any(_pair_key(x) == kp for x in pairs)


def identity_ancestor_closure(
    start_mod: "YangModule", start_name: str
) -> List[IdentityPair]:
    """
    Reflexive transitive closure of identity bases starting at (start_mod, start_name):
    all (M, L) reachable by following ``base`` edges.
    """
    out: list[IdentityPair] = []
    seen: Set[tuple[int, str]] = set()
    stack: list[IdentityPair] = [(start_mod, start_name)]
    while stack:
        pair = stack.pop()
        k = _pair_key(pair)
        if k in seen:
            continue
        seen.add(k)
        out.append(pair)
        m, n = pair
        stmt = m.identities.get(n)
        if not stmt:
            continue
        for b in stmt.bases:
            nxt = resolve_identity_base_ref(m, b)
            if nxt:
                stack.append(nxt)
    return out


def strict_ancestors(module: "YangModule", local_name: str) -> Set[str]:
    """Set of strict ancestors of ``local_name`` (same module, unprefixed base names only)."""
    seen: Set[str] = set()
    stack = [local_name]
    while stack:
        cur = stack.pop()
        stmt = module.identities.get(cur)
        if not stmt:
            continue
        for b in stmt.bases:
            if ":" in b:
                continue
            if b not in seen:
                seen.add(b)
                stack.append(b)
    return seen


def descendant_closure(module: "YangModule", base_local: str) -> Set[str]:
    """
    Identities in *module* that derive from ``base_local`` (same-module ``bases`` edges only).

    Used by JSON Schema generation; cross-module ``base`` strings are treated as opaque edge labels.
    """
    children: dict[str, Set[str]] = {}
    for name, stmt in module.identities.items():
        for b in stmt.bases:
            if ":" in b:
                continue
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


def is_derived_from_strict_qnames(importer: "YangModule", v_q: str, t_q: str) -> bool:
    """True iff identity ``v_q`` is a strict descendant of ``t_q`` (RFC 7950 ``derived-from``)."""
    pv = resolve_identity_qname_pair(importer, v_q)
    pt = resolve_identity_qname_pair(importer, t_q)
    if not pv or not pt:
        return False
    closure = identity_ancestor_closure(pv[0], pv[1])
    return pt in closure and _pair_key(pt) != _pair_key(pv)


def is_derived_from_or_self_qnames(importer: "YangModule", v_q: str, t_q: str) -> bool:
    """``derived-from-or-self`` for qualified identity names."""
    pv = resolve_identity_qname_pair(importer, v_q)
    pt = resolve_identity_qname_pair(importer, t_q)
    if not pv or not pt:
        return False
    return _pair_in_pairs(pt, identity_ancestor_closure(pv[0], pv[1]))


def is_derived_from_strict(
    module: "YangModule", value_local: str, target_local: str
) -> bool:
    """Same-module identities only (local names; unprefixed ``base`` edges)."""
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
    importer: "YangModule", value_qname: str, identityref_bases: list[str]
) -> bool:
    """
    RFC 7950: instance value must be derived from **every** ``identityref`` ``base``.
    """
    if not identityref_bases:
        return False
    pair_v = resolve_identity_qname_pair(importer, value_qname)
    if pair_v is None:
        return False
    closure = identity_ancestor_closure(pair_v[0], pair_v[1])
    for b in identityref_bases:
        br = resolve_identity_base_ref(importer, b)
        if br is None:
            return False
        if not _pair_in_pairs(br, closure):
            return False
    return True
