#!/usr/bin/env python3
"""Resolve publications into a local RFC 7951 tree, then use xYang to validate it."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.request import urlopen

from xyang import YangValidator, parse_yang_file

HERE = Path(__file__).resolve().parent
REVISION = "2026-11-10"
MODULES = ("example-hypergraph", "example-bfo", "example-lab", "example-lab-evidence")
ROOT = "example-lab:graph"


class CollectionError(ValueError):
    """Publication, identity, version, or projected schema validation failed."""


def absolute(base: str, reference: str) -> str:
    if not isinstance(reference, str) or not reference:
        raise CollectionError("URL reference must be a nonempty string")
    result = urljoin(base, reference)
    parsed = urlsplit(result)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password:
        raise CollectionError(f"Expected an HTTP(S) URL: {result!r}")
    return result


def fetch(url: str) -> bytes:
    """Small demonstration HTTP client; fail on redirects to avoid identity aliasing."""
    try:
        with urlopen(url, timeout=10) as response:
            if response.geturl() != url:
                raise CollectionError(f"Redirect changes publication identity: {url}")
            data = response.read(2_000_001)
    except OSError as exc:
        raise CollectionError(f"Cannot fetch {url}: {exc}") from exc
    if len(data) > 2_000_000:
        raise CollectionError(f"Publication too large: {url}")
    return data


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CollectionError(f"Duplicate JSON member: {key}")
        result[key] = value
    return result


def decode(data: bytes):
    try:
        return json.loads(data, object_pairs_hook=_unique_object, parse_constant=lambda value: _bad_constant(value))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CollectionError(f"Invalid JSON: {exc}") from exc


def _bad_constant(value):
    raise CollectionError(f"Non-JSON number: {value}")


def model_inventory(base: str) -> list[dict]:
    """Expected revision and digest come from trusted bundled YANG, never remote code."""
    return [
        dict(
            name=name,
            revision=REVISION,
            location=urljoin(base, f"../models/{name}@{REVISION}.yang"),
            sha256=hashlib.sha256((HERE / "models" / f"{name}@{REVISION}.yang").read_bytes()).hexdigest(),
        )
        for name in MODULES
    ]


def validator() -> YangValidator:
    # Imports, grouping instantiation, refine constraints and augments are expanded
    # by xYang itself. No schema rewriting or JSON Schema approximation is needed.
    extension = parse_yang_file(HERE / "models" / f"example-lab-evidence@{REVISION}.yang")
    return YangValidator(extension.import_prefixes["lab"])


def validate(tree: dict) -> None:
    # xYang currently accepts lexical boolean strings as well as JSON booleans.
    # Enforce RFC 7951 section 6.3 for this profile's one boolean at the boundary.
    for edge in tree.get(ROOT, {}).get("hyperedge", []):
        key = "example-lab-evidence:reviewed"
        if key in edge and type(edge[key]) is not bool:
            raise CollectionError(f"RFC 7951 requires a JSON boolean for {key}")
    valid, errors, warnings = validator().validate(tree)
    if not valid or warnings:
        raise CollectionError("YANG validation failed:\n" + "\n".join(errors + warnings))


def _collect(seed: str, *, read=fetch, max_documents: int = 32) -> dict:
    """Follow dependencies and participant document URLs, normalize, merge and validate.

    `read` is injectable for offline fixtures. Only the documented URI-valued
    fields are normalized. Text attributes and unknown members are never dropped.
    """
    seed = absolute(seed, seed)
    if urldefrag(seed)[1]:
        raise CollectionError("Seed must be a document URL without fragment")
    pending = [seed]
    seen = set()
    claimed = set()
    graph = {"document": [], "node": [], "hyperedge": []}
    suite_version = None
    verified_models = set()
    while pending:
        url = pending.pop(0)
        if url in seen:
            continue
        if len(seen) >= max_documents:
            raise CollectionError("Document collection limit exceeded")
        seen.add(url)
        publication = decode(read(url))
        if not isinstance(publication, dict) or set(publication) != {ROOT}:
            raise CollectionError(f"Publication must contain only the RFC 7951 root {ROOT}: {url}")
        part = publication[ROOT]
        if not isinstance(part, dict) or set(part) - set(graph):
            raise CollectionError(f"Unknown graph members: {url}")
        part = copy.deepcopy(part)
        for key in graph:
            if not isinstance(part.get(key, []), list):
                raise CollectionError(f"{key} must be an RFC 7951 array: {url}")
        if len(part.get("document", [])) != 1:
            raise CollectionError(f"Exactly one publishing document entry required: {url}")
        doc = part["document"][0]
        doc["id"] = absolute(url, doc["id"])
        if doc["id"] != url:
            raise CollectionError(f"Document identity conflict: {url} claims {doc['id']}")
        if not doc.get("version") or not doc.get("ontology-version"):
            raise CollectionError(f"Missing version: {url}")
        if suite_version is None:
            suite_version = doc["ontology-version"]
        if doc["ontology-version"] != suite_version:
            raise CollectionError(f"Ontology version inconsistency: {url}")
        expected = {m["name"]: m for m in model_inventory(url)}
        models = doc.get("model", [])
        if not isinstance(models, list) or len(models) != len(expected):
            raise CollectionError(f"Effective model set mismatch: {url}")
        names = set()
        for model in models:
            name = model["name"]
            if name in names or name not in expected:
                raise CollectionError(f"Effective model identity conflict: {name}")
            names.add(name)
            model["location"] = absolute(url, model["location"])
            pin = expected[name]
            if model["revision"] != pin["revision"] or model["sha256"] != pin["sha256"]:
                raise CollectionError(f"Model version/digest inconsistency: {name}")
            source_key = (model["location"], model["sha256"])
            if source_key not in verified_models:
                if hashlib.sha256(read(model["location"])).hexdigest() != pin["sha256"]:
                    raise CollectionError(f"Published model digest mismatch: {name}")
                verified_models.add(source_key)
        for dependency in doc.get("requires", []):
            dependency["id"] = absolute(url, dependency["id"])
            ref = dependency["id"]
            if urldefrag(ref)[1]:
                raise CollectionError("Document dependency cannot have a fragment")
            pending.append(ref)
        graph["document"].append(doc)
        for kind in ("node", "hyperedge"):
            for element in part.get(kind, []):
                element["id"] = absolute(url, element["id"])
                source, fragment = urldefrag(element["id"])
                if source != url or not fragment:
                    raise CollectionError(f"Element identity must belong to its publication: {element['id']}")
                if element["id"] in claimed:
                    raise CollectionError(f"Element identity conflict: {element['id']}")
                claimed.add(element["id"])
                element["origin"] = absolute(url, element["origin"])
                if element["origin"] != url:
                    raise CollectionError(f"Origin conflicts with publication: {element['id']}")
                element["evidence"] = absolute(url, element["evidence"])
                for attachment in element.get("attachment", []):
                    attachment["url"] = absolute(url, attachment["url"])
                for incidence in element.get("incidence", []):
                    for target in ("node", "hyperedge"):
                        if target in incidence:
                            incidence[target] = absolute(url, incidence[target])
                            target_doc, target_id = urldefrag(incidence[target])
                            if not target_id:
                                raise CollectionError("Participant URL needs a fragment identifier")
                            pending.append(target_doc)
                graph[kind].append(element)
    versions = {doc["id"]: doc["version"] for doc in graph["document"]}
    for doc in graph["document"]:
        for dependency in doc.get("requires", []):
            if dependency["version"] != versions.get(dependency["id"]):
                raise CollectionError(f"Document version inconsistency: {dependency['id']}")
    tree = {ROOT: graph}
    validate(tree)
    return tree


def collect(seed: str, *, read=fetch, max_documents: int = 32) -> dict:
    """Collect or raise CollectionError, including malformed publication shapes."""
    try:
        return _collect(seed, read=read, max_documents=max_documents)
    except (KeyError, TypeError, AttributeError) as exc:
        raise CollectionError(f"Malformed publication: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Published seed JSON document URL")
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    try:
        tree = collect(args.url)
    except (CollectionError, KeyError, TypeError, ValueError) as exc:
        print(f"Collection failed: {exc}", file=sys.stderr)
        return 1
    text = json.dumps(tree, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
