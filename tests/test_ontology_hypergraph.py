"""Self-contained distributed ontology example; optional independent tools are opt-in dependencies."""

from __future__ import annotations

import copy
import functools
import importlib.util
import json
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "ontology-hypergraph"
spec = importlib.util.spec_from_file_location("ontology_collector", EXAMPLE / "collector.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
ROOT = collector.ROOT
BASE = "http://ontology.test/documents/"


@pytest.fixture
def publications():
    return {BASE + path.name: json.loads(path.read_text()) for path in (EXAMPLE / "documents").glob("*.json")}


def reader(publications):
    def read(url):
        if url in publications:
            return json.dumps(publications[url]).encode()
        if urlsplit(url).path.startswith("/models/"):
            return (EXAMPLE / "models" / Path(urlsplit(url).path).name).read_bytes()
        raise collector.CollectionError("Missing publication: " + url)

    return read


def collect(publications):
    return collector.collect(BASE + "relations.json", read=reader(publications))


def edge(publications):
    return publications[BASE + "relations.json"][ROOT]["hyperedge"][0]


def document(publications, name="entities.json"):
    return publications[BASE + name][ROOT]["document"][0]


def test_projection_preserves_identity_occurrences_provenance_and_extensions(publications):
    tree = collect(publications)
    graph = tree[ROOT]
    assert len(graph["document"]) == 3
    assert len(graph["node"]) == 5
    reaction, bundle = graph["hyperedge"]
    assert reaction["id"] == BASE + "relations.json#reaction"
    assert [i["node"] for i in reaction["incidence"][:2]] == [BASE + "entities.json#sample"] * 2
    assert bundle["incidence"][0]["hyperedge"] == reaction["id"]
    assert reaction["origin"] == BASE + "relations.json"
    assert reaction["asserted-by"] == "https://example.org/agents/lab"
    assert reaction["evidence"] == BASE + "evidence.txt"
    assert reaction["attachment"][0]["url"] == BASE + "evidence.txt"
    assert reaction["experiment"] == {"accession": "EXP-17"}
    assert reaction["example-lab-evidence:reviewed"] is True
    assert graph["node"][0]["attribute"][0]["value"] == "B-17"
    assert graph["node"][-2]["term"]["bfo-class"].endswith("BFO_0000040")


def test_unbounded_arity_and_repeated_participants(publications):
    incidence = edge(publications)["incidence"]
    incidence.extend(
        {"id": f"repeat-{n}", "role": "example-lab:input", "node": "entities.json#sample"} for n in range(64)
    )
    assert len(collect(publications)[ROOT]["hyperedge"][0]["incidence"]) == 68


def test_generic_allows_zero_arity_and_cycles(publications):
    bundle = publications[BASE + "relations.json"][ROOT]["hyperedge"][1]
    bundle["incidence"] = []
    collect(publications)
    bundle["incidence"] = [{"id": "self", "role": "example-lab:member", "hyperedge": "#bundle"}]
    collect(publications)


@pytest.mark.parametrize(
    "change,match",
    [
        (lambda e: e["incidence"].pop(2), "exactly one output"),
        (
            lambda e: e["incidence"].append(
                {"id": "extra", "role": "example-lab:output", "node": "entities.json#product"}
            ),
            "exactly one output",
        ),
        (lambda e: e["incidence"][0].update(role="example-lab:member"), "only input/output/context"),
        (lambda e: e["incidence"][0].update(node="entities.json#assay"), "material-entity"),
        (lambda e: e["incidence"][0].update(node="terms.json#specimen"), "material-entity"),
        (lambda e: e["incidence"][0].update(node="entities.json#absent"), "Leafref"),
        (lambda e: e["incidence"][0].update(hyperedge="#bundle"), "[Cc]hoice"),
        (lambda e: e["incidence"][0].pop("node"), "choice"),
        (lambda e: e["incidence"][0].update(role="example-lab:specimen"), "identityref"),
        (lambda e: e.update(type="example-lab:specimen"), "identityref"),
        (lambda e: e["incidence"][1].update(id="i1"), "Duplicate"),
        (lambda e: e.update(unknown="never drop this"), "Unknown field"),
        (lambda e: e.update(reviewed=True), "Unknown field"),
        (lambda e: e.update(**{"example-lab-evidence:reviewed": "true"}), "boolean"),
        (lambda e: e["incidence"][0].update(role="lab:input"), "identityref"),
        (lambda e: e["incidence"][0].update(node="missing.json#sample"), "Missing publication"),
        (lambda e: e.update(id="entities.json#sample"), "identity"),
        (lambda e: e.update(origin="entities.json"), "Origin"),
    ],
)
def test_invalid_graphs_fail_loudly(publications, change, match):
    change(edge(publications))
    with pytest.raises(collector.CollectionError, match=match):
        collect(publications)


def test_no_inputs_rejected(publications):
    edge(publications)["incidence"] = edge(publications)["incidence"][2:]
    with pytest.raises(collector.CollectionError, match="inputs"):
        collect(publications)


def test_when_constraint_and_term_grouping(publications):
    bundle = publications[BASE + "relations.json"][ROOT]["hyperedge"][1]
    bundle["experiment"] = {"accession": "not-a-reaction"}
    with pytest.raises(collector.CollectionError, match="when"):
        collect(publications)
    del bundle["experiment"]
    publications[BASE + "terms.json"][ROOT]["node"][0]["term"].pop("definition")
    with pytest.raises(collector.CollectionError, match="definition"):
        collect(publications)


def test_entity_identity_conflict_between_kinds(publications):
    relations = publications[BASE + "relations.json"][ROOT]
    relations["node"] = [
        {
            "id": "#reaction",
            "label": "collision",
            "type": "example-lab:specimen",
            "origin": "relations.json",
            "asserted-by": "https://example.org/lab",
            "evidence": "evidence.txt",
        }
    ]
    with pytest.raises(collector.CollectionError, match="identity conflict"):
        collect(publications)


@pytest.mark.parametrize(
    "change,match",
    [
        (lambda p: document(p).update(id="terms.json"), "identity conflict"),
        (lambda p: document(p).update(**{"ontology-version": "other"}), "Ontology version"),
        (lambda p: document(p).update(version="2"), "Document version"),
        (lambda p: document(p)["model"][0].update(revision="1999-01-01"), "Model version"),
        (lambda p: document(p)["model"][0].update(sha256="0" * 64), "digest"),
        (lambda p: document(p)["model"].pop(), "model set"),
        (lambda p: document(p)["model"].__setitem__(1, copy.deepcopy(document(p)["model"][0])), "model identity"),
    ],
)
def test_publication_versions_and_inventory(publications, change, match):
    change(publications)
    with pytest.raises(collector.CollectionError, match=match):
        collect(publications)


def test_served_model_bytes_must_match_trusted_schema(publications):
    original = reader(publications)
    with pytest.raises(collector.CollectionError, match="Published model digest"):
        collector.collect(
            BASE + "relations.json", read=lambda url: b"module counterfeit {}" if "/models/" in url else original(url)
        )


def test_cycles_in_document_dependencies_and_automatic_discovery(publications):
    # No explicit dependency for the entity document: participant links discover it.
    document(publications, "relations.json").pop("requires")
    document(publications, "terms.json")["requires"] = [{"id": "relations.json", "version": "1"}]
    assert len(collect(publications)[ROOT]["document"]) == 3


def test_collection_limits(publications):
    with pytest.raises(collector.CollectionError, match="limit"):
        collector.collect(BASE + "relations.json", read=reader(publications), max_documents=1)


def test_json_encoding_arrays_namespace_and_duplicate_members(publications):
    bad = copy.deepcopy(publications)
    bad[BASE + "entities.json"][ROOT]["node"] = {"sample": {}}
    with pytest.raises(collector.CollectionError, match="array"):
        collect(bad)
    bad = copy.deepcopy(publications)
    bad[BASE + "entities.json"]["lab:graph"] = bad[BASE + "entities.json"].pop(ROOT)
    with pytest.raises(collector.CollectionError, match="RFC 7951 root"):
        collect(bad)
    for raw in (b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":Infinity}', b"no JSON"):
        with pytest.raises(collector.CollectionError):
            collector.decode(raw)


def test_leafrefs_are_enforced_after_projection(publications):
    tree = collect(publications)
    tree[ROOT]["node"] = []
    with pytest.raises(collector.CollectionError, match="Leafref"):
        collector.validate(tree)
    tree = collect(publications)
    tree[ROOT]["document"] = tree[ROOT]["document"][:1]
    with pytest.raises(collector.CollectionError, match="Leafref"):
        collector.validate(tree)


def test_real_http_publication_and_cli(tmp_path):
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass

    handler = functools.partial(QuietHandler, directory=str(EXAMPLE))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        seed = f"http://127.0.0.1:{server.server_port}/documents/relations.json"
        try:
            output = tmp_path / "projection.json"
            result = subprocess.run(
                [sys.executable, str(EXAMPLE / "collector.py"), seed, "-o", str(output)], capture_output=True, text=True
            )
            assert result.returncode == 0, result.stderr
            tree = json.loads(output.read_text())
            assert tree[ROOT]["hyperedge"][0]["id"] == seed + "#reaction"
            with pytest.raises(collector.CollectionError, match="Cannot fetch"):
                collector.fetch(seed + ".missing")
        finally:
            server.shutdown()
            thread.join()


def test_fixtures_are_reproducible():
    before = {path: path.read_bytes() for path in (EXAMPLE / "documents").glob("*.json")}
    for name in ("yang-library.json", "yangson-library.json"):
        before[EXAMPLE / name] = (EXAMPLE / name).read_bytes()
    subprocess.run([sys.executable, str(EXAMPLE / "build_fixtures.py")], check=True)
    assert before == {path: path.read_bytes() for path in before}


def test_independent_yang_tools(publications):
    pytest.importorskip("pyang")
    pytest.importorskip("yangson")
    from yangson.datamodel import DataModel
    from yangson.exceptions import YangsonException

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pyang",
            "--lint",
            "-p",
            str(EXAMPLE / "models"),
            *map(str, sorted((EXAMPLE / "models").glob("*.yang"))),
        ],
        check=True,
    )
    model = DataModel.from_file(str(EXAMPLE / "yangson-library.json"), [str(EXAMPLE / "models")])
    tree = collect(publications)
    model.from_raw(tree).validate()
    # Independent evidence for the same negative constraints.
    for mutation in (
        lambda t: t[ROOT]["hyperedge"][0]["incidence"].pop(2),
        lambda t: t[ROOT]["hyperedge"][0]["incidence"][0].update(node=BASE + "entities.json#assay"),
        lambda t: t[ROOT]["hyperedge"][0]["incidence"][0].update(node=BASE + "entities.json#missing"),
        lambda t: t[ROOT]["hyperedge"][0].update(reviewed=True),
        lambda t: t[ROOT]["hyperedge"][0].update(**{"example-lab-evidence:reviewed": "true"}),
    ):
        bad = copy.deepcopy(tree)
        mutation(bad)
        with pytest.raises(YangsonException):
            model.from_raw(bad).validate()

    # Reuse the repository's official IETF modules to check the published modern
    # inventory, independently of the compatibility file used to load our model.
    from yangson.enumerations import ContentType

    standards = EXAMPLE.parent / "ietf-yang-push" / "modules"
    revisions = (
        ("ietf-yang-library", "2019-01-04"),
        ("ietf-yang-types", "2013-07-15"),
        ("ietf-inet-types", "2013-07-15"),
        ("ietf-datastores", "2018-02-14"),
    )
    library_schema = {
        "ietf-yang-library:modules-state": {
            "module-set-id": "rfc8525",
            "module": [
                {
                    "name": name,
                    "revision": revision,
                    "namespace": "urn:ietf:params:xml:ns:yang:" + name,
                    "conformance-type": "implement",
                }
                for name, revision in revisions
            ],
        }
    }
    inventory = json.loads((EXAMPLE / "yang-library.json").read_text())
    DataModel(json.dumps(library_schema), [str(standards)]).from_raw(inventory).validate(ctype=ContentType.all)


