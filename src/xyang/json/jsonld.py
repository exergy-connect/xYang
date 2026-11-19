"""JSON-LD projections of the canonical native form; no network access or model mutation."""

from __future__ import annotations

import re
from typing import Any

from ..errors import YangExportError
from ..module import YangModule
from .generator import generate_json_schema

PREFIXES = {
    "schema": "https://schema.org/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "wd": "http://www.wikidata.org/entity/",
}
_LEGACY = {
    "schema-org-property": "iri",
    "schema-org-class": "class",
    "wikidata": "close-match",
    "unit-code": "unit-code",
}


def _namespace(namespace: str) -> str:
    return namespace if namespace.endswith(("#", "/", ":")) else namespace + "#"


class _Builder:
    def __init__(self, schema: dict[str, Any]):
        self.schema = schema
        self.xy = schema["x-yang"]
        self.module = self.xy["module"]
        self.base = _namespace(self.xy.get("namespace") or f"urn:{self.module}")
        self.namespaces = {self.module: self.base}
        self.owners = {self.xy["prefix"]: self.module}
        for prefix, stub in self.xy.get("imports", {}).items():
            self.namespaces[stub["module"]] = _namespace(stub.get("namespace") or f'urn:{stub["module"]}')
            self.owners[prefix] = stub["module"]
        self.graph: dict[str, dict[str, Any]] = {}

    def iri(self, value: str) -> str:
        prefix, sep, rest = value.partition(":")
        if sep and prefix in PREFIXES:
            value = PREFIXES[prefix] + rest
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*:[^\s]+", value):
            raise YangExportError(f"JSON-LD mapping must be an absolute IRI: {value!r}")
        return value

    def mappings(self, node: dict) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for ext in node.get("x-yang", {}).get("extensions", []):
            prefix, _, name = ext["name"].partition(":")
            standard = self.owners.get(prefix) == "xyang-jsonld"
            key = name if standard else _LEGACY.get(name)
            if key not in ("iri", "iri-value", "class", "close-match", "unit-code"):
                continue
            argument = ext.get("argument", "")
            if key != "iri-value" and not argument:
                raise YangExportError(f"JSON-LD {key} mapping requires a non-empty argument")
            if key == "iri-value":
                value: Any = True
            elif key == "unit-code":
                value = argument
            else:
                if name in ("schema-org-property", "schema-org-class") and ":" not in argument:
                    argument = PREFIXES["schema"] + argument
                if name == "wikidata" and re.fullmatch(r"Q[0-9]+", argument):
                    argument = PREFIXES["wd"] + argument
                value = argument if key == "iri" and argument in ("@id", "@type") else self.iri(argument)
            if key == "close-match":
                out.setdefault(key, []).append(value)
            elif key in out and out[key] != value:
                raise YangExportError(f"Conflicting JSON-LD {key} mappings")
            else:
                out[key] = value
            if name == "schema-org-property" and argument == PREFIXES["schema"] + "url":
                out["iri-value"] = True
        return out

    def resolve(self, node: dict, seen: frozenset[str] = frozenset()) -> dict:
        ref = node.get("$ref")
        if not ref:
            return node
        if not ref.startswith("#/$defs/") or ref in seen:
            raise YangExportError(f"Unsupported or recursive JSON-LD schema reference: {ref}")
        key = ref[len("#/$defs/") :].replace("~1", "/").replace("~0", "~")
        target = self.schema.get("$defs", {}).get(key)
        if not isinstance(target, dict):
            raise YangExportError(f"Unresolved JSON-LD schema reference: {ref}")
        return {**self.resolve(target, seen | {ref}), **{k: v for k, v in node.items() if k != "$ref"}}

    def properties(self, shape: dict) -> list[tuple[str, dict]]:
        shape = self.resolve(shape)
        out = list(shape.get("properties", {}).items())
        for key in ("oneOf", "anyOf", "allOf"):
            for branch in shape.get(key, []):
                out.extend(self.properties(branch))
        return out

    def record(self, iri: str, name: str, node: dict, mapping: dict) -> None:
        if iri.startswith("@"):
            return
        record = self.graph.setdefault(iri, {"@id": iri, "@type": "rdf:Property", "rdfs:label": name})
        values = {"rdfs:label": name}
        if node.get("description"):
            values["rdfs:comment"] = node["description"]
        units = mapping.get("unit-code") or node.get("x-yang", {}).get("units")
        if units:
            values["schema:unitCode"] = units
        if mapping.get("class"):
            values["rdfs:range"] = {"@id": mapping["class"]}
        if mapping.get("close-match"):
            values["skos:closeMatch"] = [{"@id": iri} for iri in mapping["close-match"]]
        for key, value in values.items():
            if key not in record:
                record[key] = value
            elif record[key] != value:
                old = record[key] if isinstance(record[key], list) else [record[key]]
                new = value if isinstance(value, list) else [value]
                record[key] = old + [v for v in new if v not in old]

    def terms(self, shape: dict, parent_module: str, depth: int = 0) -> dict:
        if depth > 128:
            raise YangExportError("JSON-LD context nesting exceeds 128 levels")
        context = {}
        for key, raw in self.properties(shape):
            node = self.resolve(raw)
            owner, sep, local = key.partition(":")
            if not sep:
                owner, local = parent_module, key
            if owner not in self.namespaces:
                raise YangExportError(f"JSON-LD namespace is missing for module {owner!r}")
            mapping = self.mappings(node)
            iri = mapping.get("iri") or self.namespaces[owner] + local
            term: dict = {"@id": iri}
            if mapping.get("iri-value") and iri.startswith("@"):
                raise YangExportError("JSON-LD keyword aliases cannot have value coercion")
            if mapping.get("iri-value"):
                term["@type"] = "@id"
            kind = node.get("x-yang", {}).get("type")
            if kind in ("container", "list"):
                child = node.get("items", {}) if kind == "list" else node
                term["@context"] = self.terms(child, owner, depth + 1)
                if iri.startswith("@"):
                    raise YangExportError("JSON-LD keyword aliases cannot have child contexts")
            if sep and iri != self.namespaces[owner] + local:
                raise YangExportError(f"JSON-LD cannot remap compact-IRI member {key!r}; use unqualified members")
            if key in context and context[key] != term:
                raise YangExportError(f"Conflicting JSON-LD term {key!r} across choice branches")
            context[key] = term
            self.record(iri, local, node, mapping)
        return context

    def build(self) -> tuple[dict, dict]:
        terms = self.terms(self.schema, self.module)
        context = {"@version": 1.1, "@vocab": self.base}
        for owner, namespace in self.namespaces.items():
            if owner not in terms:
                context[owner] = {"@id": namespace, "@prefix": True}
        context.update(terms)
        vocab = {"@context": {"@version": 1.1, **PREFIXES}, "@graph": [self.graph[key] for key in sorted(self.graph)]}
        return {"@context": context}, vocab


def generate_jsonld_context(module: YangModule) -> dict[str, Any]:
    """Generate a JSON-LD 1.1 context with scoped terms and explicit IRI mappings."""
    return _Builder(generate_json_schema(module).schema).build()[0]


def generate_jsonld_vocab(module: YangModule) -> dict[str, Any]:
    """Generate RDF property descriptions with class, close-match, and unit links."""
    return _Builder(generate_json_schema(module).schema).build()[1]
