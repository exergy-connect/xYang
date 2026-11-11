#!/usr/bin/env python3
"""Regenerate deterministic fixtures and schema inventory from the source YANG."""

import hashlib
import json

from collector import HERE, MODULES, REVISION, ROOT, model_inventory


def write(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def publication(name, **content):
    # Relative URI references make the same publications usable on any HTTP origin.
    models = model_inventory("http://example.test/documents/" + name)
    for model in models:
        model["location"] = "../models/" + model["name"] + "@" + REVISION + ".yang"
    return {
        ROOT: {"document": [{"id": name, "version": "1", "ontology-version": "lab-2026.1", "model": models}], **content}
    }


def provenance(document):
    return dict(origin=document, **{"asserted-by": "https://example.org/agents/lab", "evidence": "evidence.txt"})


def build():
    terms = publication(
        "terms.json",
        node=[
            {
                "id": "#specimen",
                "label": "specimen",
                "type": "example-lab:specimen",
                "term": {
                    "definition": "A material sample examined in a laboratory.",
                    "bfo-class": "http://purl.obolibrary.org/obo/BFO_0000040",
                },
                **provenance("terms.json"),
            },
            {
                "id": "#assay",
                "label": "assay",
                "type": "example-lab:assay",
                "term": {
                    "definition": "A process that examines a specimen.",
                    "bfo-class": "http://purl.obolibrary.org/obo/BFO_0000015",
                },
                **provenance("terms.json"),
            },
        ],
    )
    entities = publication(
        "entities.json",
        node=[
            {
                "id": "#" + name,
                "label": name,
                "type": kind,
                "attribute": [{"name": "https://example.org/vocab/batch", "value": "B-17"}],
                **provenance("entities.json"),
            }
            for name, kind in (
                ("sample", "example-lab:specimen"),
                ("product", "example-lab:specimen"),
                ("assay", "example-lab:assay"),
            )
        ],
    )
    entities[ROOT]["document"][0]["requires"] = [{"id": "terms.json", "version": "1"}]
    relations = publication(
        "relations.json",
        hyperedge=[
            {
                "id": "#reaction",
                "type": "example-lab:reaction",
                **provenance("relations.json"),
                "experiment": {"accession": "EXP-17"},
                "example-lab-evidence:reviewed": True,
                "attachment": [{"url": "evidence.txt", "media-type": "text/plain", "purpose": "Observation log"}],
                "incidence": [
                    {"id": "i1", "role": "example-lab:input", "node": "entities.json#sample"},
                    {"id": "i2", "role": "example-lab:input", "node": "entities.json#sample"},
                    {"id": "o1", "role": "example-lab:output", "node": "entities.json#product"},
                    {"id": "c1", "role": "example-lab:context", "node": "entities.json#assay"},
                ],
            },
            {
                "id": "#bundle",
                "type": "example-lab:bundle",
                **provenance("relations.json"),
                "incidence": [{"id": "m1", "role": "example-lab:member", "hyperedge": "#reaction"}],
            },
        ],
    )
    relations[ROOT]["document"][0]["requires"] = [{"id": "entities.json", "version": "1"}]
    for name, value in (("terms.json", terms), ("entities.json", entities), ("relations.json", relations)):
        write("documents/" + name, value)
    modules = [
        {"name": name, "revision": REVISION, "namespace": "urn:example:" + suffix}
        for name, suffix in zip(MODULES, ("hypergraph", "bfo", "lab", "lab-evidence"))
    ]
    # RFC 8525 inventory for this static publication. There are no NETCONF/NMDA
    # datastores. All four modules participate in the active schema/vocabulary.
    library = {
        "module-set": [{"name": "lab-2026.1", "module": modules}],
        "schema": [{"name": "lab", "module-set": ["lab-2026.1"]}],
    }
    library["content-id"] = hashlib.sha256(json.dumps(library, sort_keys=True).encode()).hexdigest()
    write("yang-library.json", {"ietf-yang-library:yang-library": library})
    # Yangson 1.7 uses the deprecated RFC 7895 input form for schema loading.
    write(
        "yangson-library.json",
        {
            "ietf-yang-library:modules-state": {
                "module-set-id": library["content-id"],
                "module": [{**module, "conformance-type": "implement"} for module in modules],
            }
        },
    )


if __name__ == "__main__":
    build()
