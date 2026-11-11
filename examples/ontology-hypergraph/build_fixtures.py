#!/usr/bin/env python3
"""Regenerate the synthetic audit publications, exports, projections, and schema inventory.

All names, people, systems, and records are fictional.
"""

import copy
import hashlib
import json

from collector import HERE, MODULES, REVISION, ROOT, collect, model_inventory

FIXTURE_BASE = "http://audit.test/documents/"
SUITE = "audit-2026.1"
FIRM = "https://larkspur-reed.example/agents/"

EXPORTS = {
    "hr-leavers-q3.csv": (
        "employee_id,name,termination_date\n"
        "E1031,R. Vance,2026-07-03\n"
        "E1043,J. Marsh,2026-08-14\n"
        "E1058,T. Quill,2026-09-22\n"
    ),
    "iam-active-users.csv": (
        "account,employee_id,enabled,last_login\n"
        "jmarsh,E1043,true,2026-08-26T09:12:44Z\n"
        "apatel,E0977,true,2026-09-29T16:03:10Z\n"
        "lchen,E0912,true,2026-09-30T08:41:55Z\n"
    ),
    "change-tickets-q3.csv": (
        "ticket,privileged,implementer,approver,approved_at\n"
        "CHG-2207,yes,A. Patel,L. Chen,2026-08-03T10:15:00Z\n"
        "CHG-2241,yes,L. Chen,A. Patel,2026-09-11T14:02:00Z\n"
    ),
    "deploy-log-q3.csv": (
        "ticket,deployed_by,deployed_at\n"
        "CHG-2207,A. Patel,2026-08-03T18:30:00Z\n"
        "CHG-2241,L. Chen,2026-09-11T19:45:00Z\n"
    ),
}


