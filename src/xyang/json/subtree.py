"""Project an effective YANG JSON schema to a standalone data subtree."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Collection

from ..errors import YangExportError
from ..module import YangModule
from ..validator.if_feature_eval import build_enabled_features_map, reachable_modules, stmt_if_features_satisfied
from ..xpath.ast import BinaryOpNode, FunctionCallNode, LiteralNode, PathNode
from ..xpath.parser import XPathParser


@dataclass(frozen=True)
class SchemaDiagnostic:
    path: str
    constraint: str
    expression: str
    reason: str


@dataclass(frozen=True)
class SchemaExportResult:
    schema: dict[str, Any]
    diagnostics: list[SchemaDiagnostic]


def _local(name: str) -> str:
    return name.rsplit(":", 1)[-1]


def _children(node: dict[str, Any]):
    yield node
    item = node.get("items")
    if isinstance(item, dict):
        yield from _children(item)
    for value in node.get("properties", {}).values():
        if isinstance(value, dict) and value.get("x-yang", {}).get("type") == "choice":
            yield from _children(value)
    for key in ("oneOf", "anyOf", "allOf"):
        for branch in node.get(key, []):
            if isinstance(branch, dict):
                yield from _children(branch)


def _lookup(root: dict[str, Any], path: list[str]) -> dict[str, Any]:
    node = root
    for segment in path:
        found = [value for parent in _children(node) for key, value in parent.get("properties", {}).items()
                 if key == segment or (":" not in segment and _local(key) == segment)]
        found = [value for index, value in enumerate(found) if value not in found[:index]]
        if len(found) != 1:
            raise YangExportError(f"subtree path segment '{segment}' {'is ambiguous' if found else 'was not found'}")
        node = found[0]
    return node


def _path_target(expression: str, context: list[str]) -> list[str]:
    ast = XPathParser(expression).parse()
    if not isinstance(ast, PathNode):
        raise YangExportError(f"cannot resolve leafref '{expression}'")
    target = [] if ast.is_absolute else list(context)
    for segment in ast.segments:
        if segment.step == "..":
            if not target:
                raise YangExportError(f"invalid leafref '{expression}'")
            target.pop()
        elif segment.step != ".":
            if segment.is_wildcard:
                raise YangExportError(f"cannot resolve leafref '{expression}'")
            target.append(segment.local)
    return target


def _within(expression: str, context: list[str], scope: list[str], module: YangModule, bindings: dict[str, str]) -> bool:
    def inside(path: list[str]) -> bool:
        return path[:len(scope)] == scope

    def visit(node: Any, base: list[str]) -> bool:
        if isinstance(node, LiteralNode):
            return True
        if isinstance(node, BinaryOpNode):
            if node.operator == "/" and isinstance(node.left, FunctionCallNode) and node.left.name == "current":
                return inside(context) and visit(node.right, context)
            return visit(node.left, base) and visit(node.right, base)
        if isinstance(node, FunctionCallNode):
            if node.name == "deref":
                return False
            if node.name == "current":
                return inside(context)
            return all(visit(arg, base) for arg in node.args)
        if not isinstance(node, PathNode):
            return False
        path = [] if node.is_absolute else list(base)
        for segment in node.segments:
            if segment.prefix and segment.prefix != module.prefix and bindings.get(segment.prefix) != module.name:
                return False
            if segment.step == "..":
                if path:
                    path.pop()
            elif segment.step != ".":
                if segment.is_wildcard:
                    return False
                path.append(segment.local)
            if segment.predicate is not None and not visit(segment.predicate, path):
                return False
        return inside(path)
    return visit(XPathParser(expression).parse(), context)


def _supported_prefixes(expression: str, module: YangModule, bindings: dict[str, str]) -> bool:
    def visit(node: Any) -> bool:
        if isinstance(node, (LiteralNode,)):
            return True
        if isinstance(node, BinaryOpNode):
            return visit(node.left) and visit(node.right)
        if isinstance(node, FunctionCallNode):
            return all(visit(arg) for arg in node.args)
        if isinstance(node, PathNode):
            return all((not segment.prefix or segment.prefix == module.prefix or bindings.get(segment.prefix) == module.name)
                       and (segment.predicate is None or visit(segment.predicate)) for segment in node.segments)
        return False
    return visit(XPathParser(expression).parse())


def _json_pattern(pattern: str) -> str:
    """Map XSD's literal anchors and dot to JSON Schema regex syntax."""
    result: list[str] = []
    escaped = False
    in_class = False
    for char in pattern:
        if escaped:
            if char in "dDsSwWiIcCpP":
                raise YangExportError(f"subtree schema cannot portably encode XSD regex escape '\\{char}'")
            if char in "nrt":
                result.append("\\" + char)
            elif ord(char) < 128:
                result.append(f"\\u{ord(char):04X}")
            else:
                raise YangExportError("subtree schema cannot portably encode escaped non-ASCII characters")
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "[":
            in_class = True
            result.append(char)
        elif char == "]" and in_class:
            in_class = False
            result.append(char)
        elif not in_class and char in "^$":
            result.append("\\" + char)
        elif not in_class and char == ".":
            result.append("[^\\r\\n]")
        else:
            result.append(char)
    if escaped:
        raise YangExportError("invalid trailing escape in YANG pattern")
    return "^(?:" + "".join(result) + ")$"


