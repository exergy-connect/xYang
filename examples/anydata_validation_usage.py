"""
Optional ``anydata`` subtree validation (draft-ietf-netmod-yang-anydata-validation).

Uses minimal YANG stubs aligned with the draft's §1 (interface counters) and §4
(JSON ``module-name:node`` under ``anydata``).

Three behaviors:

1. **Extension off** (default) — children of ``anydata`` are not validated against
   other modules; arbitrary JSON is accepted.
2. **``AnydataValidationMode.COMPLETE``** — full RFC 7950 checks on the resolved subtree
   (``when``, ``must``, types, …).
3. **``AnydataValidationMode.CANDIDATE``** — structural checks under the subtree without
   those constraint phases (per draft §5 / RFC 7950 §8.3.3 style).

Run::

    PYTHONPATH=src python3 examples/anydata_validation_usage.py
"""

from __future__ import annotations

from xyang import parse_yang_string, YangValidator
from xyang.ext.anydata_validation import AnydataValidationMode
from xyang.validator import ValidatorExtension

HOST_YANG = """
module example-push-host {
  yang-version 1.1;
  namespace "urn:ietf:params:draft:anydata-validation:host";
  prefix ph;
  container notification {
    anydata payload {
      description "Opaque subtree; draft §4 JSON uses module:node members.";
    }
  }
}
"""

PAYLOAD_YANG = """
module example-rfc8343-shape {
  yang-version 1.1;
  namespace "urn:ietf:params:draft:anydata-validation:8343-shape";
  prefix ifshape;
  container interfaces-state {
    list interface {
      key name;
      leaf name { type string; }
      leaf in-octets { type uint64; }
    }
  }
}
"""


def _modules():
    host = parse_yang_string(HOST_YANG)
    payload = parse_yang_string(PAYLOAD_YANG)
    return {host.name: host, payload.name: payload}, host


INSTANCE_OK = {
    "notification": {
        "payload": {
            "example-rfc8343-shape:interfaces-state": {
                "interface": [{"name": "eth0", "in-octets": 42}],
            },
        },
    },
}

# Invalid ``in-octets`` (not an integer) — COMPLETE rejects; CANDIDATE ignores type rules.
INSTANCE_BAD_TYPE = {
    "notification": {
        "payload": {
            "example-rfc8343-shape:interfaces-state": {
                "interface": [{"name": "eth0", "in-octets": "not-a-number"}],
            },
        },
    },
}


def main() -> None:
    modules, host = _modules()

    print("=== 1. Extension OFF (default) ===")
    print("    No enable_extension — anydata contents are opaque.")
    v_off = YangValidator(host)
    ok, errors, _w = v_off.validate(INSTANCE_BAD_TYPE)
    print(f"    Invalid in-octets string → valid={ok!r}, errors={errors!r}")

    print("\n=== 2. AnydataValidationMode.COMPLETE ===")
    print("    Full constraint validation on the subtree.")
    v_complete = YangValidator(host)
    v_complete.enable_extension(
        ValidatorExtension.ANYDATA_VALIDATION,
        modules=modules,
        mode=AnydataValidationMode.COMPLETE,
    )
    ok, errors, _w = v_complete.validate(INSTANCE_OK)
    print(f"    Good counters → valid={ok!r}")
    ok, errors, _w = v_complete.validate(INSTANCE_BAD_TYPE)
    print(f"    Bad in-octets → valid={ok!r}")
    for e in errors:
        print(f"      {e}")

    print("\n=== 3. AnydataValidationMode.CANDIDATE ===")
    print("    Structural validation only (no when/must/type on the anydata subtree).")
    v_cand = YangValidator(host)
    v_cand.enable_extension(
        ValidatorExtension.ANYDATA_VALIDATION,
        modules=modules,
        mode=AnydataValidationMode.CANDIDATE,
    )
    ok, errors, _w = v_cand.validate(INSTANCE_BAD_TYPE)
    print(f"    Same bad in-octets → valid={ok!r}, errors={errors!r}")


if __name__ == "__main__":
    main()
