"""Write session/invalid/*.json: one mutation of session/valid.json per rule.

Run from anywhere: python examples/mcp-interface/build_fixtures.py
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
ROOT = "example-topology-tools:session"
TOOL = "example-topology-tools:"


def call(doc: dict[str, Any], call_id: int) -> dict[str, Any]:
    return next(c for c in doc[ROOT]["call"] if c["id"] == call_id)


def hallucinated_link_target(d):
    call(d, 4)["arguments"]["add-link"]["target"] = "r9"


def link_before_node(d):
    call(d, 3)["id"] = 8  # h1 is now created after the link (5) and the path (7) that use it


def link_to_failed_node(d):
    call(d, 2)["result"] = {"status": "error", "message": "quota exceeded"}


def self_loop(d):
    call(d, 4)["arguments"]["add-link"]["target"] = "r1"


def duplicate_node(d):
    call(d, 6)["result"] = {"status": "ok"}


def undeclared_tool(d):
    call(d, 6)["tool"] = TOOL + "delete-node"


def arguments_for_other_tool(d):
    call(d, 4)["arguments"] = {"add-node": {"session": d[ROOT]["handle"], "name": "r3"}}


def missing_arguments(d):
    call(d, 1)["arguments"] = {}


def hallucinated_path_hop(d):
    call(d, 7)["result"]["find-path"]["hop"] = ["r1", "r9", "h1"]


def path_missing_endpoint(d):
    call(d, 7)["result"]["find-path"]["hop"] = ["r1", "r2"]


def path_too_long(d):
    call(d, 7)["arguments"]["find-path"]["max-hops"] = 1


def call_in_other_session(d):
    call(d, 4)["arguments"]["add-link"]["session"] = "ses_00000000000000000000000000000000"


def bandwidth_out_of_range(d):
    call(d, 5)["arguments"]["add-link"]["bandwidth-mbps"] = 0


MUTATIONS: dict[str, Callable[[dict[str, Any]], None]] = {
    f.__name__.replace("_", "-"): f
    for f in (
        hallucinated_link_target,
        link_before_node,
        link_to_failed_node,
        self_loop,
        duplicate_node,
        undeclared_tool,
        arguments_for_other_tool,
        missing_arguments,
        hallucinated_path_hop,
        path_missing_endpoint,
        path_too_long,
        bandwidth_out_of_range,
        call_in_other_session,
    )
}


def main() -> None:
    valid = json.loads((HERE / "session" / "valid.json").read_text())
    out = HERE / "session" / "invalid"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    for name, mutate in MUTATIONS.items():
        doc = copy.deepcopy(valid)
        mutate(doc)
        (out / f"{name}.json").write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote {len(MUTATIONS)} fixtures to {out}")


if __name__ == "__main__":
    main()
