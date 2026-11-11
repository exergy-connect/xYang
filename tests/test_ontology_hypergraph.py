"""Distributed audit-engagement hypergraph example; optional independent tools are opt-in dependencies."""

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

pytestmark = pytest.mark.ontology

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "ontology-hypergraph"
sys.path.insert(0, str(EXAMPLE))
spec = importlib.util.spec_from_file_location("ontology_collector", EXAMPLE / "collector.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)

ROOT = collector.ROOT
BASE = "http://ontology.test/documents/"
A = "example-audit:"


@pytest.fixture(scope="module")
def _publications_base():
    return {BASE + path.name: json.loads(path.read_text()) for path in (EXAMPLE / "documents").glob("*.json")}


@pytest.fixture
def publications(_publications_base):
    return copy.deepcopy(_publications_base)


def reader(publications, exports=None):
    def read(url):
        if url in publications:
            return json.dumps(publications[url]).encode()
        path = urlsplit(url).path
        if path.startswith("/models/"):
            return (EXAMPLE / "models" / Path(path).name).read_bytes()
        if "/exports/" in path:
            name = Path(path).name
            if exports and name in exports:
                return exports[name]
            return (EXAMPLE / "documents" / "exports" / name).read_bytes()
        raise collector.CollectionError("Missing publication: " + url)

    return read


def collect(publications, **kwargs):
    return collector.collect(BASE + "reviews.json", read=reader(publications, **kwargs))


def edges(publications, name):
    return publications[BASE + name][ROOT]["hyperedge"]


def edge(publications, name, fragment):
    return next(e for e in edges(publications, name) if e["id"] == "#" + fragment)


def node(publications, name, fragment):
    return next(n for n in publications[BASE + name][ROOT]["node"] if n["id"] == "#" + fragment)


def document(publications, name="evidence.json"):
    return publications[BASE + name][ROOT]["document"][0]


def projected(tree, fragment):
    return next(e for e in tree[ROOT]["hyperedge"] + tree[ROOT]["node"] if e["id"].endswith("#" + fragment))


def test_projection_has_engagement_records_with_provenance(publications):
    tree = collect(publications)
    graph = tree[ROOT]
    assert len(graph["document"]) == 4
    assert len(graph["node"]) == 47
    assert len(graph["hyperedge"]) == 11
    exception = projected(tree, "as-ac-01")
    assert exception["result"]["outcome"] == "exception"
    assert [i["node"] for i in exception["incidence"] if i["role"] == A + "cited-evidence"] == [
        BASE + "evidence.json#hr-leavers-q3",
        BASE + "evidence.json#iam-signins-q3",
    ]
    assert projected(tree, "as-cm-02")["result"]["outcome"] == "supported"
    assert projected(tree, "fd-ac-01")["incidence"][0]["hyperedge"] == exception["id"]
    record = projected(tree, "iam-signins-q3")["evidence-record"]
    assert record["source-system"] == BASE + "evidence.json#gatekeeper"
    assert record["export"] == BASE + "exports/iam-signins-q3.csv"
    use = projected(tree, "use-jmarsh")["account-use"]
    assert use["account"] == BASE + "evidence.json#jmarsh" and use["breach"] == "yes"
    assert projected(tree, "fd-ac-01")["incidence"][1]["node"] == BASE + "evidence.json#use-jmarsh"
    assert exception["origin"] == BASE + "assessments.json"
    assert exception["asserted-by"].endswith("/drafting-agent")
    assert projected(tree, "rv-ac-01")["sign-off"]["decision"] == "approved"


def test_unbounded_arity_and_repeated_participants(publications):
    incidence = edge(publications, "assessments.json", "as-ac-01")["incidence"]
    incidence.extend(
        {"id": f"repeat-{n}", "role": A + "cited-evidence", "node": "evidence.json#hr-leavers-q3"} for n in range(64)
    )
    assert len(projected(collect(publications), "as-ac-01")["incidence"]) == 69


def test_generic_allows_zero_arity_and_cycles(publications):
    bundle = edge(publications, "assessments.json", "wp-2026")
    bundle["incidence"] = []
    collect(publications)
    bundle["incidence"] = [{"id": "self", "role": A + "member", "hyperedge": "#wp-2026"}]
    collect(publications)


def _as(publications, fragment="as-cm-02"):
    return edge(publications, "assessments.json", fragment)


def _rv(publications, fragment="rv-cm-02"):
    return edge(publications, "reviews.json", fragment)


def _cited(e):
    return [i for i in e["incidence"] if i["role"] == A + "cited-evidence"]


@pytest.mark.parametrize(
    "change,match",
    [
        (lambda p: _cited(_as(p))[0].update(node="evidence.json#absent"), "Leafref"),
        (lambda p: _as(p).__setitem__("incidence", [i for i in _as(p)["incidence"] if i not in _cited(_as(p))]), "cite at least one"),
        (lambda p: _as(p)["incidence"].append(dict(_as(p)["incidence"][0], id="by-2")), "one assessor"),
        (lambda p: _as(p)["incidence"][1].update(node="catalogue.json#ac-01", id="ctl") or _as(p)["incidence"].append({"id": "ctl-2", "role": A + "assessed-control", "node": "catalogue.json#cm-02"}), "one control"),
        (lambda p: _as(p)["incidence"][0].update(node="catalogue.json#collector"), "practitioner"),
        (lambda p: _as(p)["incidence"][1].update(node="catalogue.json#term-control"), "control individual"),
        (lambda p: _cited(_as(p))[0].update(node="evidence.json#hr-leavers-q3"), "accepts"),
        (lambda p: _cited(_as(p))[0].update(node="evidence.json#peoplecore"), "evidence-record individual"),
        (lambda p: _as(p)["incidence"][0].update(role=A + "reviewer"), "one assessor"),
        (lambda p: _rv(p)["incidence"][0].update(node="catalogue.json#m-ito"), "must not be the assessor"),
        (lambda p: _rv(p)["incidence"][0].update(node="catalogue.json#drafting-agent"), "audit-professional"),
        (lambda p: _rv(p)["incidence"].append(dict(_rv(p)["incidence"][0], id="by-2")), "exactly one reviewer"),
        (lambda p: _rv(p)["incidence"][1].update(hyperedge="assessments.json#fd-ac-01"), "assessment hyperedge"),
        (lambda p: edge(p, "assessments.json", "fd-ac-01")["incidence"][0].update(hyperedge="#as-cm-02"), "outcome is exception"),
        (lambda p: edge(p, "evidence.json", "col-hr")["incidence"][0].update(node="catalogue.json#m-ito"), "collection-agent"),
        (lambda p: edge(p, "evidence.json", "col-hr")["incidence"].pop(1), "one source"),
        (lambda p: node(p, "evidence.json", "hr-leavers-q3")["evidence-record"].update(**{"source-system": "catalogue.json#m-ito"}), "source-system node"),
        (lambda p: node(p, "evidence.json", "hr-leavers-q3")["evidence-record"].update(**{"collected-at": "yesterday"}), "integer|uint32"),
        (lambda p: node(p, "evidence.json", "jmarsh")["account"].update(owner="#peoplecore"), "owner must be an employee"),
        (lambda p: node(p, "evidence.json", "term-e1043")["termination"].update(source="#jmarsh"), "source must be an evidence-record"),
        (lambda p: node(p, "evidence.json", "chg-chg-2207")["change"].pop("approved-at"), "approved-at"),
        (lambda p: _as(p)["result"].update(outcome="pass"), "enumeration|outcome"),
        (lambda p: _as(p).pop("result"), "outcome|result"),
        (lambda p: _as(p).pop("recorded-at"), "recorded-at"),
        (lambda p: _rv(p).update(**{"sign-off": {"decision": "maybe"}}), "enumeration|decision"),
        (lambda p: node(p, "catalogue.json", "cm-02")["control"].update(**{"accepted-evidence": []}), "accepted-evidence|min-elements"),
        (lambda p: _as(p)["incidence"][0].pop("node"), "[Cc]hoice"),
        (lambda p: _as(p)["incidence"][0].update(role=A + "control"), "identityref"),
        (lambda p: _as(p).update(type=A + "control"), "identityref"),
        (lambda p: _as(p)["incidence"][1].update(id="by"), "Duplicate"),
        (lambda p: _as(p).update(unknown="never drop this"), "Unknown field"),
        (lambda p: _as(p)["incidence"][0].update(role="audit:assessor"), "identityref"),
        (lambda p: _cited(_as(p))[0].update(node="missing.json#x"), "Missing publication"),
        (lambda p: _as(p).update(id="evidence.json#deploy-log-q3"), "identity"),
        (lambda p: _as(p).update(origin="evidence.json"), "Origin"),
    ],
)
def test_invalid_graphs_fail_loudly(publications, change, match):
    change(publications)
    with pytest.raises(collector.CollectionError, match=match):
        collect(publications)


def test_when_constraints_and_term_grouping(publications):
    bundle = edge(publications, "assessments.json", "wp-2026")
    bundle["result"] = {"outcome": "supported", "rationale": "not an assessment"}
    with pytest.raises(collector.CollectionError, match="when"):
        collect(publications)
    del bundle["result"]
    node(publications, "catalogue.json", "term-control")["term"].pop("definition")
    with pytest.raises(collector.CollectionError, match="definition"):
        collect(publications)


def test_insufficient_evidence_may_cite_nothing(publications):
    tree = collect(publications)
    assert [i for i in projected(tree, "as-ac-04")["incidence"] if i["role"] == A + "cited-evidence"] == []


def test_entity_identity_conflict_between_kinds(publications):
    publications[BASE + "assessments.json"][ROOT]["node"] = [
        dict(node(publications, "catalogue.json", "m-ito"), id="#as-ac-01", origin="assessments.json")
    ]
    with pytest.raises(collector.CollectionError, match="identity conflict"):
        collect(publications)


@pytest.mark.parametrize(
    "change,match",
    [
        (lambda p: document(p).update(id="catalogue.json"), "identity conflict"),
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
            BASE + "reviews.json", read=lambda url: b"module counterfeit {}" if "/models/" in url else original(url)
        )


def test_export_bytes_must_match_declared_digest(publications):
    with pytest.raises(collector.CollectionError, match="Export digest mismatch"):
        collect(publications, exports={"iam-signins-q3.csv": b"account,employee_id,signed_in_at\n"})


def test_cycles_in_document_dependencies_and_automatic_discovery(publications):
    # Participant links discover the catalogue and evidence locker without explicit dependencies.
    document(publications, "assessments.json").pop("requires")
    document(publications, "evidence.json").pop("requires")
    document(publications, "catalogue.json")["requires"] = [{"id": "reviews.json", "version": "1"}]
    assert len(collect(publications)[ROOT]["document"]) == 4


def test_collection_limits(publications):
    with pytest.raises(collector.CollectionError, match="limit"):
        collector.collect(BASE + "reviews.json", read=reader(publications), max_documents=1)


def test_json_encoding_arrays_namespace_and_duplicate_members(publications):
    bad = copy.deepcopy(publications)
    bad[BASE + "evidence.json"][ROOT]["node"] = {"x": {}}
    with pytest.raises(collector.CollectionError, match="array"):
        collect(bad)
    bad = copy.deepcopy(publications)
    bad[BASE + "evidence.json"]["audit:graph"] = bad[BASE + "evidence.json"].pop(ROOT)
    with pytest.raises(collector.CollectionError, match="RFC 7951 root"):
        collect(bad)
    for raw in (b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":Infinity}', b"no JSON"):
        with pytest.raises(collector.CollectionError):
            collector.decode(raw)


def test_leafrefs_are_enforced_after_projection(publications):
    tree = collect(publications)
    tree[ROOT]["node"] = [n for n in tree[ROOT]["node"] if not n["id"].endswith("#gatekeeper")]
    with pytest.raises(collector.CollectionError, match="Leafref"):
        collector.validate(tree)
    tree = collect(publications)
    tree[ROOT]["document"] = tree[ROOT]["document"][:1]
    with pytest.raises(collector.CollectionError, match="Leafref"):
        collector.validate(tree)


FIXTURES = EXAMPLE / "fixtures"
EXPECTED = json.loads((FIXTURES / "expected-errors.json").read_text())


@functools.cache
def _validator():
    return collector.validator()


def _errors(tree):
    result = _validator().validate_detailed(tree)
    return sorted(
        (e["path"].replace("/" + ROOT, ""), e["code"], e["message"] if e["code"] == "must" else None)
        for e in result["errors"]
    )


def test_checked_in_fixtures_fail_exactly_as_documented():
    assert _validator().validate_detailed(json.loads((FIXTURES / "valid.json").read_text()))["errors"] == []
    assert {p.stem for p in (FIXTURES / "invalid").glob("*.json")} == set(EXPECTED)
    for name, errors in EXPECTED.items():
        expected = sorted((e["path"], e["code"], e.get("message")) for e in errors)
        assert _errors(json.loads((FIXTURES / "invalid" / f"{name}.json").read_text())) == expected, name


def _valid():
    return json.loads((FIXTURES / "valid.json").read_text())


def test_equal_times_are_on_the_permitted_side():
    tree = _valid()
    # tquill signs in at the exact second the termination takes effect: not a breach.
    assert projected(tree, "use-tquill")["account-use"]["at"] == projected(tree, "term-e1058")["termination"]["effective-at"]
    assert projected(tree, "use-tquill")["account-use"]["breach"] == "no"
    # CHG-2241 is approved at the second it deploys: independent and prior enough.
    change = projected(tree, "chg-chg-2241")["change"]
    assert change["approved-at"] == change["deployed-at"] and change["breach"] == "no"
    engagement = projected(tree, "eng-2026")["engagement"]
    projected(tree, "iam-signins-q3")["evidence-record"]["collected-at"] = engagement["as-of"] - engagement["max-evidence-age"]
    projected(tree, "deploy-log-q3")["evidence-record"]["collected-at"] = projected(tree, "as-cm-02")["recorded-at"]
    projected(tree, "rv-cm-02")["recorded-at"] = projected(tree, "as-cm-02")["recorded-at"]
    projected(tree, "rv-ac-04")["recorded-at"] = engagement["as-of"]
    assert _errors(tree) == []


def test_breach_join_is_per_owner():
    tree = _valid()
    # Moving jmarsh's sign-in to before the termination removes the breach; the
    # still-declared yes then fails, and so does the exception that relied on it.
    projected(tree, "use-jmarsh")["account-use"]["at"] = projected(tree, "term-e1043")["termination"]["effective-at"] - 1
    assert ("/node/41/account-use/breach", "must", "breach must say whether the account owner's termination took effect before this use.") in _errors(tree)
    # Reassigning the terminated account to a never-terminated owner also removes it.
    tree = _valid()
    projected(tree, "jmarsh")["account"]["owner"] = "http://audit.test/documents/evidence.json#e0977"
    assert ("/node/41/account-use/breach", "must", "breach must say whether the account owner's termination took effect before this use.") in _errors(tree)


def test_change_exception_with_fact_grounded_finding_is_valid():
    tree = _valid()
    graph = tree[ROOT]
    base = "http://audit.test/documents/"
    change = projected(tree, "chg-chg-2241")["change"]
    change.update(approver=base + "evidence.json#e0912", breach="yes")
    projected(tree, "as-cm-02")["result"]["outcome"] = "exception"
    finding = copy.deepcopy(projected(tree, "fd-ac-01"))
    finding["id"] = base + "assessments.json#fd-cm-02"
    finding["incidence"] = [
        {"id": "basis", "role": A + "basis", "hyperedge": base + "assessments.json#as-cm-02"},
        {"id": "v", "role": A + "violation", "node": base + "evidence.json#chg-chg-2241"},
        {"id": "ev", "role": A + "cited-evidence", "node": base + "evidence.json#change-tickets-q3"},
    ]
    graph["hyperedge"].append(finding)
    assert _errors(tree) == []
    # The same finding without the ticket export it was taken from is rejected.
    finding["incidence"][2]["node"] = base + "evidence.json#deploy-log-q3"
    assert ("/hyperedge/11/incidence/1", "must", "A finding must cite the evidence its violation was taken from.") in _errors(tree)


def test_real_http_publication_and_cli(tmp_path):
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass

    handler = functools.partial(QuietHandler, directory=str(EXAMPLE))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}/documents/"
        try:
            output = tmp_path / "projection.json"
            result = subprocess.run(
                [sys.executable, str(EXAMPLE / "collector.py"), base + "reviews.json", "-o", str(output)],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr
            tree = json.loads(output.read_text())
            assert projected(tree, "fd-ac-01")["id"] == base + "assessments.json#fd-ac-01"
            with pytest.raises(collector.CollectionError, match="Cannot fetch"):
                collector.fetch(base + "reviews.json.missing")
        finally:
            server.shutdown()
            thread.join()


def test_fixtures_are_reproducible():
    paths = [*(EXAMPLE / "documents").rglob("*.json"), *(EXAMPLE / "documents" / "exports").glob("*.csv")]
    paths += [*FIXTURES.rglob("*.json"), EXAMPLE / "yang-library.json", EXAMPLE / "yangson-library.json"]
    before = {path: path.read_bytes() for path in paths}
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
    model.from_raw(collect(publications)).validate()
    for name in EXPECTED:
        with pytest.raises(YangsonException):
            model.from_raw(json.loads((FIXTURES / "invalid" / f"{name}.json").read_text())).validate()

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
    projected(tree, "iam-signins-q3")["also-type"] = ["example-bfo:occurrent"]
    collector.validate(tree)
    _, errors = evaluate(tree)
    assert errors and any("disjoint" in error.lower() for error in errors)


def test_client_hosted_evidence_on_another_origin(publications):
    client = "https://evidence.alder-ridge.example/locker/"
    publications[client + "evidence.json"] = publications.pop(BASE + "evidence.json")
    document(publications, "assessments.json")["requires"][0]["id"] = client + "evidence.json"
    for e in edges(publications, "assessments.json"):
        for inc in e["incidence"]:
            if "node" in inc and inc["node"].startswith("evidence.json"):
                inc["node"] = client + inc["node"]
    evidence = publications[client + "evidence.json"][ROOT]
    for item in evidence["node"] + evidence["hyperedge"]:
        for inc in item.get("incidence", []):
            if inc["node"].startswith("catalogue.json"):
                inc["node"] = BASE + inc["node"]
    evidence["document"][0]["requires"][0]["id"] = BASE + "catalogue.json"
    tree = collect(publications)
    assert projected(tree, "iam-signins-q3")["origin"] == client + "evidence.json"
    assert projected(tree, "iam-signins-q3")["evidence-record"]["export"] == client + "exports/iam-signins-q3.csv"
    assert projected(tree, "use-jmarsh")["account-use"]["account"] == client + "evidence.json#jmarsh"


def test_review_of_assessment_in_another_document_must_resolve(publications):
    _rv(publications)["incidence"][1]["hyperedge"] = "assessments.json#absent"
    with pytest.raises(collector.CollectionError, match="Leafref"):
        collect(publications)


def test_projection_does_not_modify_publications(publications):
    before = copy.deepcopy(publications)
    collect(publications)
    assert publications == before


@pytest.mark.parametrize(
    "value", ["file:///tmp/ontology.json", "ftp://example.org/ontology.json", BASE + "evidence.json#hr-leavers-q3"]
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
