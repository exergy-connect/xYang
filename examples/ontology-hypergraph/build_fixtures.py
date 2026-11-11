#!/usr/bin/env python3
"""Regenerate the synthetic audit publications, exports, projections, and schema inventory.

All names, people, systems, and records are fictional. The same tables produce
the CSV exports and the structured facts, so the facts match the exported rows.
"""

import copy
import hashlib
import json
from datetime import datetime

from collector import HERE, MODULES, REVISION, ROOT, collect, model_inventory

FIXTURE_BASE = "http://audit.test/documents/"
SUITE = "audit-2026.1"
FIRM = "https://larkspur-reed.example/agents/"
DAY = 86_400


def at(iso: str) -> int:
    """UTC ISO 8601 timestamp to the model's epoch seconds."""
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


# Client facts. Times are UTC.
EMPLOYEES = [("e0912", "E0912", "L. Chen"), ("e0977", "E0977", "A. Patel"), ("e1031", "E1031", "R. Vance"),
             ("e1043", "E1043", "J. Marsh"), ("e1058", "E1058", "T. Quill")]  # fmt: skip
TERMINATIONS = [("e1031", "2026-07-03T17:00:00Z"), ("e1043", "2026-08-14T17:00:00Z"), ("e1058", "2026-09-22T17:00:00Z")]
ACCOUNTS = [("lchen", "e0912"), ("apatel", "e0977"), ("rvance", "e1031"), ("jmarsh", "e1043"), ("tquill", "e1058")]
# (account, time): rvance before termination, jmarsh 12 days after, tquill at the exact
# termination second (not after it), apatel and lchen never terminated.
SIGN_INS = [("rvance", "2026-07-02T08:00:00Z"), ("jmarsh", "2026-08-26T09:12:44Z"), ("tquill", "2026-09-22T17:00:00Z"),
            ("apatel", "2026-09-29T16:03:10Z"), ("lchen", "2026-09-30T08:41:55Z")]  # fmt: skip
CHANGES = [  # (ticket, implementer, approver, approved, deployed)
    ("CHG-2207", "e0977", "e0912", "2026-08-03T10:15:00Z", "2026-08-03T18:30:00Z"),
    ("CHG-2241", "e0912", "e0977", "2026-09-11T19:45:00Z", "2026-09-11T19:45:00Z"),
]
NAMES = {key: name for key, _, name in EMPLOYEES}
STAFF = {key: staff for key, staff, _ in EMPLOYEES}
OWNERS = dict(ACCOUNTS)
ENGAGEMENT = {
    "client": "Alder Ridge Logistics Ltd (fictional)",
    "period-start": at("2026-07-01T00:00:00Z"),
    "period-end": at("2026-09-30T23:59:59Z"),
    "as-of": at("2026-10-08T00:00:00Z"),
    "max-evidence-age": 30 * DAY,
}

