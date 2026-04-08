"""
Evaluate YANG 1.1 ``if-feature`` boolean expressions (RFC 7950 §7.20.2, §14).

Multiple ``if-feature`` substatements on one node are combined with logical AND.
"""

from __future__ import annotations

from typing import AbstractSet, Dict, List, Mapping, Optional, Set

from ..module import YangModule


class IfFeatureEvalError(Exception):
    """Malformed ``if-feature`` expression."""


def reachable_modules(root: YangModule) -> List[YangModule]:
    """``root`` and all modules reachable via ``import`` (transitive)."""
    out: List[YangModule] = []
    seen: Set[int] = set()

    def walk(m: YangModule) -> None:
        if id(m) in seen:
            return
        seen.add(id(m))
        out.append(m)
        for im in m.import_prefixes.values():
            walk(im)

    walk(root)
    return out


def build_enabled_features_map(
    root: YangModule,
    override: Optional[Mapping[str, AbstractSet[str]]],
) -> Dict[str, AbstractSet[str]]:
    """
    For each reachable module, the set of feature names that are *enabled*.

    * ``override is None``: every *declared* feature is enabled (backward compatible).
    * ``override[m]`` present: only those feature names are enabled for module ``m``.
    * Module not listed in ``override``: all declared features enabled.
    """
    modules = reachable_modules(root)
    result: Dict[str, AbstractSet[str]] = {}
    for m in modules:
        if override is None or m.name not in override:
            result[m.name] = frozenset(m.features)
        else:
            result[m.name] = frozenset(override[m.name])
    return _prune_per_feature_if_features(modules, result)


def feature_is_supported(
    ctx_module: YangModule,
    enabled_by_module: Mapping[str, AbstractSet[str]],
    ref: str,
) -> bool:
    """
    Whether feature reference *ref* (``name`` or ``prefix:name``) is supported
    in the context of *ctx_module* (the module where the ``if-feature`` appears).
    """
    if ":" in ref:
        pref, _, fname = ref.partition(":")
        mod = ctx_module.resolve_prefixed_module(pref)
        if mod is None:
            return False
    else:
        mod = ctx_module
        fname = ref
    if fname not in mod.features:
        return False
    enabled = enabled_by_module.get(mod.name)
    if enabled is None:
        return False
    return fname in enabled


def _tokenize(expr: str) -> List[str]:
    tokens: List[str] = []
    i = 0
    n = len(expr)
    while i < n:
        c = expr[i]
        if c.isspace():
            i += 1
            continue
        if c in "()":
            tokens.append(c)
            i += 1
            continue
        j = i
        while j < n and not expr[j].isspace() and expr[j] not in "()":
            j += 1
        tokens.append(expr[i:j])
        i = j
    return tokens


class _IfFeatureParser:
    __slots__ = ("_ctx", "_enabled", "_i", "_toks")

    def __init__(
        self,
        tokens: List[str],
        ctx_module: YangModule,
        enabled_by_module: Mapping[str, AbstractSet[str]],
    ) -> None:
        self._toks = tokens
        self._i = 0
        self._ctx = ctx_module
        self._enabled = enabled_by_module

    def _peek(self) -> Optional[str]:
        return self._toks[self._i] if self._i < len(self._toks) else None

    def _eat(self, expected: Optional[str] = None) -> str:
        t = self._peek()
        if t is None:
            raise IfFeatureEvalError("unexpected end of expression")
        if expected is not None and t != expected:
            raise IfFeatureEvalError(f"expected {expected!r}, got {t!r}")
        self._i += 1
        return t

    def parse_expr(self) -> bool:
        left = self.parse_term()
        while self._peek() == "or":
            self._eat("or")
            # Parse RHS unconditionally — Python ``or`` short-circuits and would skip
            # consuming tokens, breaking ``at_end()`` and wrong results for ``a or b``.
            right = self.parse_expr()
            left = left or right
        return left

    def parse_term(self) -> bool:
        left = self.parse_factor()
        while self._peek() == "and":
            self._eat("and")
            right = self.parse_term()
            left = left and right
        return left

    def parse_factor(self) -> bool:
        t = self._peek()
        if t == "not":
            self._eat("not")
            return not self.parse_factor()
        if t == "(":
            self._eat("(")
            v = self.parse_expr()
            self._eat(")")
            return v
        if t is None:
            raise IfFeatureEvalError("unexpected end of expression")
        self._eat()
        return feature_is_supported(self._ctx, self._enabled, t)

    def at_end(self) -> bool:
        return self._i >= len(self._toks)


def evaluate_if_feature_expression(
    expr: str,
    ctx_module: YangModule,
    enabled_by_module: Mapping[str, AbstractSet[str]],
) -> bool:
    """
    Evaluate a single ``if-feature`` argument string.

    On malformed syntax, returns ``False`` (strict: node is inactive).
    """
    expr = expr.strip()
    if not expr:
        return False
    try:
        p = _IfFeatureParser(_tokenize(expr), ctx_module, enabled_by_module)
        out = p.parse_expr()
        if not p.at_end():
            return False
        return out
    except IfFeatureEvalError:
        return False


def stmt_if_features_satisfied(
    if_features: List[str],
    ctx_module: YangModule,
    enabled_by_module: Mapping[str, AbstractSet[str]],
) -> bool:
    """True iff every ``if-feature`` substatement on the node passes (AND)."""
    if not if_features:
        return True
    return all(
        evaluate_if_feature_expression(e, ctx_module, enabled_by_module)
        for e in if_features
    )


def _prune_per_feature_if_features(
    modules: List[YangModule],
    enabled: Dict[str, AbstractSet[str]],
) -> Dict[str, AbstractSet[str]]:
    """RFC 7950 §7.20.1: drop feature names whose own ``if-feature`` substatements fail."""
    mutable: Dict[str, Set[str]] = {m.name: set(enabled.get(m.name, ())) for m in modules}
    changed = True
    while changed:
        changed = False
        frozen = {mn: frozenset(s) for mn, s in mutable.items()}
        for m in modules:
            for fname in list(mutable[m.name]):
                reqs = m.feature_if_features.get(fname)
                if not reqs:
                    continue
                if not stmt_if_features_satisfied(reqs, m, frozen):
                    mutable[m.name].discard(fname)
                    changed = True
    return {k: frozenset(v) for k, v in mutable.items()}
