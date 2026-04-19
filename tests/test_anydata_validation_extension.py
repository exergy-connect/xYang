"""
draft-ietf-netmod-yang-anydata-validation style checks (§1 counters, §4 JSON names).

Uses minimal stubs evoking RFC8343 interface statistics; not the real ietf-interfaces module.
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


def _validator():
    host = parse_yang_string(HOST_YANG)
    payload = parse_yang_string(PAYLOAD_YANG)
    v = YangValidator(host)
    v.enable_extension(
        ValidatorExtension.ANYDATA_VALIDATION,
        modules={host.name: host, payload.name: payload},
        mode=AnydataValidationMode.COMPLETE,
    )
    return v


def test_anydata_complete_accepts_valid_counters():
    """draft §1 / RFC8343-shaped counters; draft §4 namespace-qualified anydata root."""
    v = _validator()
    data = {
        "notification": {
            "payload": {
                "example-rfc8343-shape:interfaces-state": {
                    "interface": [{"name": "eth0", "in-octets": 42}],
                },
            },
        },
    }
    ok, errors, _warnings = v.validate(data)
    assert ok, errors


def test_anydata_complete_rejects_invalid_in_octets():
    """draft §1: defective sender with invalid counter; COMPLETE must catch it."""
    v = _validator()
    data = {
        "notification": {
            "payload": {
                "example-rfc8343-shape:interfaces-state": {
                    "interface": [{"name": "eth0", "in-octets": "not-a-number"}],
                },
            },
        },
    }
    ok, errors, _warnings = v.validate(data)
    assert not ok
    assert errors
    assert any("in-octets" in e or "integer" in e.lower() for e in errors)


def test_anydata_candidate_allows_invalid_in_octets_type_check():
    """draft §5 / RFC7950 §8.3.3 candidate: no type (constraint) checks on subtree."""
    host = parse_yang_string(HOST_YANG)
    payload = parse_yang_string(PAYLOAD_YANG)
    v = YangValidator(host)
    v.enable_extension(
        ValidatorExtension.ANYDATA_VALIDATION,
        modules={host.name: host, payload.name: payload},
        mode=AnydataValidationMode.CANDIDATE,
    )
    data = {
        "notification": {
            "payload": {
                "example-rfc8343-shape:interfaces-state": {
                    "interface": [{"name": "eth0", "in-octets": "not-a-number"}],
                },
            },
        },
    }
    ok, errors, _warnings = v.validate(data)
    assert ok, errors


def test_anydata_unknown_qualified_member():
    v = _validator()
    data = {
        "notification": {
            "payload": {
                "example-rfc8343-shape:nonexistent": {},
            },
        },
    }
    ok, errors, _warnings = v.validate(data)
    assert not ok
    assert any("nonexistent" in e for e in errors)


def test_enable_extension_modules_key_must_match_module_name():
    host = parse_yang_string(HOST_YANG)
    payload = parse_yang_string(PAYLOAD_YANG)
    v = YangValidator(host)
    try:
        v.enable_extension(
            ValidatorExtension.ANYDATA_VALIDATION,
            modules={"wrong-key": payload},
            mode=AnydataValidationMode.COMPLETE,
        )
    except TypeError as e:
        assert "must match" in str(e).lower() or "name" in str(e).lower()
    else:
        raise AssertionError("expected TypeError for mismatched module map key")
