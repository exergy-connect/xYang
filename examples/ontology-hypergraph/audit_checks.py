#!/usr/bin/env python3
"""Application-level engagement checks on a projection that already passed YANG validation.

YANG checks structure, references, role cardinality, separation of reviewer and
assessor, and evidence-type fit. These rules need time arithmetic or graph walks,
so they live here and fail explicitly:

- cited evidence must be collected before the assessment and no more than
  --max-evidence-age-days earlier;
- a review must be recorded after the assessment it reviews;
- every finding's basis assessment needs an approved review;
- every cited evidence record must come from a collection in the same engagement.

Passing these checks is not an audit opinion. The output lists exceptions the
engagement found; a clean run only means these records are internally consistent.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from collector import ROOT


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _targets(edge: dict, role: str, kind: str = "node") -> list[str]:
    return [i[kind] for i in edge.get("incidence", []) if i["role"] == "example-audit:" + role and kind in i]


def check(tree: dict, max_evidence_age_days: int = 30) -> dict:
    graph = tree[ROOT]
    nodes = {n["id"]: n for n in graph["node"]}
    edges = {e["id"]: e for e in graph["hyperedge"]}
    by_type: dict[str, list[dict]] = {}
    for edge in graph["hyperedge"]:
        by_type.setdefault(edge["type"].split(":", 1)[1], []).append(edge)
    issues: list[str] = []

    collected_for: dict[str, set[str]] = {}
    for col in by_type.get("collection", []):
        for engagement in _targets(col, "in-engagement"):
            for record in _targets(col, "collected"):
                collected_for.setdefault(record, set()).add(engagement)

    max_age = timedelta(days=max_evidence_age_days)
    for assessment in by_type.get("assessment", []):
        at = _time(assessment["recorded-at"])
        engagement = _targets(assessment, "in-engagement")[0]
        for record in _targets(assessment, "cited-evidence"):
            collected = _time(nodes[record]["evidence-record"]["collected-at"])
            if collected > at:
                issues.append(f"{assessment['id']}: cites {record} collected after the assessment")
            elif at - collected > max_age:
                issues.append(f"{assessment['id']}: cites {record} collected {(at - collected).days} days earlier (stale)")
            if engagement not in collected_for.get(record, set()):
                issues.append(f"{assessment['id']}: cites {record}, which no collection in {engagement} produced")

    approved: set[str] = set()
    decisions: dict[str, str] = {}
    for review in by_type.get("review", []):
        target = _targets(review, "reviewed", "hyperedge")[0]
        decision = review["sign-off"]["decision"]
        decisions[target] = decision
        if decision == "approved":
            approved.add(target)
        if _time(review["recorded-at"]) < _time(edges[target]["recorded-at"]):
            issues.append(f"{review['id']}: recorded before the assessment it reviews")

    findings = []
    for finding in by_type.get("finding", []):
        basis = _targets(finding, "basis", "hyperedge")[0]
        if basis not in approved:
            issues.append(f"{finding['id']}: basis {basis} has no approved review")
        findings.append({"id": finding["id"], "severity": finding["detail"]["severity"], "basis": basis})

    conclusions = []
    for assessment in by_type.get("assessment", []):
        control = nodes[_targets(assessment, "assessed-control")[0]]["control"]["reference"]
        conclusions.append(
            {
                "control": control,
                "outcome": assessment["result"]["outcome"],
                "review": decisions.get(assessment["id"], "not reviewed"),
            }
        )
    return {
        "scope": "record consistency only; not an audit opinion",
        "conclusions": sorted(conclusions, key=lambda c: c["control"]),
        "findings": findings,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("projection", type=Path)
    parser.add_argument("--max-evidence-age-days", type=int, default=30)
    args = parser.parse_args()
    report = check(json.loads(args.projection.read_text(encoding="utf-8")), args.max_evidence_age_days)
    print(json.dumps(report, indent=2))
    return 1 if report["issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
