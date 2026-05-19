"""Anydata module map: cross-file augments merge into imported targets."""

from __future__ import annotations

from pathlib import Path

from xyang import YangValidator
from xyang.ast import YangLeafStmt
from xyang.ext.anydata_validation import AnydataValidationMode
from xyang.parser import YangParser
from xyang.validator import ValidatorExtension
from xyang.__main__ import _load_anydata_module_map


def test_anydata_module_map_merges_cross_file_augment(tmp_path: Path) -> None:
  (tmp_path / "ietf-yang-push@2019-09-09.yang").write_text(
    """
module ietf-yang-push {
  yang-version 1.1;
  namespace "urn:ietf:params:xml:ns:yang:ietf-yang-push";
  prefix yp;
  notification push-change-update {
    leaf id { type uint32; }
  }
}
""",
    encoding="utf-8",
  )
  (tmp_path / "ietf-distributed-notif@2024-04-21.yang").write_text(
    """
module ietf-distributed-notif {
  yang-version 1.1;
  namespace "urn:ietf:params:xml:ns:yang:ietf-distributed-notif";
  prefix dn;
  import ietf-yang-push { prefix yp; }
  augment "/yp:push-change-update" {
    leaf message-publisher-id { type uint32; config false; }
  }
}
""",
    encoding="utf-8",
  )
  (tmp_path / "host.yang").write_text(
    """
module host {
  yang-version 1.1;
  namespace "urn:host";
  prefix h;
  container envelope { anydata contents; }
}
""",
    encoding="utf-8",
  )

  host = YangParser().parse_file(tmp_path / "host.yang")
  modules = _load_anydata_module_map(
    (tmp_path / "host.yang").resolve(),
    host,
    include_path=(str(tmp_path),),
    extra_module_paths=[
      tmp_path / "ietf-yang-push@2019-09-09.yang",
      tmp_path / "ietf-distributed-notif@2024-04-21.yang",
    ],
  )
  yp = modules["ietf-yang-push"]
  notif = yp.find_statement("push-change-update")
  assert notif is not None
  pub = notif.find_statement("message-publisher-id")
  assert isinstance(pub, YangLeafStmt)

  v = YangValidator(host)
  v.enable_extension(
    ValidatorExtension.ANYDATA_VALIDATION,
    modules=modules,
    mode=AnydataValidationMode.COMPLETE,
  )
  data = {
    "envelope": {
      "contents": {
        "ietf-yang-push:push-change-update": {
          "id": 1,
          "ietf-distributed-notif:message-publisher-id": 42,
        },
      },
    },
  }
  ok, errors, _ = v.validate(data)
  assert ok, errors