def write(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def publication(name, version="1", requires=(), **content):
    # Relative URI references make the same publications usable on any HTTP origin.
    models = model_inventory(FIXTURE_BASE + name)
    for model in models:
        model["location"] = "../models/" + model["name"] + "@" + REVISION + ".yang"
    doc = {"id": name, "version": version, "ontology-version": SUITE, "model": models}
    if requires:
        doc["requires"] = [{"id": dep, "version": "1"} for dep in requires]
    return {ROOT: {"document": [doc], **content}}


def provenance(document, agent, evidence):
    return dict(origin=document, **{"asserted-by": FIRM + agent, "evidence": evidence})


def node(document, agent, fragment, label, kind, evidence="catalogue.json", **extra):
    return {"id": "#" + fragment, "label": label, "type": "example-audit:" + kind, **provenance(document, agent, evidence), **extra}


def incidence(ident, role, target, kind="node"):
    return {"id": ident, "role": "example-audit:" + role, kind: target}


def term(kind, definition, bfo):
    return node(
        "catalogue.json",
        "methodology-desk",
        "term-" + kind,
        kind,
        kind,
        term={"definition": definition, "bfo-class": "http://purl.obolibrary.org/obo/BFO_" + bfo},
    )


def build_publications():
    catalogue = publication(
        "catalogue.json",
        node=[
            term("engagement", "An engagement assessing a client's controls for a period.", "0000015"),
            term("control", "A documented control the client asserts it operates.", "0000002"),
            term("evidence-record", "An artifact collected from a client system.", "0000002"),
            term("source-system", "A client information system that produces artifacts.", "0000002"),
            term("collection-agent", "Software that retrieves client artifacts.", "0000002"),
            term("assessment-agent", "Software that drafts control assessments.", "0000002"),
            term("audit-professional", "A person on the engagement team.", "0000040"),
            node(
                "catalogue.json",
                "engagement-office",
                "eng-2026",
                "Alder Ridge Logistics access and change controls 2026",
                "engagement",
                engagement={"client": "Alder Ridge Logistics Ltd (fictional)", "period-start": "2026-07-01", "period-end": "2026-09-30"},
            ),
            node(
                "catalogue.json",
                "methodology-desk",
                "ac-01",
                "Timely removal of leaver access",
                "control",
                control={
                    "reference": "AC-01",
                    "statement": "Access for terminated employees is disabled within one business day of termination.",
                    "accepted-evidence": ["example-audit:hr-termination-report", "example-audit:active-account-listing"],
                },
            ),
            node(
                "catalogue.json",
                "methodology-desk",
                "cm-02",
                "Independent approval of privileged changes",
                "control",
                control={
                    "reference": "CM-02",
                    "statement": "Privileged production changes are approved by someone other than the implementer before deployment.",
                    "accepted-evidence": ["example-audit:change-ticket-export", "example-audit:deployment-log"],
                },
            ),
            node(
                "catalogue.json",
                "methodology-desk",
                "ac-04",
                "Quarterly user access review",
                "control",
                control={
                    "reference": "AC-04",
                    "statement": "Application owners review user access each quarter and record removals.",
                    "accepted-evidence": ["example-audit:policy-document", "example-audit:active-account-listing"],
                },
            ),
            node("catalogue.json", "engagement-office", "collector", "Evidence collection agent", "collection-agent"),
            node("catalogue.json", "engagement-office", "drafting-agent", "Assessment drafting agent", "assessment-agent"),
            node("catalogue.json", "engagement-office", "m-ito", "M. Ito (fictional senior)", "audit-professional"),
            node("catalogue.json", "engagement-office", "r-okafor", "R. Okafor (fictional manager)", "audit-professional"),
        ],
    )

    def evidence(fragment, label, kind, system, collected_at, export):
        data = EXPORTS[export].encode()
        return node(
            "evidence.json",
            "collector",
            fragment,
            label,
            "evidence-record",
            evidence="exports/" + export,
            **{
                "evidence-record": {
                    "evidence-type": "example-audit:" + kind,
                    "source-system": "#" + system,
                    "collected-at": collected_at,
                    "export": "exports/" + export,
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            },
        )

    def collection(fragment, system, records, at):
        return {
            "id": "#" + fragment,
            "type": "example-audit:collection",
            **provenance("evidence.json", "collector", "exports/" + EVIDENCE_FILES[records[0]]),
            "recorded-at": at,
            "incidence": [
                incidence("by", "collector", "catalogue.json#collector"),
                incidence("from", "source", "#" + system),
                incidence("for", "in-engagement", "catalogue.json#eng-2026"),
                *[incidence("got-" + r, "collected", "#" + r) for r in records],
            ],
        }

    evidence_doc = publication(
        "evidence.json",
        requires=("catalogue.json",),
        node=[
            node("evidence.json", "collector", "peoplecore", "PeopleCore HR (fictional)", "source-system"),
            node("evidence.json", "collector", "gatekeeper", "Gatekeeper IAM (fictional)", "source-system"),
            node("evidence.json", "collector", "changedesk", "ChangeDesk (fictional)", "source-system"),
            evidence("hr-leavers-q3", "Q3 leavers", "hr-termination-report", "peoplecore", "2026-10-02T09:00:00Z", "hr-leavers-q3.csv"),
            evidence("iam-active-users", "Enabled accounts", "active-account-listing", "gatekeeper", "2026-10-02T09:05:00Z", "iam-active-users.csv"),
            evidence("change-tickets-q3", "Q3 privileged change tickets", "change-ticket-export", "changedesk", "2026-10-02T09:10:00Z", "change-tickets-q3.csv"),
            evidence("deploy-log-q3", "Q3 production deployments", "deployment-log", "changedesk", "2026-10-02T09:12:00Z", "deploy-log-q3.csv"),
        ],
        hyperedge=[
            collection("col-hr", "peoplecore", ["hr-leavers-q3"], "2026-10-02T09:01:00Z"),
            collection("col-iam", "gatekeeper", ["iam-active-users"], "2026-10-02T09:06:00Z"),
            collection("col-change", "changedesk", ["change-tickets-q3", "deploy-log-q3"], "2026-10-02T09:13:00Z"),
        ],
    )

    def assessment(fragment, control, assessor, outcome, rationale, cited, at):
        return {
            "id": "#" + fragment,
            "type": "example-audit:assessment",
            **provenance("assessments.json", assessor, "catalogue.json"),
            "recorded-at": at,
            "result": {"outcome": outcome, "rationale": rationale},
            "incidence": [
                incidence("by", "assessor", "catalogue.json#" + assessor),
                incidence("ctl", "assessed-control", "catalogue.json#" + control),
                incidence("for", "in-engagement", "catalogue.json#eng-2026"),
                *[incidence("ev-" + r, "cited-evidence", "evidence.json#" + r) for r in cited],
            ],
        }

    assessments = publication(
        "assessments.json",
        requires=("evidence.json",),
        hyperedge=[
            assessment(
                "as-ac-01",
                "ac-01",
                "drafting-agent",
                "exception",
                "E1043 left on 2026-08-14; account jmarsh was still enabled and logged in on 2026-08-26.",
                ["hr-leavers-q3", "iam-active-users"],
                "2026-10-05T11:00:00Z",
            ),
            assessment(
                "as-cm-02",
                "cm-02",
                "m-ito",
                "supported",
                "Both privileged changes were approved by a different person before deployment.",
                ["change-tickets-q3", "deploy-log-q3"],
                "2026-10-05T14:30:00Z",
            ),
            assessment(
                "as-ac-04",
                "ac-04",
                "drafting-agent",
                "insufficient-evidence",
                "No quarterly access review records were provided for the period.",
                [],
                "2026-10-05T15:10:00Z",
            ),
            {
                "id": "#fd-ac-01",
                "type": "example-audit:finding",
                **provenance("assessments.json", "drafting-agent", "exports/iam-active-users.csv"),
                "recorded-at": "2026-10-05T11:20:00Z",
                "detail": {"severity": "high", "condition": "A terminated employee's account remained enabled and was used 12 days after termination."},
                "incidence": [
                    incidence("basis", "basis", "#as-ac-01", "hyperedge"),
                    incidence("ev-hr", "cited-evidence", "evidence.json#hr-leavers-q3"),
                    incidence("ev-iam", "cited-evidence", "evidence.json#iam-active-users"),
                ],
            },
            {
                "id": "#wp-2026",
                "type": "example-audit:workpaper-bundle",
                **provenance("assessments.json", "drafting-agent", "catalogue.json"),
                "incidence": [incidence("m" + str(n), "member", "#" + a, "hyperedge") for n, a in enumerate(("as-ac-01", "as-cm-02", "as-ac-04"), 1)],
            },
        ],
    )

    def review(fragment, assessment_id, reviewer, decision, at, comment):
        return {
            "id": "#" + fragment,
            "type": "example-audit:review",
            **provenance("reviews.json", reviewer, "assessments.json"),
            "recorded-at": at,
            "sign-off": {"decision": decision, "comment": comment},
            "incidence": [
                incidence("by", "reviewer", "catalogue.json#" + reviewer),
                incidence("of", "reviewed", "assessments.json#" + assessment_id, "hyperedge"),
            ],
        }

    reviews = publication(
        "reviews.json",
        requires=("assessments.json",),
        hyperedge=[
            review("rv-ac-01", "as-ac-01", "r-okafor", "approved", "2026-10-07T10:00:00Z", "Exception confirmed against both exports."),
            review("rv-cm-02", "as-cm-02", "r-okafor", "approved", "2026-10-07T10:20:00Z", "Approver differs from implementer for both tickets."),
            review("rv-ac-04", "as-ac-04", "m-ito", "approved", "2026-10-07T10:40:00Z", "Request access review records from the client."),
        ],
    )
    return {"catalogue.json": catalogue, "evidence.json": evidence_doc, "assessments.json": assessments, "reviews.json": reviews}


EVIDENCE_FILES = {
    "hr-leavers-q3": "hr-leavers-q3.csv",
    "iam-active-users": "iam-active-users.csv",
    "change-tickets-q3": "change-tickets-q3.csv",
    "deploy-log-q3": "deploy-log-q3.csv",
}


def offline_reader(publications):
    def read(url):
        name = url[len(FIXTURE_BASE):] if url.startswith(FIXTURE_BASE) else None
        if name in publications:
            return json.dumps(publications[name]).encode()
        if name and name.startswith("exports/"):
            return EXPORTS[name[len("exports/"):]].encode()
        if "/models/" in url:
            return (HERE / "models" / url.rsplit("/", 1)[1]).read_bytes()
        raise KeyError(url)

    return read


def _edge(tree, fragment):
    return next(e for e in tree[ROOT]["hyperedge"] if e["id"].endswith("#" + fragment))


def _set_target(tree, fragment, incidence_id, target):
    for inc in _edge(tree, fragment)["incidence"]:
        if inc["id"] == incidence_id:
            inc["node"] = target


INVALID = {
    "dangling-evidence": lambda t: _set_target(t, "as-ac-01", "ev-iam-active-users", FIXTURE_BASE + "evidence.json#iam-export-missing"),
    "assessment-without-evidence": lambda t: _edge(t, "as-cm-02").__setitem__(
        "incidence", [i for i in _edge(t, "as-cm-02")["incidence"] if not i["id"].startswith("ev-")]
    ),
    "reviewer-is-assessor": lambda t: _set_target(t, "rv-cm-02", "by", FIXTURE_BASE + "catalogue.json#m-ito"),
    "review-with-two-reviewers": lambda t: _edge(t, "rv-ac-01")["incidence"].append(
        {"id": "by-2", "role": "example-audit:reviewer", "node": FIXTURE_BASE + "catalogue.json#m-ito"}
    ),
    "finding-on-supported-assessment": lambda t: _edge(t, "fd-ac-01")["incidence"][0].__setitem__(
        "hyperedge", FIXTURE_BASE + "assessments.json#as-cm-02"
    ),
    "evidence-type-not-accepted": lambda t: _set_target(t, "as-cm-02", "ev-deploy-log-q3", FIXTURE_BASE + "evidence.json#hr-leavers-q3"),
}


def build():
    publications = build_publications()
    for name, value in publications.items():
        write("documents/" + name, value)
    for name, text in EXPORTS.items():
        (HERE / "documents" / "exports" / name).write_text(text, encoding="utf-8")
    valid = collect(FIXTURE_BASE + "reviews.json", read=offline_reader(publications))
    write("fixtures/valid.json", valid)
    for name, mutate in INVALID.items():
        tree = copy.deepcopy(valid)
        mutate(tree)
        write(f"fixtures/invalid/{name}.json", tree)
    modules = [
        {"name": name, "revision": REVISION, "namespace": "urn:example:" + suffix}
        for name, suffix in zip(MODULES, ("hypergraph", "bfo", "audit"))
    ]
    # RFC 8525 inventory for this static publication. There are no NETCONF/NMDA datastores.
    library = {
        "module-set": [{"name": SUITE, "module": modules}],
        "schema": [{"name": "audit", "module-set": [SUITE]}],
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
