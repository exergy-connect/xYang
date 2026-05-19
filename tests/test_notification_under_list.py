"""``notification`` under ``list`` / ``container`` / ``grouping`` (RFC 7950 YANG 1.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from xyang import parse_yang_file, parse_yang_string
from xyang.ast import YangListStmt, YangNotificationStmt

_REPO = Path(__file__).resolve().parent.parent
IETF_ALARMS = _REPO / "examples" / "ietf-yang-push" / "modules" / "ietf-alarms@2019-09-11.yang"


def test_notification_under_list_inline() -> None:
    mod = parse_yang_string(
        """module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  grouping g {
    leaf x { type string; }
  }
  list alarm {
    key "id";
    leaf id { type string; }
    uses g;
    notification operator-action {
      uses g;
    }
  }
}"""
    )
    lst = mod.find_statement("alarm")
    assert isinstance(lst, YangListStmt)
    notif = next(
        s for s in lst.statements if isinstance(s, YangNotificationStmt) and s.name == "operator-action"
    )
    assert notif.name == "operator-action"
    assert len(notif.statements) >= 1


def test_notification_under_container_and_grouping() -> None:
    mod = parse_yang_string(
        """module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  grouping g {
    notification g-notif { leaf a { type string; } }
  }
  container c {
    notification c-notif { leaf b { type string; } }
  }
}"""
    )
    g = mod.groupings["g"]
    assert any(isinstance(s, YangNotificationStmt) and s.name == "g-notif" for s in g.statements)
    c = mod.find_statement("c")
    assert c is not None
    assert any(isinstance(s, YangNotificationStmt) and s.name == "c-notif" for s in c.statements)


@pytest.mark.skipif(not IETF_ALARMS.is_file(), reason="ietf-alarms example module missing")
def test_ietf_alarms_list_alarm_operator_action_notification(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING", logger="xyang.parser.unsupported_skip"):
        mod = parse_yang_file(IETF_ALARMS)
    assert not any(
        "notification" in r.getMessage().lower() and "alarm" in r.getMessage().lower()
        for r in caplog.records
    )
    alarms = mod.find_statement("alarms")
    assert alarms is not None
    alarm_list = next(s for s in alarms.statements if getattr(s, "name", None) == "alarm-list")
    alarm = next(s for s in alarm_list.statements if isinstance(s, YangListStmt) and s.name == "alarm")
    notif = next(
        s for s in alarm.statements if isinstance(s, YangNotificationStmt) and s.name == "operator-action"
    )
    assert notif.name == "operator-action"
