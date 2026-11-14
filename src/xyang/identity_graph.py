"""
Identity derivation graph (RFC 7950) for YANG modules, including ``import`` prefixes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union

from .identifier_ref import (
    YangIdentifierRef,
    parse_identifier_ref_atom,
)

if TYPE_CHECKING:
    from .module import YangModule

IdentityPair = tuple["YangModule", str]
BaseRef = Union[str, YangIdentifierRef]


def qualified_identity_name(module: "YangModule", local_name: str) -> str:
    """Return ``prefix:local`` for this module."""
    p = (module.prefix or "").strip('"\'')
    return f"{p}:{local_name}"


def _as_base_ref(base: BaseRef) -> YangIdentifierRef:
    if isinstance(base, YangIdentifierRef):
        return base
    return parse_identifier_ref_atom(base)


def resolve_identity_qname_pair(importer: "YangModule", qname: str) -> Optional[IdentityPair]:
    """
    Resolve ``prefix:name`` to (defining module, local identity name), using ``import`` map.
    """
    ref = parse_identifier_ref_atom(qname)
    if not ref.prefix:
        return None
    return resolve_identity_base_ref(importer, ref)


def resolve_identity_value(module: "YangModule", value: str) -> Optional[IdentityPair]:
    """Resolve an RFC 7951 identityref instance value (§6.8).

    ``name`` resolves in *module*. ``modname:name`` resolves where ``modname`` is the
    *module name* (not the prefix) of *module* itself or of a module it imports.
    """
    if not isinstance(value, str) or not value:
        return None
    if ":" in value:
        mod_name, name = value.split(":", 1)
        if mod_name == module.name:
            target: Optional["YangModule"] = module
        else:
            imported = list(module.import_prefixes.values())
            for sub in module.included_files.values():
                imported.extend(sub.import_prefixes.values())
            target = next((m for m in imported if m.name == mod_name), None)
        if target is None:
            return None
    else:
        target, name = module, value
    if name not in target.identities:
        return None
    return (target, name)


def resolve_identity_base_ref(
    from_mod: "YangModule", base: BaseRef, file: str | None = None
) -> Optional[IdentityPair]:
    """Resolve a ``base`` substatement (possibly prefixed) to (module, local identity).

    *file* is the source file that wrote the ``base`` (a submodule name, or None).
    """
    ref = _as_base_ref(base)
    if ref.prefix:
        m = from_mod.resolve_prefixed_module(ref.prefix, file)
        if m is None or ref.name not in m.identities:
            return None
        return (m, ref.name)
    if ref.name in from_mod.identities:
        return (from_mod, ref.name)
    return None


def _pair_key(pair: IdentityPair) -> tuple[int, str]:
    m, n = pair
    return (id(m), n)


def _pair_in_pairs(p: IdentityPair, pairs: list[IdentityPair]) -> bool:
    kp = _pair_key(p)
    return any(_pair_key(x) == kp for x in pairs)


def identity_ancestor_closure(
    start_mod: "YangModule", start_name: str
) -> list[IdentityPair]:
    """
    Reflexive transitive closure of identity bases starting at (start_mod, start_name):
    all (M, L) reachable by following ``base`` edges.
    """
    out: list[IdentityPair] = []
    seen: set[tuple[int, str]] = set()
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
            nxt = resolve_identity_base_ref(m, b, getattr(stmt, "included_from", None))
            if nxt:
                stack.append(nxt)
    return out


def strict_ancestors(module: "YangModule", local_name: str) -> set[str]:
    """Set of strict ancestors of ``local_name`` (same module, unprefixed base names only)."""
    seen: set[str] = set()
    stack = [local_name]
    while stack:
        cur = stack.pop()
        stmt = module.identities.get(cur)
        if not stmt:
            continue
        for b in stmt.bases:
            ref = _as_base_ref(b)
            if ref.prefix:
                continue
            if ref.name not in seen:
                seen.add(ref.name)
                stack.append(ref.name)
    return seen


def descendant_closure(module: "YangModule", base_local: str) -> set[str]:
    """
    Identities in *module* that derive from ``base_local`` (same-module ``bases`` edges only).

    Used by JSON Schema generation; cross-module ``base`` refs are treated as opaque edge labels.
    """
    children: dict[str, set[str]] = {}
    for name, stmt in module.identities.items():
        for b in stmt.bases:
            ref = _as_base_ref(b)
            if ref.prefix:
                continue
            children.setdefault(ref.name, set()).add(name)

    out: set[str] = {base_local}
    stack = [base_local]
    while stack:
        cur = stack.pop()
        for ch in children.get(cur, ()):
            if ch not in out:
                out.add(ch)
                stack.append(ch)
    return out


def is_derived_from_strict_qnames(importer: "YangModule", v_q: str, t_q: str) -> bool:
    """True iff identity ``v_q`` is a strict descendant of ``t_q`` (RFC 7950 ``derived-from``).

    ``v_q`` is an instance value (RFC 7951 module name); ``t_q`` is a schema literal (prefix).
    """
    pv = resolve_identity_value(importer, v_q)
    pt = resolve_identity_qname_pair(importer, t_q)
    if not pv or not pt:
        return False
    closure = identity_ancestor_closure(pv[0], pv[1])
    return pt in closure and _pair_key(pt) != _pair_key(pv)


def is_derived_from_or_self_qnames(importer: "YangModule", v_q: str, t_q: str) -> bool:
    """``derived-from-or-self``; same name rules as :func:`is_derived_from_strict_qnames`."""
    pv = resolve_identity_value(importer, v_q)
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


def identityref_value_valid(
    importer: "YangModule",
    value_qname: str,
    identityref_bases: list[YangIdentifierRef],
    base_scope: Optional["YangModule"] = None,
) -> bool:
    """
    RFC 7950: instance value must be derived from **every** ``identityref`` ``base``.
    The bases resolve in *base_scope*, the module that wrote the ``type`` (default *importer*).
    The value uses RFC 7951 module names; the bases use schema prefixes.
    """
    if not identityref_bases:
        return False
    pair_v = resolve_identity_value(importer, value_qname)
    if pair_v is None:
        return False
    closure = identity_ancestor_closure(pair_v[0], pair_v[1])
    for b in identityref_bases:
        br = resolve_identity_base_ref(base_scope or importer, b)
        if br is None:
            return False
        if not _pair_in_pairs(br, closure):
            return False
    return True
