"""Minimal parse coverage for ``rpc`` with ``input`` and ``output`` (RFC 7950 §7.14)."""

from __future__ import annotations

from xyang import parse_yang_string
from xyang.ast import YangInputStmt, YangLeafStmt, YangOutputStmt, YangRpcStmt


def test_rpc_input_output_minimal():
    yang = """
module example-rpc {
  yang-version 1.1;
  namespace "urn:example:rpc";
  prefix erpc;

  rpc reboot {
    input {
      leaf delay-seconds {
        type uint16;
      }
    }
    output {
      leaf status-message {
        type string;
      }
    }
  }
}
"""
    mod = parse_yang_string(yang)
    reboot = mod.find_statement("reboot")
    assert isinstance(reboot, YangRpcStmt)
    assert reboot.name == "reboot"

    inp = reboot.find_statement("input")
    assert isinstance(inp, YangInputStmt)
    delay = inp.find_statement("delay-seconds")
    assert isinstance(delay, YangLeafStmt)
    assert delay.type is not None
    assert delay.type.name == "uint16"

    out = reboot.find_statement("output")
    assert isinstance(out, YangOutputStmt)
    msg = out.find_statement("status-message")
    assert isinstance(msg, YangLeafStmt)
    assert msg.type is not None
    assert msg.type.name == "string"
