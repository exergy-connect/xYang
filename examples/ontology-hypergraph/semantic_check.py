#!/usr/bin/env python3
"""Optional OWL RL evaluation of a deliberately small BFO alignment projection.

This is a partial semantic view, not a reversible serialization of the graph,
not the complete BFO-2020 axiomatization, and not an ISO conformity test.
"""

import argparse
import json
from pathlib import Path

from collector import ROOT, validate

BFO = "http://purl.obolibrary.org/obo/BFO_"
ALIGNMENTS = {
    "example-bfo:entity": BFO + "0000001",
    "example-bfo:continuant": BFO + "0000002",
    "example-bfo:occurrent": BFO + "0000003",
    "example-bfo:material-entity": BFO + "0000040",
    "example-bfo:process": BFO + "0000015",
}
DOMAIN_BASES = {
    "example-audit:engagement": "example-bfo:process",
    "example-audit:control": "example-bfo:continuant",
    "example-audit:evidence-record": "example-bfo:continuant",
    "example-audit:source-system": "example-bfo:continuant",
    "example-audit:employee": "example-bfo:material-entity",
    "example-audit:account": "example-bfo:continuant",
    "example-audit:termination-event": "example-bfo:process",
    "example-audit:account-use-event": "example-bfo:process",
    "example-audit:change-event": "example-bfo:process",
    "example-audit:collection-agent": "example-bfo:continuant",
    "example-audit:assessment-agent": "example-bfo:continuant",
    "example-audit:audit-professional": "example-bfo:material-entity",
}


def evaluate(tree):
    """Return (RDF graph, inferred inconsistency messages) using external OWL RL."""
    from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef
    from owlrl import DeductiveClosure, OWLRL_Semantics

    validate(tree)
    graph = Graph()
    alignments = dict(ALIGNMENTS)
    for node in tree[ROOT]["node"]:
        if "term" in node:
            if node["type"] not in DOMAIN_BASES or node["type"] in alignments:
                raise ValueError(f"Unsupported or duplicate domain term {node['type']!r}")
            alignments[node["type"]] = node["id"]
    if not set(DOMAIN_BASES) <= alignments.keys():
        raise ValueError("Semantic evaluation requires every published domain term definition")
    prov = Namespace("http://www.w3.org/ns/prov#")
    # Explicit, reviewable subset of BFO class relationships, plus local domain
    # subclass assertions. See README; full BFO temporal axioms are not included.
    for child, parent in (
        ("continuant", "entity"),
        ("occurrent", "entity"),
        ("material-entity", "continuant"),
        ("process", "occurrent"),
    ):
        graph.add(
            (URIRef(alignments["example-bfo:" + child]), RDFS.subClassOf, URIRef(alignments["example-bfo:" + parent]))
        )
    graph.add(
        (URIRef(alignments["example-bfo:continuant"]), OWL.disjointWith, URIRef(alignments["example-bfo:occurrent"]))
    )
    for child, parent in DOMAIN_BASES.items():
        graph.add((URIRef(alignments[child]), RDFS.subClassOf, URIRef(alignments[parent])))
    for node in tree[ROOT]["node"]:
        subject = URIRef(node["id"])
        graph.add((subject, prov.wasDerivedFrom, URIRef(node["origin"])))
        graph.add((subject, prov.wasAttributedTo, URIRef(node["asserted-by"])))
        graph.add((subject, RDFS.label, Literal(node["label"])))
        if "term" in node:
            term = node["term"]
            graph.add((subject, RDF.type, OWL.Class))
            graph.add((subject, RDFS.subClassOf, URIRef(term["bfo-class"])))
            graph.add((subject, RDFS.comment, Literal(term["definition"])))
        else:
            for identity in [node["type"], *node.get("also-type", [])]:
                if identity not in alignments:
                    raise ValueError(f"No semantic mapping for identity {identity!r}")
                graph.add((subject, RDF.type, URIRef(alignments[identity])))
    DeductiveClosure(OWLRL_Semantics).expand(graph)
    errors = sorted(
        str(message)
        for message in graph.objects(predicate=URIRef("http://www.daml.org/2002/03/agents/agent-ont#error"))
    )
    return graph, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projection", type=Path)
    parser.add_argument("--rdf", type=Path, help="Write the partial inferred semantic view as Turtle")
    args = parser.parse_args()
    graph, errors = evaluate(json.loads(args.projection.read_text()))
    if args.rdf:
        graph.serialize(destination=args.rdf, format="turtle")
    print(json.dumps({"scope": "BFO subclass/disjointness subset only", "errors": errors}, indent=2))
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
