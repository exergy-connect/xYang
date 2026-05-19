"""CLI and validator: --anydata-validation with module discovery and notifications."""

from __future__ import annotations

from xyang import parse_yang_string, YangValidator
from xyang.ext.anydata_validation import AnydataValidationMode
from xyang.validator import ValidatorExtension

ENVELOPE_HOST = """
module example-ypn {
  yang-version 1.1;
  namespace "urn:example:ypn";
  prefix ypn;
  container envelope {
    leaf event-time { type string; mandatory true; }
    anydata contents;
  }
}
"""

PUSH_YANG = """
module example-push {
  yang-version 1.1;
  namespace "urn:example:push";
  prefix yp;
  notification push-change-update {
    leaf id { type uint32; }
    container datastore-changes {
      leaf patch-id { type string; }
    }
  }
}
"""


def test_structure_instance_root_and_anydata_notification():
    host = parse_yang_string(ENVELOPE_HOST)
    push = parse_yang_string(PUSH_YANG)

    v = YangValidator(host)
    v.enable_extension(
        ValidatorExtension.ANYDATA_VALIDATION,
        modules={host.name: host, push.name: push},
        mode=AnydataValidationMode.COMPLETE,
    )
    data = {
        "envelope": {
            "event-time": "2026-01-01T00:00:00Z",
            "contents": {
                "example-push:push-change-update": {
                    "id": 1,
                    "datastore-changes": {"patch-id": "0"},
                },
            },
        },
    }
    ok, errors, _warnings = v.validate(data)
    assert ok, errors


def test_anydata_rejects_unknown_qualified_member():
    host = parse_yang_string(
        """
module h {
  yang-version 1.1;
  namespace "urn:h";
  prefix h;
  container c { anydata payload; }
}
"""
    )
    v = YangValidator(host)
    v.enable_extension(
        ValidatorExtension.ANYDATA_VALIDATION,
        modules={host.name: host},
        mode=AnydataValidationMode.COMPLETE,
    )
    ok, errors, _ = v.validate({"c": {"payload": {"unknown-mod:node": {}}}})
    assert not ok
    assert any("Unknown anydata member" in e for e in errors)