EXPORTS = {
    "hr-leavers-q3.csv": "employee_id,name,termination_effective\n"
    + "".join(f"{STAFF[e]},{NAMES[e]},{t}\n" for e, t in TERMINATIONS),
    "iam-signins-q3.csv": "account,employee_id,signed_in_at\n"
    + "".join(f"{a},{STAFF[OWNERS[a]]},{t}\n" for a, t in SIGN_INS),
    "change-tickets-q3.csv": "ticket,privileged,implementer,approver,approved_at\n"
    + "".join(f"{c},yes,{NAMES[i]},{NAMES[a]},{ap}\n" for c, i, a, ap, _ in CHANGES),
    "deploy-log-q3.csv": "ticket,deployed_by,deployed_at\n" + "".join(f"{c},{NAMES[i]},{d}\n" for c, i, _, _, d in CHANGES),
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


def control(fragment, label, reference, statement, rule, accepted):
    return node(
        "catalogue.json",
        "methodology-desk",
        fragment,
        label,
        "control",
        control={
            "reference": reference,
            "statement": statement,
            "rule": "example-audit:" + rule,
            "accepted-evidence": ["example-audit:" + kind for kind in accepted],
        },
    )


def build_publications():
    catalogue = publication(
        "catalogue.json",
        node=[
            term("engagement", "An engagement assessing a client's controls for a period.", "0000015"),
            term("control", "A documented control the client asserts it operates.", "0000002"),
            term("evidence-record", "An artifact collected from a client system.", "0000002"),
            term("source-system", "A client information system that produces artifacts.", "0000002"),
            term("employee", "A person employed by the client.", "0000040"),
            term("account", "A client system account owned by one employee.", "0000002"),
            term("termination-event", "The taking effect of an employee's termination.", "0000015"),
            term("account-use-event", "A recorded use of an account.", "0000015"),
            term("change-event", "A privileged change reaching production.", "0000015"),
            term("collection-agent", "Software that retrieves client artifacts.", "0000002"),
            term("assessment-agent", "Software that drafts control assessments.", "0000002"),
            term("audit-professional", "A person on the engagement team.", "0000040"),
            node(
                "catalogue.json",
                "engagement-office",
                "eng-2026",
                "Alder Ridge Logistics access and change controls 2026",
                "engagement",
                engagement=ENGAGEMENT,
            ),
            control("ac-01", "No use of leaver accounts", "AC-01", "No account is used after its owner's termination takes effect.",
                    "leaver-access", ["hr-termination-report", "sign-in-log"]),  # fmt: skip
            control("cm-02", "Independent approval of privileged changes", "CM-02",
                    "Each privileged production change is approved by someone other than the implementer no later than deployment.",
                    "change-approval", ["change-ticket-export", "deployment-log"]),  # fmt: skip
            control("ac-04", "Quarterly user access review", "AC-04",
                    "Application owners review user access each quarter and record removals.",
                    "manual-review", ["access-review-record"]),  # fmt: skip
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
                    "collected-at": at(collected_at),
                    "export": "exports/" + export,
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            },
        )

    def fact(fragment, label, kind, export, **content):
        return node("evidence.json", "collector", fragment, label, kind, evidence="exports/" + export, **content)

    def collection(fragment, system, records, recorded):
        return {
            "id": "#" + fragment,
            "type": "example-audit:collection",
            **provenance("evidence.json", "collector", "exports/" + EVIDENCE_FILES[records[0]]),
            "recorded-at": at(recorded),
            "incidence": [
                incidence("by", "collector", "catalogue.json#collector"),
                incidence("from", "source", "#" + system),
                incidence("for", "in-engagement", "catalogue.json#eng-2026"),
                *[incidence("got-" + r, "collected", "#" + r) for r in records],
            ],
        }

    terminated = {e: at(t) for e, t in TERMINATIONS}
    evidence_doc = publication(
        "evidence.json",
        requires=("catalogue.json",),
        node=[
            node("evidence.json", "collector", "peoplecore", "PeopleCore HR (fictional)", "source-system"),
            node("evidence.json", "collector", "gatekeeper", "Gatekeeper IAM (fictional)", "source-system"),
            node("evidence.json", "collector", "changedesk", "ChangeDesk (fictional)", "source-system"),
            evidence("hr-leavers-q3", "Q3 leavers", "hr-termination-report", "peoplecore", "2026-10-02T09:00:00Z", "hr-leavers-q3.csv"),
            evidence("iam-signins-q3", "Q3 sign-ins", "sign-in-log", "gatekeeper", "2026-10-02T09:05:00Z", "iam-signins-q3.csv"),
            evidence("change-tickets-q3", "Q3 privileged change tickets", "change-ticket-export", "changedesk", "2026-10-02T09:10:00Z", "change-tickets-q3.csv"),
            evidence("deploy-log-q3", "Q3 production deployments", "deployment-log", "changedesk", "2026-10-02T09:12:00Z", "deploy-log-q3.csv"),
            *[fact(e, f"{NAMES[e]} (fictional)", "employee", "hr-leavers-q3.csv", employee={"staff-id": STAFF[e]}) for e, _, _ in EMPLOYEES],
            *[fact(a, a, "account", "iam-signins-q3.csv", account={"login": a, "owner": "#" + o}) for a, o in ACCOUNTS],
            *[
                fact(f"term-{e}", f"{NAMES[e]} leaves", "termination-event", "hr-leavers-q3.csv",
                     termination={"employee": "#" + e, "effective-at": at(t), "source": "#hr-leavers-q3"})  # fmt: skip
                for e, t in TERMINATIONS
            ],
            *[
                fact(f"use-{a}", f"{a} signs in", "account-use-event", "iam-signins-q3.csv",
                     **{"account-use": {"account": "#" + a, "at": at(t), "source": "#iam-signins-q3",
                                        "breach": "yes" if OWNERS[a] in terminated and terminated[OWNERS[a]] < at(t) else "no"}})  # fmt: skip
                for a, t in SIGN_INS
            ],
            *[
                fact(f"chg-{c.lower()}", c, "change-event", "change-tickets-q3.csv",
                     change={"ticket": c, "implementer": "#" + i, "approver": "#" + ap, "approved-at": at(apt),
                             "deployed-at": at(dep), "source": "#change-tickets-q3", "deployment-source": "#deploy-log-q3",
                             "breach": "yes" if ap == i or at(apt) > at(dep) else "no"})  # fmt: skip
                for c, i, ap, apt, dep in CHANGES
            ],
        ],
        hyperedge=[
            collection("col-hr", "peoplecore", ["hr-leavers-q3"], "2026-10-02T09:01:00Z"),
            collection("col-iam", "gatekeeper", ["iam-signins-q3"], "2026-10-02T09:06:00Z"),
            collection("col-change", "changedesk", ["change-tickets-q3", "deploy-log-q3"], "2026-10-02T09:13:00Z"),
        ],
    )

    def assessment(fragment, ctl, assessor, outcome, rationale, cited, recorded):
        return {
            "id": "#" + fragment,
            "type": "example-audit:assessment",
            **provenance("assessments.json", assessor, "catalogue.json"),
            "recorded-at": at(recorded),
            "result": {"outcome": outcome, "rationale": rationale},
            "incidence": [
                incidence("by", "assessor", "catalogue.json#" + assessor),
                incidence("ctl", "assessed-control", "catalogue.json#" + ctl),
                incidence("for", "in-engagement", "catalogue.json#eng-2026"),
                *[incidence("ev-" + r, "cited-evidence", "evidence.json#" + r) for r in cited],
            ],
        }

    assessments = publication(
        "assessments.json",
        requires=("evidence.json",),
        hyperedge=[
            assessment("as-ac-01", "ac-01", "drafting-agent", "exception",
                       "E1043's termination took effect 2026-08-14T17:00Z; account jmarsh signed in 2026-08-26T09:12:44Z.",
                       ["hr-leavers-q3", "iam-signins-q3"], "2026-10-05T11:00:00Z"),  # fmt: skip
            assessment("as-cm-02", "cm-02", "m-ito", "supported",
                       "Both privileged changes were approved by a different person no later than deployment.",
                       ["change-tickets-q3", "deploy-log-q3"], "2026-10-05T14:30:00Z"),  # fmt: skip
            assessment("as-ac-04", "ac-04", "drafting-agent", "insufficient-evidence",
                       "No quarterly access review records were provided for the period.", [], "2026-10-05T15:10:00Z"),  # fmt: skip
            {
                "id": "#fd-ac-01",
                "type": "example-audit:finding",
                **provenance("assessments.json", "drafting-agent", "exports/iam-signins-q3.csv"),
                "recorded-at": at("2026-10-07T11:20:00Z"),
                "detail": {"severity": "high", "condition": "Account jmarsh was used 12 days after its owner's termination took effect."},
                "incidence": [
                    incidence("basis", "basis", "#as-ac-01", "hyperedge"),
                    incidence("v-jmarsh", "violation", "evidence.json#use-jmarsh"),
                    incidence("ev-hr", "cited-evidence", "evidence.json#hr-leavers-q3"),
                    incidence("ev-iam", "cited-evidence", "evidence.json#iam-signins-q3"),
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

    def review(fragment, assessment_id, reviewer, decision, recorded, comment):
        return {
            "id": "#" + fragment,
            "type": "example-audit:review",
            **provenance("reviews.json", reviewer, "assessments.json"),
            "recorded-at": at(recorded),
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
    "iam-signins-q3": "iam-signins-q3.csv",
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


def _find(tree, fragment):
    graph = tree[ROOT]
    return next(e for e in graph["hyperedge"] + graph["node"] if e["id"].endswith("#" + fragment))


def _set_target(tree, fragment, incidence_id, target, kind="node"):
    for inc in _find(tree, fragment)["incidence"]:
        if inc["id"] == incidence_id:
            inc[kind] = target


def _drop(tree, fragment):
    graph = tree[ROOT]
    graph["hyperedge"] = [e for e in graph["hyperedge"] if not e["id"].endswith("#" + fragment)]


def _drop_incidence(tree, fragment, prefix):
    edge = _find(tree, fragment)
    edge["incidence"] = [i for i in edge["incidence"] if not i["id"].startswith(prefix)]


B = FIXTURE_BASE
# One rule each. Expected errors are asserted exactly in tests/test_ontology_hypergraph.py.
INVALID = {
    # Reference integrity and structure.
    "dangling-evidence": lambda t: _set_target(t, "as-ac-01", "ev-iam-signins-q3", B + "evidence.json#iam-export-missing"),
    "assessment-without-evidence": lambda t: _drop_incidence(t, "as-cm-02", "ev-"),
    "reviewer-is-assessor": lambda t: _set_target(t, "rv-cm-02", "by", B + "catalogue.json#m-ito"),
    "review-with-two-reviewers": lambda t: _find(t, "rv-ac-01")["incidence"].append(
        {"id": "by-2", "role": "example-audit:reviewer", "node": B + "catalogue.json#m-ito"}
    ),
    "evidence-type-not-accepted": lambda t: _set_target(t, "as-cm-02", "ev-deploy-log-q3", B + "evidence.json#hr-leavers-q3"),
    "finding-on-supported-assessment": lambda t: _set_target(t, "fd-ac-01", "basis", B + "assessments.json#as-cm-02", "hyperedge"),
    # Conclusions must agree with facts.
    "supported-despite-breach": lambda t: (_find(t, "as-ac-01")["result"].update(outcome="supported"), _drop(t, "fd-ac-01")),
    "breach-declared-no": lambda t: _find(t, "use-jmarsh")["account-use"].update(breach="no"),
    "missing-exception-finding": lambda t: _drop(t, "fd-ac-01"),
    "unsupported-finding": lambda t: _find(t, "fd-ac-01")["incidence"].insert(
        2, {"id": "v-apatel", "role": "example-audit:violation", "node": B + "evidence.json#use-apatel"}
    ),
    "breach-claimed-for-unterminated-owner": lambda t: _find(t, "use-apatel")["account-use"].update(breach="yes"),
    "breach-claimed-at-termination-second": lambda t: _find(t, "use-tquill")["account-use"].update(breach="yes"),
    "exception-without-breach": lambda t: _find(t, "as-cm-02")["result"].update(outcome="exception"),
    "self-approved-change-declared-no": lambda t: _find(t, "chg-chg-2241")["change"].update(approver=B + "evidence.json#e0912"),
    "change-approved-after-deployment-declared-no": lambda t: _find(t, "chg-chg-2207")["change"].update(**{"approved-at": at("2026-08-03T18:30:01Z")}),
    "finding-without-approved-review": lambda t: _find(t, "rv-ac-01")["sign-off"].update(decision="rejected"),
    # Time and provenance.
    "stale-evidence": lambda t: _find(t, "iam-signins-q3")["evidence-record"].update(**{"collected-at": ENGAGEMENT["as-of"] - 30 * DAY - 1}),
    "evidence-collected-after-assessment": lambda t: _find(t, "deploy-log-q3")["evidence-record"].update(**{"collected-at": at("2026-10-05T14:30:01Z")}),
    "review-before-assessment": lambda t: _find(t, "rv-cm-02").update(**{"recorded-at": at("2026-10-05T14:29:59Z")}),
    "review-after-as-of": lambda t: _find(t, "rv-ac-04").update(**{"recorded-at": ENGAGEMENT["as-of"] + 1}),
    "evidence-not-collected-for-engagement": lambda t: _drop_incidence(t, "col-iam", "got-"),
    "use-outside-period": lambda t: _find(t, "use-lchen")["account-use"].update(at=ENGAGEMENT["period-end"] + 1),
}


def build():
    publications = build_publications()
    for name, value in publications.items():
        write("documents/" + name, value)
    exports = HERE / "documents" / "exports"
    for stale in exports.glob("*.csv"):
        if stale.name not in EXPORTS:
            stale.unlink()
    for name, text in EXPORTS.items():
        (exports / name).write_text(text, encoding="utf-8")
    valid = collect(FIXTURE_BASE + "reviews.json", read=offline_reader(publications))
    write("fixtures/valid.json", valid)
    invalid_dir = HERE / "fixtures" / "invalid"
    for stale in invalid_dir.glob("*.json"):
        if stale.stem not in INVALID:
            stale.unlink()
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