def _translate_patterns(value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            _translate_patterns(item)
    elif isinstance(value, dict):
        meta = value.get("x-yang", {})
        patterns = meta.get("string-patterns", []) if isinstance(meta, dict) else []
        if len(patterns) == 1 and not patterns[0].get("invert-match"):
            value["pattern"] = _json_pattern(patterns[0]["pattern"])
        elif patterns and isinstance(value.get("allOf"), list):
            for pattern, branch in zip(patterns, value["allOf"]):
                target = branch.get("not", {}) if pattern.get("invert-match") else branch
                target["pattern"] = _json_pattern(pattern["pattern"])
        for child in value.values():
            _translate_patterns(child)


def project_subtree(full: dict[str, Any], module: YangModule, path: str, *,
                    features: Mapping[str, Collection[str]] | None = None,
                    native_json: bool = False) -> SchemaExportResult:
    if not isinstance(path, str) or not path.startswith("/") or path == "/":
        raise YangExportError(f"subtree path must be absolute: {path!r}")
    raw_segments = path[1:].split("/")
    if any(not segment for segment in raw_segments):
        raise YangExportError(f"invalid subtree path: {path!r}")
    for segment in raw_segments:
        if ":" in segment and segment.split(":", 1)[0] not in (module.prefix, module.name):
            raise YangExportError(f"unsupported module prefix in subtree path '{path}'")
    scope = [_local(segment) for segment in raw_segments]
    enabled = build_enabled_features_map(module, features)
    available = deepcopy(full)

    def active(meta: dict[str, Any]) -> bool:
        import re
        guards = meta.get("if-features", [])
        imports = [other for other in reachable_modules(module) if other is not module]
        for expression in guards:
            for token in re.findall(r"[A-Za-z_][A-Za-z0-9_.:-]*", expression):
                if token not in ("and", "or", "not") and ":" not in token and any(token in other.features for other in imports):
                    raise YangExportError(f"cannot safely resolve unqualified if-feature '{token}' shared with an imported module")
        return stmt_if_features_satisfied(guards, module, enabled)

    def restrict(node: Any) -> None:
        """Drop enum and bit values whose ``if-feature`` is false from a schema object."""
        if isinstance(node, list):
            for item in node:
                restrict(item)
            return
        if not isinstance(node, dict):
            return
        meta = node.get("x-yang")
        if isinstance(meta, dict):
            entries = meta.get("enums")
            values = node.get("enum")
            if isinstance(entries, list) and isinstance(values, list):
                drop: set[str] = set()
                kept = []
                for entry in entries:
                    if not isinstance(entry, dict):
                        kept.append(entry)
                        continue
                    name = entry.get("name")
                    feats = entry.get("if-features") or []
                    if isinstance(name, str) and isinstance(feats, list) and feats and not active({"if-features": feats}):
                        drop.add(name)
                        continue
                    kept.append(entry)
                if drop:
                    node["enum"] = [value for value in values if value not in drop]
                    if any(isinstance(entry, dict) and entry.get("if-features") for entry in kept):
                        meta["enums"] = kept
                    else:
                        meta.pop("enums", None)
            bit_guards = meta.get("bit-if-features")
            bits = meta.get("bits")
            if isinstance(bit_guards, dict) and isinstance(bits, dict):
                disabled = [
                    name for name, feats in bit_guards.items()
                    if isinstance(feats, list) and feats and not active({"if-features": feats})
                ]
                if disabled:
                    for name in disabled:
                        bits.pop(name, None)
                        bit_guards.pop(name, None)
                    from .generator import _bits_space_separated_pattern

                    node["pattern"] = _bits_space_separated_pattern(list(bits))
                    if not bit_guards:
                        meta.pop("bit-if-features", None)
        for child in list(node.values()):
            restrict(child)

    restrict(available)

    def prune(node: dict[str, Any]) -> bool:
        meta = node.get("x-yang", {})
        if not active(meta):
            return False
        choice = meta.get("choice")
        if isinstance(choice, dict) and not active(choice):
            branches = [branch for branch in node.get("oneOf", []) if isinstance(branch, dict)]
            if branches:
                common = dict(branches[0].get("properties", {}))
                for branch in branches[1:]:
                    common = {key: value for key, value in common.items() if branch.get("properties", {}).get(key) == value}
                required = [key for key in branches[0].get("required", []) if all(key in branch.get("required", []) for branch in branches[1:])]
                node["properties"] = common
                node["additionalProperties"] = False
                if required:
                    node["required"] = required
                else:
                    node.pop("required", None)
            node.pop("oneOf", None)
            del meta["choice"]
        props = node.get("properties")
        if isinstance(props, dict):
            for name, child in list(props.items()):
                if isinstance(child, dict) and not prune(child):
                    del props[name]
            if isinstance(node.get("required"), list):
                node["required"] = [name for name in node["required"] if name in props]
        if isinstance(node.get("items"), dict):
            prune(node["items"])
        for key in ("oneOf", "anyOf", "allOf"):
            if isinstance(node.get(key), list):
                node[key] = [branch for branch in node[key] if not isinstance(branch, dict) or prune(branch)]
        return True
    prune(available)
    selected = deepcopy(_lookup(available, scope))
    diagnostics: list[SchemaDiagnostic] = []

    def report(current: list[str], kind: str, expression: str, reason: str = "depends on data outside the selected subtree or cannot be proved local") -> None:
        item = SchemaDiagnostic("/" + "/".join(current), kind, expression, reason)
        if item not in diagnostics:
            diagnostics.append(item)

    def contains_leafref(value: Any, seen: set[str] | None = None) -> bool:
        if not isinstance(value, dict):
            return False
        if value.get("x-yang", {}).get("type") == "leafref":
            return True
        seen = seen or set()
        ref = value.get("$ref", "")
        if ref.startswith("#/$defs/") and ref not in seen:
            seen.add(ref)
            if contains_leafref(full.get("$defs", {}).get(ref.removeprefix("#/$defs/")), seen):
                return True
        return any(contains_leafref(item, set(seen)) for item in value.get("oneOf", []))

    def visit(node: dict[str, Any], current: list[str]) -> None:
        meta = node.get("x-yang", {})
        resolved = node
        ref = node.get("$ref", "")
        if ref.startswith("#/$defs/"):
            resolved = full.get("$defs", {}).get(ref.removeprefix("#/$defs/"), node)
        if meta.get("type") in ("leaf", "leaf-list") and resolved.get("oneOf") and contains_leafref(resolved):
            raise YangExportError(f"cannot safely project a union containing a leafref at '/{'/'.join(current)}'")
        musts = meta.get("must")
        if isinstance(musts, list):
            kept = []
            for item in musts:
                expression = item.get("must", "")
                if _within(expression, current, scope, module, item.get("xpath-prefixes", {})):
                    kept.append(item)
                else:
                    report(current, "must", expression)
            meta["must"] = kept
        when = meta.get("when")
        if isinstance(when, dict) and isinstance(when.get("condition"), str):
            expression = when["condition"]
            context = current[:-1] if when.get("evaluate-with-parent-context") else current
            if not _within(expression, context, scope, module, when.get("xpath-prefixes", {})):
                report(current, "when", expression)
                del meta["when"]
        # Typedefs may themselves carry a leafref; retain its definition at each use.
        ref = node.get("$ref", "")
        definition = full.get("$defs", {}).get(ref.removeprefix("#/$defs/"), {}) if ref.startswith("#/$defs/") else {}
        refmeta = definition.get("x-yang", {})
        if meta.get("type") == "leafref" or refmeta.get("type") == "leafref":
            if refmeta.get("type") == "leafref" and ref.startswith("#/$defs/"):
                typedef = module.typedefs.get(ref.removeprefix("#/$defs/"))
                type_path = getattr(getattr(typedef, "type", None), "path", None)
                if isinstance(type_path, PathNode) and not getattr(type_path, "source", None) and any(segment.predicate is not None for segment in type_path.segments):
                    raise YangExportError("cannot safely project a leafref typedef path with predicates")
            info = meta if meta.get("type") == "leafref" else refmeta
            expression = info.get("path", "")
            if not _supported_prefixes(expression, module, info.get("xpath-prefixes", {})):
                raise YangExportError(f"cannot resolve leafref '{expression}' outside module")
            target_path = _path_target(expression, current)
            target = _lookup(full, target_path)
            target_context = target_path
            seen: set[tuple[str, ...]] = set()
            while True:
                target_meta = target.get("x-yang", {})
                ref = target.get("$ref", "")
                if target_meta.get("type") != "leafref" and ref.startswith("#/$defs/"):
                    target_meta = full.get("$defs", {}).get(ref.removeprefix("#/$defs/"), {}).get("x-yang", {})
                if target_meta.get("type") != "leafref":
                    break
                key = tuple(target_context)
                if key in seen:
                    raise YangExportError(f"circular leafref '{expression}'")
                seen.add(key)
                next_path = target_meta.get("path", "")
                if not _supported_prefixes(next_path, module, target_meta.get("xpath-prefixes", {})):
                    raise YangExportError(f"cannot resolve leafref '{next_path}' outside module")
                target_context = _path_target(next_path, target_context)
                target = _lookup(full, target_context)
            for key in ("type", "$ref", "enum", "pattern", "minimum", "maximum", "minLength", "maxLength", "anyOf", "oneOf", "allOf", "format", "multipleOf"):
                node.pop(key, None)
                if key in target:
                    node[key] = deepcopy(target[key])
            try:
                _lookup(available, target_path)
                target_enabled = True
            except YangExportError:
                target_enabled = False
            if not _within(expression, current, scope, module, info.get("xpath-prefixes", {})) or not target_enabled:
                meta["type"] = "leaf"
                for key in ("path", "require-instance", "xpath-prefixes"):
                    meta.pop(key, None)
                report(current, "leafref", expression, "target is disabled by feature selection" if not target_enabled else "depends on data outside the selected subtree or cannot be proved local")
            else:
                meta.update(deepcopy(info))
            node["x-yang"] = meta
        for name, child in node.get("properties", {}).items():
            if isinstance(child, dict):
                visit(child, [*current, _local(name)])
        if isinstance(node.get("items"), dict):
            visit(node["items"], current)
        for key in ("oneOf", "anyOf", "allOf"):
            for branch in node.get(key, []):
                if isinstance(branch, dict):
                    visit(branch, current)
        if native_json and meta.get("type") == "list" and len(str(meta.get("key", "")).split()) == 1:
            item = node.pop("items")
            keyed_item = deepcopy(item)
            if isinstance(keyed_item.get("required"), list):
                keyed_item["required"] = [name for name in keyed_item["required"] if _local(name) != _local(meta["key"])]
            array = {"type": "array", "items": item}
            keyed = {"type": "object", "additionalProperties": keyed_item}
            for key, other in (("minItems", "minProperties"), ("maxItems", "maxProperties")):
                if key in node:
                    array[key] = node.pop(key)
                    keyed[other] = array[key]
            node.pop("type", None)
            node["anyOf"] = [array, keyed]

    visit(selected, scope)
    selected.setdefault("x-yang", {})["subtree-path"] = path
    selected["$schema"] = full["$schema"]
    selected["$id"] = full["$id"]
    if "$defs" in available:
        selected["$defs"] = available["$defs"]
    restrict(selected)
    _translate_patterns(selected)
    return SchemaExportResult(selected, diagnostics)
