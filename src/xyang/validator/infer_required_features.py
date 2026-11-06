"""Infer positive feature requirements from instance member presence."""
import re

from ..ast import (YangContainerStmt, YangListStmt, YangLeafStmt, YangLeafListStmt,
                   YangAnydataStmt, YangAnyxmlStmt, YangChoiceStmt, YangCaseStmt)
from ..module import YangModule
from .if_feature_eval import reachable_modules


def infer_required_features(module: YangModule, instance: object) -> list[str]:
    """Return sorted module:feature names; raise ValueError for unsupported input.

    Supports feature atoms and positive conjunctions. Does not validate values or
    descend into opaque anydata/anyxml payloads. Parse with uses expansion enabled.
    """
    modules = {m.name: m for m in reachable_modules(module)}
    required: set[str] = set()
    active: set[str] = set()

    def add_conditions(conditions, ctx):
        for expression in conditions or []:
            atoms = re.split(r"\s+and\s+", expression.strip())
            if any(not re.fullmatch(r"[A-Za-z_][\w.-]*(?::[A-Za-z_][\w.-]*)?", a, re.ASCII)
                   or a in {"and", "or", "not"} for a in atoms):
                raise ValueError(f"Unsupported if-feature expression: {expression}")
            for atom in atoms:
                parts = atom.split(":")
                name = parts[-1]
                owner = ctx.resolve_prefixed_module(parts[0]) if len(parts) == 2 else ctx
                if owner is None or name not in owner.features:
                    raise ValueError(f"Unknown feature: {atom}")
                key = f"{owner.name}:{name}"
                if key in active:
                    raise ValueError(f"Cyclic feature prerequisite: {key}")
                if key in required:
                    continue
                active.add(key)
                add_conditions(owner.feature_if_features.get(name), owner)
                active.remove(key)
                required.add(key)

    def entries(statements, ctx, gates=()):
        for stmt in statements:
            owner = getattr(stmt, "defining_module", None)
            local = modules.get(owner) if owner else ctx
            if local is None:
                raise ValueError(f"Unknown defining module: {owner}")
            if isinstance(stmt, (YangChoiceStmt, YangCaseStmt)):
                children = stmt.cases if isinstance(stmt, YangChoiceStmt) else stmt.statements
                yield from entries(children, local, (*gates, (stmt, local)))
            elif isinstance(stmt, (YangContainerStmt, YangListStmt, YangLeafStmt,
                                   YangLeafListStmt, YangAnydataStmt, YangAnyxmlStmt)):
                yield stmt, gates, local

    def walk(statements, value, ctx):
        if not isinstance(value, dict):
            raise ValueError("Instance object expected")
        candidates = list(entries(statements, ctx))
        for key, child in value.items():
            matches = [(s, g, c) for s, g, c in candidates
                       if key == f"{c.name}:{s.name}" or (key == s.name and c is ctx)]
            if len(matches) != 1:
                raise ValueError(f"Unknown or ambiguous instance element: {key}")
            stmt, gates, local = matches[0]
            for gate, gate_ctx in gates:
                add_conditions(gate.if_features, gate_ctx)
            add_conditions(stmt.if_features, local)
            if isinstance(stmt, YangListStmt):
                if not isinstance(child, list):
                    raise ValueError(f"List array expected: {key}")
                for row in child:
                    walk(stmt.statements, row, local)
            elif isinstance(stmt, YangContainerStmt):
                walk(stmt.statements, child, local)

    walk(module.statements, instance, module)
    return sorted(required)