def test_optional_semantic_evaluation_is_separate(publications, monkeypatch):
    pytest.importorskip("owlrl")
    monkeypatch.syspath_prepend(str(EXAMPLE))
    from semantic_check import evaluate

    tree = collect(publications)
    _, errors = evaluate(tree)
    assert not errors
    # Structurally legal classifications can still contradict BFO disjointness.
    tree[ROOT]["node"][0]["also-type"] = ["example-bfo:occurrent"]
    collector.validate(tree)
    _, errors = evaluate(tree)
    assert errors and any("disjoint" in error.lower() for error in errors)


def test_references_across_origins(publications):
    remote = "https://second-publisher.test/documents/"
    for name in ("entities.json", "terms.json"):
        publications[remote + name] = publications.pop(BASE + name)
    document(publications, "relations.json")["requires"][0]["id"] = remote + "entities.json"
    for incidence in edge(publications)["incidence"]:
        incidence["node"] = remote + incidence["node"]
    tree = collect(publications)
    assert tree[ROOT]["hyperedge"][0]["incidence"][0]["node"] == remote + "entities.json#sample"
    assert {node["origin"] for node in tree[ROOT]["node"]} == {remote + "entities.json", remote + "terms.json"}


def test_nested_hyperedge_in_another_document(publications):
    original = publications[BASE + "relations.json"]
    bundle = original[ROOT]["hyperedge"].pop()
    publication = copy.deepcopy(original)
    publication[ROOT]["document"][0]["id"] = "bundle.json"
    publication[ROOT]["hyperedge"] = [bundle]
    bundle["origin"] = "bundle.json"
    bundle["incidence"][0]["hyperedge"] = "relations.json#reaction"
    publications[BASE + "bundle.json"] = publication
    tree = collector.collect(BASE + "bundle.json", read=reader(publications))
    assert len(tree[ROOT]["document"]) == 4
    assert tree[ROOT]["hyperedge"][0]["incidence"][0]["hyperedge"] == BASE + "relations.json#reaction"
    bundle["incidence"][0]["hyperedge"] = "relations.json#absent"
    with pytest.raises(collector.CollectionError, match="Leafref"):
        collector.collect(BASE + "bundle.json", read=reader(publications))


def test_projection_does_not_modify_publications(publications):
    before = copy.deepcopy(publications)
    collect(publications)
    assert publications == before


@pytest.mark.parametrize(
    "value", ["file:///tmp/ontology.json", "ftp://example.org/ontology.json", BASE + "entities.json#sample"]
)
def test_invalid_seed_references(value):
    with pytest.raises(collector.CollectionError):
        collector.collect(value)


def test_generic_grouping_has_no_bfo_dependency(tmp_path):
    from xyang import YangValidator, parse_yang_file

    host = tmp_path / "plain.yang"
    host.write_text("""module plain {
      yang-version 1.1; namespace "urn:plain"; prefix p;
      import example-hypergraph { prefix hg; revision-date 2026-11-10; }
      identity thing { base hg:element-kind; }
      identity relation { base hg:relation; }
      identity participant { base hg:role; }
      container graph { uses hg:hypergraph; }
    }""")
    module = parse_yang_file(host, include_path=(str(EXAMPLE / "models"),))
    assert set(module.import_prefixes) == {"hg"}
    source = "https://plain.test/data.json"
    provenance = {"origin": source, "asserted-by": "https://plain.test/agent", "evidence": source}
    tree = {
        "plain:graph": {
            "document": [
                {
                    "id": source,
                    "version": "1",
                    "ontology-version": "plain-1",
                    "model": [collector.model_inventory(BASE)[0]],
                }
            ],
            "node": [{"id": source + "#n", "type": "plain:thing", "label": "arbitrary", **provenance}],
            "hyperedge": [
                {
                    "id": source + "#e",
                    "type": "plain:relation",
                    **provenance,
                    "incidence": [{"id": str(n), "role": "plain:participant", "node": source + "#n"} for n in range(5)],
                }
            ],
        }
    }
    valid, errors, warnings = YangValidator(module).validate(tree)
    assert valid and not warnings, errors + warnings
